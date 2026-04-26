import { useState, useEffect } from 'react'
import { useStore, Container } from '../store'

const STATUS_DOT: Record<string, string> = {
  running: 'bg-green-500',
  exited: 'bg-red-500',
  stopped: 'bg-red-500',
  paused: 'bg-yellow-500',
  restarting: 'bg-yellow-400 animate-pulse',
}

interface Group {
  key: string
  stack: string | null
  containers: Container[]
  alerts: number
}

function parseStack(name: string): { stack: string | null; service: string } {
  const parts = name.split('-')
  const last = parts[parts.length - 1]
  const trimmed = /^\d+$/.test(last) ? parts.slice(0, -1) : parts
  if (trimmed.length >= 2) {
    return {
      stack: trimmed.slice(0, -1).join('-'),
      service: trimmed[trimmed.length - 1],
    }
  }
  return { stack: null, service: name }
}

function buildGroups(containers: Container[], openFindings: (n: string) => number): Group[] {
  const map = new Map<string, Group>()

  for (const c of containers) {
    const { stack } = parseStack(c.name)
    const key = stack ?? `__standalone__${c.name}`
    if (!map.has(key)) map.set(key, { key, stack, containers: [], alerts: 0 })
    const g = map.get(key)!
    g.containers.push(c)
    g.alerts += openFindings(c.name)
  }

  for (const g of map.values()) {
    g.containers.sort((a, b) => {
      const diff = openFindings(b.name) - openFindings(a.name)
      return diff !== 0 ? diff : a.name.localeCompare(b.name)
    })
  }

  return [...map.values()].sort((a, b) => {
    if (b.alerts !== a.alerts) return b.alerts - a.alerts
    return (a.stack ?? 'zzz').localeCompare(b.stack ?? 'zzz')
  })
}

export function ContainerGrid() {
  const containers = useStore((s) => s.containers)
  const selected = useStore((s) => s.selectedContainer)
  const setSelected = useStore((s) => s.setSelectedContainer)
  const findings = useStore((s) => s.findings)
  const sidebarFilter = useStore((s) => s.sidebarFilter)
  const setSidebarFilter = useStore((s) => s.setSidebarFilter)

  const openFindings = (name: string) =>
    findings.filter((f) => f.container_name === name && f.status === 'open').length

  const allGroups = buildGroups(containers, openFindings)
  const groups = sidebarFilter === 'unhealthy'
    ? allGroups
        .map((g) => ({ ...g, containers: g.containers.filter((c) => openFindings(c.name) > 0) }))
        .filter((g) => g.containers.length > 0)
    : allGroups

  // Track which stacks are expanded. Stacks with alerts auto-expand (unless user
  // has explicitly collapsed them). Stacks without alerts are collapsed by default.
  const [userExpanded, setUserExpanded] = useState<Set<string>>(new Set())
  const [userCollapsed, setUserCollapsed] = useState<Set<string>>(new Set())

  // Auto-expand stacks that gain alerts
  useEffect(() => {
    const keysWithAlerts = allGroups.filter((g) => g.alerts > 0).map((g) => g.key)
    if (keysWithAlerts.length === 0) return
    setUserCollapsed((prev) => {
      // Remove any newly-alerted stack from the collapsed set so auto-expand kicks in
      const next = new Set(prev)
      let changed = false
      for (const k of keysWithAlerts) {
        if (next.has(k)) { next.delete(k); changed = true }
      }
      return changed ? next : prev
    })
  }, [allGroups.map((g) => `${g.key}:${g.alerts}`).join('|')])

  const isExpanded = (key: string, alerts: number) => {
    if (userCollapsed.has(key)) return false
    if (alerts > 0) return true
    return userExpanded.has(key)
  }

  const toggleStack = (key: string, alerts: number) => {
    if (isExpanded(key, alerts)) {
      setUserCollapsed((p) => new Set(p).add(key))
      setUserExpanded((p) => { const s = new Set(p); s.delete(key); return s })
    } else {
      setUserExpanded((p) => new Set(p).add(key))
      setUserCollapsed((p) => { const s = new Set(p); s.delete(key); return s })
    }
  }

  return (
    <aside className="flex flex-col overflow-y-auto h-full">
      {/* Top filter buttons */}
      <div className="flex flex-col gap-0.5 p-2 pb-1">
        {(
          [
            { id: 'all', label: 'All containers' },
            { id: 'unhealthy', label: 'Unhealthy only' },
          ] as const
        ).map(({ id, label }) => (
          <button
            key={id}
            onClick={() => {
              setSidebarFilter(id)
              setSelected(null)
            }}
            className={`text-left px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              sidebarFilter === id
                ? 'bg-gray-700 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            {label}
            {id === 'unhealthy' && (() => {
              const n = allGroups.reduce((s, g) => s + g.alerts, 0)
              return n > 0 ? (
                <span className="ml-1.5 bg-red-600 text-white text-xs rounded-full px-1.5 py-0 leading-none">
                  {n}
                </span>
              ) : null
            })()}
          </button>
        ))}
      </div>

      <div className="border-t border-gray-800 mx-2 mb-1" />

      {/* Container list */}
      <div className="flex flex-col gap-0.5 px-2 pb-2">
        {containers.length === 0 && (
          <p className="text-xs text-gray-600 px-2 mt-2">Waiting for Docker...</p>
        )}

        {groups.map((group) => {
          const expanded = isExpanded(group.key, group.alerts)

          return (
            <div key={group.key} className="mb-0.5">
              {/* Stack header (clickable to expand/collapse) */}
              {group.stack ? (
                <button
                  onClick={() => toggleStack(group.key, group.alerts)}
                  className="w-full flex items-center gap-1.5 px-2 py-1 rounded hover:bg-gray-900 transition-colors group"
                >
                  <span className={`text-gray-600 text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>
                    ▶
                  </span>
                  <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider truncate">
                    {group.stack}
                  </span>
                  {group.alerts > 0 && (
                    <span className="ml-auto shrink-0 text-xs text-red-400 font-semibold">
                      {group.alerts}
                    </span>
                  )}
                </button>
              ) : null}

              {/* Container rows */}
              {(expanded || !group.stack) && (
                <div className={group.stack ? 'pl-3' : ''}>
                  {group.containers.map((c) => {
                    const alerts = openFindings(c.name)
                    const isSelected = selected === c.name
                    const dot = STATUS_DOT[c.status] ?? 'bg-gray-500'
                    const label = group.stack ? parseStack(c.name).service : c.name

                    return (
                      <button
                        key={c.id}
                        onClick={() => setSelected(isSelected ? null : c.name)}
                        className={`w-full text-left px-2 py-1.5 rounded transition-colors ${
                          isSelected
                            ? 'bg-gray-700 text-white'
                            : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className={`shrink-0 w-2 h-2 rounded-full ${dot}`} />
                          <span className="truncate text-xs font-mono">{label}</span>
                          {alerts > 0 && (
                            <span className="ml-auto shrink-0 text-xs bg-red-600 text-white rounded-full px-1.5 py-0.5 leading-none">
                              {alerts}
                            </span>
                          )}
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
