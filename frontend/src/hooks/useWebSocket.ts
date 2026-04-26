import { useEffect, useRef } from 'react'
import { useStore } from '../store'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const store = useStore.getState()

  useEffect(() => {
    let unmounted = false

    function connect() {
      if (unmounted) return
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        useStore.getState().setWsConnected(true)
      }

      ws.onclose = () => {
        useStore.getState().setWsConnected(false)
        if (!unmounted) {
          reconnectTimer.current = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => ws.close()

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          handleMessage(msg)
        } catch {
          // ignore malformed
        }
      }
    }

    function handleMessage(msg: { type: string; data: unknown }) {
      const s = useStore.getState()
      switch (msg.type) {
        case 'container_status': {
          const d = msg.data as { containers: Parameters<typeof s.setContainers>[0] }
          s.setContainers(d.containers)
          break
        }
        case 'log_line': {
          s.addLog(msg.data as Parameters<typeof s.addLog>[0])
          break
        }
        case 'finding': {
          s.addFinding(msg.data as Parameters<typeof s.addFinding>[0])
          s.setActiveTab('findings')
          break
        }
        case 'plan_ready': {
          s.attachPlan(msg.data as Parameters<typeof s.attachPlan>[0])
          break
        }
        case 'finding_updated': {
          const d = msg.data as { id: string; status: string }
          s.updateFinding(d.id, { status: d.status as 'dismissed' })
          break
        }
        case 'action_update': {
          const d = msg.data as Parameters<typeof s.setActionUpdate>[0]
          s.setActionUpdate(d)
          if (d.status !== 'executing') {
            s.addAuditEntry({
              id: crypto.randomUUID(),
              timestamp: new Date().toISOString(),
              event_type: 'action_executed',
              container_name: null,
              action: d.label ?? null,
              result: d.status,
              details: d.output ?? null,
            })
          }
          break
        }
      }
    }

    connect()

    // Fetch initial data
    fetch('/api/findings')
      .then((r) => r.json())
      .then((findings) => findings.forEach(useStore.getState().addFinding))
      .catch(() => {})

    fetch('/api/audit')
      .then((r) => r.json())
      .then((entries) =>
        entries.reverse().forEach(useStore.getState().addAuditEntry),
      )
      .catch(() => {})

    return () => {
      unmounted = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])
}
