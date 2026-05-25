import { useStore } from '../store'
import { useState } from 'react'

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
  const [summary, setSummary] = useState<string>('')

  async function generateSummary() {
    try {
      const resp = await fetch('/api/summary/shift')
      const payload = await resp.json()
      setSummary(String(payload?.markdown ?? ''))
    } catch {
      setSummary('Failed to generate summary')
    }
  }

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        No audit entries yet
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto font-mono text-xs p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-gray-500">Audit Trail</span>
        <button
          onClick={generateSummary}
          className="px-2 py-1 rounded bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700"
        >
          Export Shift Summary
        </button>
      </div>

      {summary && (
        <pre className="whitespace-pre-wrap bg-gray-900 border border-gray-800 rounded p-2 text-gray-300 max-h-56 overflow-y-auto">
          {summary}
        </pre>
      )}

      <div className="space-y-px">
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
    </div>
  )
}
