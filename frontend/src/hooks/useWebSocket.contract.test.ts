import { describe, expect, it, vi } from 'vitest'

import { applyWsMessage } from './useWebSocket'

function makeStore() {
  return {
    setContainers: vi.fn(),
    addLog: vi.fn(),
    addFinding: vi.fn(),
    setActiveTab: vi.fn(),
    attachPlan: vi.fn(),
    updateFinding: vi.fn(),
    setActionUpdate: vi.fn(),
    addAuditEntry: vi.fn(),
  }
}

describe('applyWsMessage', () => {
  it('handles container_status', () => {
    const store = makeStore()

    applyWsMessage(store, {
      type: 'container_status',
      data: { containers: [{ id: '1', name: 'api', status: 'running', image: 'api:latest' }] },
    })

    expect(store.setContainers).toHaveBeenCalledTimes(1)
  })

  it('routes finding event and activates findings tab', () => {
    const store = makeStore()

    applyWsMessage(store, {
      type: 'finding',
      data: {
        id: 'f1',
        container_name: 'api',
        detected_at: '2026-05-25T00:00:00Z',
        severity: 'ERROR',
        summary: 'Database timeout',
        root_cause: 'Network instability',
        raw_logs: 'ERROR: timeout',
        status: 'open',
      },
    })

    expect(store.addFinding).toHaveBeenCalledTimes(1)
    expect(store.setActiveTab).toHaveBeenCalledWith('findings')
  })

  it('preserves trigger reasons on finding payloads', () => {
    const store = makeStore()

    applyWsMessage(store, {
      type: 'finding',
      data: {
        id: 'f2',
        container_name: 'worker',
        detected_at: '2026-05-25T00:00:00Z',
        severity: 'WARNING',
        summary: 'retry storm',
        root_cause: 'queue delay',
        raw_logs: 'WARN',
        status: 'open',
        anomaly_score: 2.1,
        trigger_reasons: ['rate_spike', 'severity_warning'],
      },
    })

    expect(store.addFinding).toHaveBeenCalledWith(
      expect.objectContaining({
        anomaly_score: 2.1,
        trigger_reasons: ['rate_spike', 'severity_warning'],
      }),
    )
  })

  it('applies clustered finding updates without creating a new finding', () => {
    const store = makeStore()

    applyWsMessage(store, {
      type: 'finding_updated',
      data: {
        id: 'f1',
        occurrence_count: 3,
        last_seen_at: '2026-05-25T20:00:00Z',
      },
    })

    expect(store.updateFinding).toHaveBeenCalledWith('f1', {
      occurrence_count: 3,
      last_seen_at: '2026-05-25T20:00:00Z',
    })
    expect(store.addFinding).not.toHaveBeenCalled()
  })

  it('records completed action updates in audit entries', () => {
    const store = makeStore()
    vi.stubGlobal('crypto', { randomUUID: () => 'audit-id-1' })

    applyWsMessage(store, {
      type: 'action_update',
      data: {
        plan_id: 'p1',
        action_index: 0,
        status: 'done',
        output: 'ok',
        label: 'Restart API',
      },
    })

    expect(store.setActionUpdate).toHaveBeenCalledTimes(1)
    expect(store.addAuditEntry).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('passes action ranking metadata through plan_ready', () => {
    const store = makeStore()

    applyWsMessage(store, {
      type: 'plan_ready',
      data: {
        id: 'p1',
        finding_id: 'f1',
        created_at: '2026-05-25T00:00:00Z',
        steps: [],
        status: 'pending',
        proposed_actions: [
          {
            label: 'Restart API',
            action_type: 'docker_restart',
            command: null,
            container_name: 'api',
            historical_score: 0.82,
            historical_success_rate: 0.86,
            historical_sample_size: 7,
            ranking_reason: '6/7 successful; last seen 1h ago',
          },
        ],
      },
    })

    expect(store.attachPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        proposed_actions: [
          expect.objectContaining({
            historical_score: 0.82,
            historical_success_rate: 0.86,
            historical_sample_size: 7,
            ranking_reason: '6/7 successful; last seen 1h ago',
          }),
        ],
      }),
    )
  })
})
