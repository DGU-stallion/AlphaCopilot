import { describe, expect, it } from 'vitest'
import { chartPlotDefinition } from '../src/definition'
import type { ChartPlotData } from '../src/events'

function makeEvent(data: ChartPlotData) {
  return { type: 'chart/plot', data }
}

describe('chartPlotDefinition', () => {
  it('matches chart/plot events', () => {
    const data: ChartPlotData = {
      chartId: 'test-1',
      title: 'Test',
      series: [{ code: '600519', name: '茅台', points: [] }],
    }
    const match = chartPlotDefinition.match(makeEvent(data))
    expect(match).not.toBeNull()
    expect(match!.id).toBe('test-1')
    expect(match!.role).toBe('start')
  })

  it('ignores non-chart events', () => {
    expect(chartPlotDefinition.match({ type: 'user/message' })).toBeNull()
  })

  it('returns state in start', () => {
    const data: ChartPlotData = {
      chartId: 'test-2',
      title: 'Title',
      series: [],
    }
    const match = chartPlotDefinition.match(makeEvent(data))!
    const state = chartPlotDefinition.start({} as any, match)
    expect(state.title).toBe('Title')
  })
})
