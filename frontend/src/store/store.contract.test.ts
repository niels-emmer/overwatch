import { describe, expect, it } from 'vitest'

import { useStore } from './index'

describe('store ai health state', () => {
  it('updates aiDegraded flag', () => {
    useStore.getState().setAiDegraded(true)
    expect(useStore.getState().aiDegraded).toBe(true)

    useStore.getState().setAiDegraded(false)
    expect(useStore.getState().aiDegraded).toBe(false)
  })
})
