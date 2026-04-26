import { useState } from 'react'
import { useStore, Finding, ProposedAction } from '../store'

function ActionButton({ action, planId, actionIndex }: {
  action: ProposedAction
  planId: string
  actionIndex: number
}) {
  const key = `${planId}:${actionIndex}`
  const update = useStore((s) => s.actionUpdates[key])
  const [confirming, setConfirming] = useState(false)

  const status = update?.status

  async function execute() {
    setConfirming(false)
    await fetch(`/api/plans/${planId}/actions/${actionIndex}/execute`, { method: 'POST' })
  }

  if (status === 'executing') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-800 rounded text-sm text-yellow-400 animate-pulse">
        <span className="w-2 h-2 rounded-full bg-yellow-400" />
        Executing...
      </div>
    )
  }

  if (status === 'done') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-green-950 border border-green-800 rounded text-sm text-green-400">
        <span>✓</span>
        <span>{action.label}</span>
        {update?.output && (
          <details className="ml-auto">
            <summary className="text-xs text-gray-500 cursor-pointer">output</summary>
            <pre className="text-xs text-gray-400 mt-1 whitespace-pre-wrap">{update.output}</pre>
          </details>
        )}
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="px-3 py-2 bg-red-950 border border-red-800 rounded text-sm text-red-400">
        <span>✗ {action.label} — failed</span>
        {update?.output && <pre className="text-xs text-gray-400 mt-1 whitespace-pre-wrap">{update.output}</pre>}
      </div>
    )
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-800 border border-gray-600 rounded text-sm">
        <span className="text-gray-300 flex-1">
          {action.action_type === 'docker_restart'
            ? `Restart container "${action.container_name}"?`
            : `Run "${action.command}" in "${action.container_name}"?`}
        </span>
        <button
          onClick={execute}
          className="px-2 py-1 bg-red-700 hover:bg-red-600 text-white rounded text-xs"
        >
          Confirm
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs"
        >
          Cancel
        </button>
      </div>
    )
  }

  const icon = action.action_type === 'docker_restart' ? '↻' : '▶'

  return (
    <button
      onClick={() => setConfirming(true)}
      className="w-full flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-gray-600 rounded text-sm text-gray-200 transition-colors"
    >
      <span className="text-blue-400">{icon}</span>
      <span>{action.label}</span>
      <span className="ml-auto text-xs text-gray-500">{action.container_name}</span>
    </button>
  )
}

function PlanDetail({ finding }: { finding: Finding }) {
  const plan = finding.plan

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
            finding.severity === 'CRITICAL' ? 'bg-red-600 text-white' :
            finding.severity === 'ERROR' ? 'bg-red-700 text-red-100' :
            finding.severity === 'WARNING' ? 'bg-yellow-700 text-yellow-100' :
            'bg-gray-700 text-gray-200'
          }`}>
            {finding.severity}
          </span>
          <span className="text-xs text-gray-500 font-mono">{finding.container_name}</span>
        </div>
        <p className="text-sm text-gray-200">{finding.summary}</p>
        {finding.root_cause && (
          <p className="text-xs text-gray-500 mt-1">Hypothesis: {finding.root_cause}</p>
        )}
      </div>

      {!plan && (
        <div className="text-xs text-gray-500 animate-pulse">Generating diagnostic plan...</div>
      )}

      {plan && (
        <>
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Diagnostic Steps
            </h3>
            <ol className="space-y-2">
              {plan.steps.map((step, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="shrink-0 text-gray-600 font-mono">{i + 1}.</span>
                  <div>
                    <div className="text-gray-300 font-medium">{step.step}</div>
                    {step.description && (
                      <div className="text-gray-500 text-xs">{step.description}</div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {plan.proposed_actions.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Proposed Actions
              </h3>
              <div className="space-y-2">
                {plan.proposed_actions.map((action, i) => (
                  <ActionButton
                    key={i}
                    action={action}
                    planId={plan.id}
                    actionIndex={i}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <details>
        <summary className="text-xs text-gray-600 cursor-pointer hover:text-gray-400">
          Raw log excerpt
        </summary>
        <pre className="text-xs text-gray-500 mt-2 whitespace-pre-wrap overflow-x-auto font-mono bg-gray-900 p-2 rounded max-h-40 overflow-y-auto">
          {finding.raw_logs}
        </pre>
      </details>
    </div>
  )
}

export function PlanView() {
  const activeFindingId = useStore((s) => s.activeFindingId)
  const findings = useStore((s) => s.findings)
  const setActive = useStore((s) => s.setActiveFinding)

  const finding = findings.find((f) => f.id === activeFindingId)

  if (!finding) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm p-4 text-center">
        Select a finding to see the diagnostic plan
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Plan</h2>
        <button
          onClick={() => setActive(null)}
          className="text-gray-600 hover:text-gray-400 text-lg leading-none"
        >
          ×
        </button>
      </div>
      <PlanDetail finding={finding} />
    </div>
  )
}
