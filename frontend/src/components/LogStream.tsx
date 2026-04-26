import { useEffect, useRef } from 'react'
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

export function LogStream() {
  const logs = useStore((s) => s.logs)
  const selected = useStore((s) => s.selectedContainer)
  const bottomRef = useRef<HTMLDivElement>(null)
  const autoScroll = useRef(true)
  const containerRef = useRef<HTMLDivElement>(null)

  const visible = selected ? logs.filter((l) => l.container === selected) : logs

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

  if (visible.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm font-mono">
        No log lines yet...
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className="h-full overflow-y-auto font-mono text-xs leading-5 p-2 space-y-0.5"
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
  )
}
