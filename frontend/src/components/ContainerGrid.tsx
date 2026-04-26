import { useStore } from '../store'

const STATUS_DOT: Record<string, string> = {
  running: 'bg-green-500',
  exited: 'bg-red-500',
  stopped: 'bg-red-500',
  paused: 'bg-yellow-500',
  restarting: 'bg-yellow-400 animate-pulse',
}

export function ContainerGrid() {
  const containers = useStore((s) => s.containers)
  const selected = useStore((s) => s.selectedContainer)
  const setSelected = useStore((s) => s.setSelectedContainer)
  const findings = useStore((s) => s.findings)

  const openFindings = (name: string) =>
    findings.filter((f) => f.container_name === name && f.status === 'open').length

  return (
    <aside className="flex flex-col gap-1 p-2 overflow-y-auto">
      <button
        onClick={() => setSelected(null)}
        className={`text-left px-3 py-2 rounded text-xs font-mono transition-colors ${
          selected === null
            ? 'bg-gray-700 text-white'
            : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
        }`}
      >
        All containers
      </button>
      {containers.length === 0 && (
        <p className="text-xs text-gray-600 px-3 mt-2">Waiting for Docker...</p>
      )}
      {containers.map((c) => {
        const dot = STATUS_DOT[c.status] ?? 'bg-gray-500'
        const alerts = openFindings(c.name)
        const isSelected = selected === c.name
        return (
          <button
            key={c.id}
            onClick={() => setSelected(isSelected ? null : c.name)}
            className={`text-left px-3 py-2 rounded transition-colors group ${
              isSelected
                ? 'bg-gray-700 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className={`shrink-0 w-2 h-2 rounded-full ${dot}`} />
              <span className="truncate text-xs font-mono">{c.name}</span>
              {alerts > 0 && (
                <span className="ml-auto shrink-0 text-xs bg-red-600 text-white rounded-full px-1.5 py-0.5 leading-none">
                  {alerts}
                </span>
              )}
            </div>
            <div className="text-xs text-gray-600 truncate pl-4 mt-0.5">{c.image}</div>
          </button>
        )
      })}
    </aside>
  )
}
