import { useEffect, useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useStore } from './store'
import { ContainerGrid } from './components/ContainerGrid'
import { LogStream } from './components/LogStream'
import { FindingsPanel } from './components/FindingsPanel'
import { PlanView } from './components/PlanView'
import { AuditLog } from './components/AuditLog'

function StatusBar() {
  const wsConnected = useStore((s) => s.wsConnected)
  const aiDegraded = useStore((s) => s.aiDegraded)
  const containers = useStore((s) => s.containers)
  const serverUptimeSeconds = useStore((s) => s.serverUptimeSeconds)
  const riskSnapshots = useStore((s) => s.riskSnapshots)
  const riskThreshold = useStore((s) => s.riskThreshold)
  const findings = useStore((s) => s.findings)
  const openCount = findings.filter((f) => f.status === 'open').length
  const atRiskCount = riskSnapshots.filter((r) => (r.risk_score ?? 0) >= riskThreshold).length
  const [profile, setProfile] = useState('recommendation_only')

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((cfg) => {
        const next = String(cfg?.auto_remediation_profile ?? 'recommendation_only')
        setProfile(next)
      })
      .catch(() => {})
  }, [])

  async function onProfileChange(next: string) {
    setProfile(next)
    try {
      await fetch('/api/policy-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template: next }),
      })
    } catch {
      // keep optimistic selection; backend state will refresh on next load
    }
  }

  function formatUptime(seconds: number | null): string {
    if (seconds === null || Number.isNaN(seconds)) return '--'
    const total = Math.max(0, Math.floor(seconds))
    const h = Math.floor(total / 3600)
    const m = Math.floor((total % 3600) / 60)
    const s = total % 60
    if (h > 0) return `${h}h ${m}m ${s}s`
    if (m > 0) return `${m}m ${s}s`
    return `${s}s`
  }

  return (
    <header className="flex items-center gap-4 px-4 py-2 bg-gray-900 border-b border-gray-800 shrink-0">
      <span className="text-sm font-semibold tracking-widest text-gray-200 uppercase">
        Overwatch
      </span>
      <span className={`text-xs px-2 py-0.5 rounded-full ${wsConnected ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'}`}>
        {wsConnected ? 'live' : 'connecting...'}
      </span>
      <span className={`text-xs px-2 py-0.5 rounded-full ${aiDegraded ? 'bg-yellow-900 text-yellow-400' : 'bg-gray-800 text-gray-400'}`}>
        {aiDegraded ? 'ai degraded' : 'ai healthy'}
      </span>
      <div className="ml-auto flex items-center gap-2">
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">
          {containers.length} container{containers.length !== 1 ? 's' : ''}
        </span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">
          uptime {formatUptime(serverUptimeSeconds)}
        </span>
        <label className="text-xs text-gray-500 flex items-center gap-1">
          policy
          <select
            value={profile}
            onChange={(e) => onProfileChange(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-1 py-0.5 text-gray-300"
          >
            <option value="recommendation_only">recommendation-only</option>
            <option value="conservative">conservative</option>
            <option value="default">default</option>
            <option value="aggressive">aggressive</option>
          </select>
        </label>
        {atRiskCount > 0 && (
          <span className="text-xs bg-yellow-900 text-yellow-300 px-2 py-0.5 rounded-full">
            {atRiskCount} at risk
          </span>
        )}
        {openCount > 0 && (
          <span className="text-xs bg-red-700 text-white px-2 py-0.5 rounded-full">
            {openCount} open finding{openCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </header>
  )
}

type Tab = 'logs' | 'findings' | 'audit'

function TabBar() {
  const activeTab = useStore((s) => s.activeTab)
  const setTab = useStore((s) => s.setActiveTab)
  const findings = useStore((s) => s.findings)
  const openCount = findings.filter((f) => f.status === 'open').length

  const tabs: { id: Tab; label: string; badge?: number }[] = [
    { id: 'logs', label: 'Logs' },
    { id: 'findings', label: 'Findings', badge: openCount || undefined },
    { id: 'audit', label: 'Audit' },
  ]

  return (
    <div className="flex gap-1 px-3 pt-2 pb-0 border-b border-gray-800 shrink-0">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          className={`px-3 py-1.5 text-xs font-medium rounded-t transition-colors relative ${
            activeTab === t.id
              ? 'bg-gray-800 text-white border border-b-transparent border-gray-700'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          {t.label}
          {t.badge !== undefined && (
            <span className="ml-1.5 bg-red-600 text-white text-xs rounded-full px-1 py-0">{t.badge}</span>
          )}
        </button>
      ))}
    </div>
  )
}

export default function App() {
  useWebSocket()
  const activeTab = useStore((s) => s.activeTab)
  const activeFindingId = useStore((s) => s.activeFindingId)

  return (
    <div className="h-full flex flex-col bg-gray-950 text-gray-100">
      <StatusBar />
      <div className="flex flex-1 min-h-0">
        {/* Left sidebar */}
        <div className="w-48 shrink-0 border-r border-gray-800 overflow-hidden flex flex-col bg-gray-950">
          <div className="px-3 pt-3 pb-1 text-xs text-gray-600 uppercase tracking-wider font-semibold">
            Containers
          </div>
          <ContainerGrid />
        </div>

        {/* Center main panel */}
        <div className="flex-1 min-w-0 flex flex-col">
          <TabBar />
          <div className="flex-1 min-h-0">
            {activeTab === 'logs' && <LogStream />}
            {activeTab === 'findings' && <FindingsPanel />}
            {activeTab === 'audit' && <AuditLog />}
          </div>
        </div>

        {/* Right panel — always visible, shows plan or placeholder */}
        <div className={`border-l border-gray-800 flex flex-col transition-all duration-200 ${activeFindingId ? 'w-80' : 'w-56'}`}>
          <div className="px-4 pt-3 pb-1 text-xs text-gray-600 uppercase tracking-wider font-semibold shrink-0">
            Diagnostic Plan
          </div>
          <div className="flex-1 min-h-0">
            <PlanView />
          </div>
        </div>
      </div>
    </div>
  )
}
