import { describe, expect, it } from 'vitest'

import { useStore } from './index'

describe('store ai health state', () => {
  it('updates aiDegraded flag', () => {
    useStore.getState().setAiDegraded(true)
    expect(useStore.getState().aiDegraded).toBe(true)

    useStore.getState().setAiDegraded(false)
    expect(useStore.getState().aiDegraded).toBe(false)
  })

  it('stores risk snapshots and threshold', () => {
    useStore.getState().setRiskState(
      [
        {
          container_name: 'api',
          risk_score: 72,
          risk_horizon_minutes: 30,
          reasons: ['baseline_drift'],
        },
      ],
      65,
    )

    expect(useStore.getState().riskThreshold).toBe(65)
    expect(useStore.getState().riskSnapshots).toHaveLength(1)
    expect(useStore.getState().riskSnapshots[0]).toEqual(
      expect.objectContaining({
        container_name: 'api',
        risk_score: 72,
      }),
    )
  })
})
