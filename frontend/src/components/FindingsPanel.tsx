import { useStore, Finding } from '../store'

const SEV_STYLE: Record<string, string> = {
  CRITICAL: 'bg-red-900 border-red-600 text-red-200',
  ERROR: 'bg-red-950 border-red-700 text-red-300',
  WARNING: 'bg-yellow-950 border-yellow-700 text-yellow-300',
  INFO: 'bg-gray-900 border-gray-700 text-gray-300',
}

const SEV_BADGE: Record<string, string> = {
  CRITICAL: 'bg-red-600 text-white',
  ERROR: 'bg-red-700 text-red-100',
  WARNING: 'bg-yellow-700 text-yellow-100',
  INFO: 'bg-gray-700 text-gray-200',
}

function FindingCard({ finding }: { finding: Finding }) {
  const setActive = useStore((s) => s.setActiveFinding)
  const activeFindingId = useStore((s) => s.activeFindingId)
  const isActive = activeFindingId === finding.id

  async function dismiss() {
    await fetch(`/api/findings/${finding.id}/dismiss`, { method: 'POST' })
  }

  return (
    <div
      className={`border rounded p-3 cursor-pointer transition-all ${SEV_STYLE[finding.severity] ?? SEV_STYLE.INFO} ${
        isActive ? 'ring-1 ring-blue-500' : 'hover:opacity-90'
      } ${finding.status === 'dismissed' ? 'opacity-40' : ''}`}
      onClick={() => setActive(finding.id)}
    >
      <div className="flex items-start gap-2 mb-1">
        <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${SEV_BADGE[finding.severity]}`}>
          {finding.severity}
        </span>
        <span className="text-xs text-gray-500 font-mono">{finding.container_name}</span>
        <span className="text-xs text-gray-600 ml-auto shrink-0">
          {new Date(finding.detected_at).toLocaleTimeString()}
        </span>
      </div>
      <p className="text-sm leading-snug">{finding.summary}</p>
      {finding.plan && (
        <p className="text-xs text-blue-400 mt-1">Plan available — {finding.plan.proposed_actions.length} action(s)</p>
      )}
      {finding.status === 'open' && (
        <button
          onClick={(e) => { e.stopPropagation(); dismiss() }}
          className="text-xs text-gray-500 hover:text-gray-300 mt-2"
        >
          Dismiss
        </button>
      )}
    </div>
  )
}

export function FindingsPanel() {
  const findings = useStore((s) => s.findings)
  const selected = useStore((s) => s.selectedContainer)
  const visible = selected
    ? findings.filter((f) => f.container_name === selected)
    : findings

  if (visible.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        No findings yet
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-3 space-y-2">
      {visible.map((f) => (
        <FindingCard key={f.id} finding={f} />
      ))}
    </div>
  )
}
