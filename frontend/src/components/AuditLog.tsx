import { useStore } from '../store'

const EVENT_ICON: Record<string, string> = {
  finding_detected: '🔍',
  finding_dismissed: '✓',
  action_executed: '▶',
}

const RESULT_COLOR: Record<string, string> = {
  done: 'text-green-400',
  failed: 'text-red-400',
}

export function AuditLog() {
  const entries = useStore((s) => s.auditLog)

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        No audit entries yet
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto font-mono text-xs p-3 space-y-px">
      {entries.map((entry) => (
        <div key={entry.id} className="flex gap-3 items-start py-1.5 border-b border-gray-900">
          <span className="shrink-0 text-gray-600 w-20">
            {new Date(entry.timestamp).toLocaleTimeString('en', { hour12: false })}
          </span>
          <span className="shrink-0 w-4">{EVENT_ICON[entry.event_type] ?? '•'}</span>
          {entry.container_name && (
            <span className="shrink-0 text-gray-500 w-28 truncate">{entry.container_name}</span>
          )}
          <span className="text-gray-300 flex-1 truncate">
            {entry.action ?? entry.details ?? entry.event_type}
          </span>
          {entry.result && (
            <span className={`shrink-0 ${RESULT_COLOR[entry.result] ?? 'text-gray-400'}`}>
              {entry.result}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
