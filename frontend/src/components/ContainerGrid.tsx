import { useStore, Container } from '../store'

const STATUS_DOT: Record<string, string> = {
  running: 'bg-green-500',
  exited: 'bg-red-500',
  stopped: 'bg-red-500',
  paused: 'bg-yellow-500',
  restarting: 'bg-yellow-400 animate-pulse',
}

interface Grouped {
  stack: string | null   // null = standalone
  containers: Container[]
  alerts: number
}

function parseStack(name: string): { stack: string | null; service: string } {
  const parts = name.split('-')
  // Strip trailing replica number (e.g. "-1")
  const last = parts[parts.length - 1]
  const trimmed = /^\d+$/.test(last) ? parts.slice(0, -1) : parts
  if (trimmed.length >= 2) {
    const service = trimmed[trimmed.length - 1]
    const stack = trimmed.slice(0, -1).join('-')
    return { stack, service }
  }
  return { stack: null, service: name }
}

function groupAndSort(
  containers: Container[],
  openFindings: (name: string) => number,
): Grouped[] {
  const map = new Map<string, Grouped>()

  for (const c of containers) {
    const { stack } = parseStack(c.name)
    const key = stack ?? `__standalone__${c.name}`
    if (!map.has(key)) {
      map.set(key, { stack, containers: [], alerts: 0 })
    }
    const group = map.get(key)!
    group.containers.push(c)
    group.alerts += openFindings(c.name)
  }

  for (const group of map.values()) {
    group.containers.sort((a, b) => {
      const da = openFindings(a.name)
      const db = openFindings(b.name)
      if (db !== da) return db - da  // findings first
      return a.name.localeCompare(b.name)
    })
  }

  return [...map.values()].sort((a, b) => {
    // Stacks with findings first
    if (b.alerts !== a.alerts) return b.alerts - a.alerts
    // Standalones after named stacks
    const aKey = a.stack ?? 'zzz'
    const bKey = b.stack ?? 'zzz'
    return aKey.localeCompare(bKey)
  })
}

function ContainerButton({ c, alerts }: { c: Container; alerts: number }) {
  const selected = useStore((s) => s.selectedContainer)
  const setSelected = useStore((s) => s.setSelectedContainer)
  const isSelected = selected === c.name
  const dot = STATUS_DOT[c.status] ?? 'bg-gray-500'

  return (
    <button
      onClick={() => setSelected(isSelected ? null : c.name)}
      className={`w-full text-left px-2 py-1.5 rounded transition-colors ${
        isSelected
          ? 'bg-gray-700 text-white'
          : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className={`shrink-0 w-2 h-2 rounded-full ${dot}`} />
        <span className="truncate text-xs font-mono">{parseStack(c.name).service}</span>
        {alerts > 0 && (
          <span className="ml-auto shrink-0 text-xs bg-red-600 text-white rounded-full px-1.5 py-0.5 leading-none">
            {alerts}
          </span>
        )}
      </div>
    </button>
  )
}

export function ContainerGrid() {
  const containers = useStore((s) => s.containers)
  const selected = useStore((s) => s.selectedContainer)
  const setSelected = useStore((s) => s.setSelectedContainer)
  const findings = useStore((s) => s.findings)

  const openFindings = (name: string) =>
    findings.filter((f) => f.container_name === name && f.status === 'open').length

  const groups = groupAndSort(containers, openFindings)

  return (
    <aside className="flex flex-col gap-0.5 p-2 overflow-y-auto">
      <button
        onClick={() => setSelected(null)}
        className={`text-left px-3 py-2 rounded text-xs font-mono transition-colors mb-1 ${
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

      {groups.map((group) => (
        <div key={group.stack ?? group.containers[0]?.name} className="mb-1">
          {group.stack && (
            <div className="flex items-center gap-1.5 px-2 pt-1.5 pb-0.5">
              <span className="text-xs text-gray-600 font-semibold uppercase tracking-wider truncate">
                {group.stack}
              </span>
              {group.alerts > 0 && (
                <span className="shrink-0 text-xs text-red-400 font-semibold">
                  {group.alerts}
                </span>
              )}
            </div>
          )}
          <div className={group.stack ? 'pl-2' : ''}>
            {group.containers.map((c) => (
              <ContainerButton key={c.id} c={c} alerts={openFindings(c.name)} />
            ))}
          </div>
        </div>
      ))}
    </aside>
  )
}
