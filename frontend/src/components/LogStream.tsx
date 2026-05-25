import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'

const LEVEL_COLOR: Record<string, string> = {
  error: 'text-red-400',
  warning: 'text-yellow-400',
  info: 'text-gray-400',
}

const LEVEL_TAG: Record<string, string> = {
  error: 'ERR',
  warning: 'WRN',
  info: 'INF',
}

type LevelFilter = 'all' | 'info' | 'warning' | 'error'

export function LogStream() {
  const logs = useStore((s) => s.logs)
  const selected = useStore((s) => s.selectedContainer)
  const bottomRef = useRef<HTMLDivElement>(null)
  const autoScroll = useRef(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('all')

  const byContainer = selected ? logs.filter((l) => l.container === selected) : logs
  const visible = levelFilter === 'all'
    ? byContainer
    : byContainer.filter((l) => l.level === levelFilter)

  useEffect(() => {
    if (autoScroll.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
    }
  }, [visible.length])

  function onScroll() {
    const el = containerRef.current
    if (!el) return
    autoScroll.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-3 py-2 border-b border-gray-800 flex items-center gap-1">
        {(['all', 'info', 'warning', 'error'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setLevelFilter(f)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
              levelFilter === f
                ? 'bg-gray-700 text-white'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="flex items-center justify-center flex-1 text-gray-600 text-sm font-mono">
          No log lines for selected filter...
        </div>
      ) : (
        <div
          ref={containerRef}
          onScroll={onScroll}
          className="flex-1 overflow-y-auto font-mono text-xs leading-5 p-2 space-y-0.5"
        >
          {visible.map((line, i) => (
            <div key={i} className="flex gap-2 items-start group">
              <span className="shrink-0 text-gray-600 w-12 text-right select-none">
                {new Date(line.ts).toLocaleTimeString('en', { hour12: false })}
              </span>
              {!selected && (
                <span className="shrink-0 text-gray-500 w-24 truncate">{line.container}</span>
              )}
              <span className={`shrink-0 w-7 font-semibold ${LEVEL_COLOR[line.level] ?? 'text-gray-400'}`}>
                {LEVEL_TAG[line.level] ?? 'INF'}
              </span>
              <span className={`break-all whitespace-pre-wrap ${LEVEL_COLOR[line.level] ?? 'text-gray-300'}`}>
                {line.text}
              </span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
