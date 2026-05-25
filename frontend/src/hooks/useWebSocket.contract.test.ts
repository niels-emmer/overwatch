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
})
