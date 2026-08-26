import type { ConversationNodeDefinition, ConversationMatch } from '@deepseek-ai/dsh-client-runtime/client'
import type { ChartPlotData } from './events'

export const chartPlotDefinition: ConversationNodeDefinition<ChartPlotData> = {
  kind: 'chart.plot',
  target: 'chat',
  match(event: { type: string; data?: unknown }): ConversationMatch | null {
    if (event.type === 'chart/plot' && event.data && typeof (event.data as ChartPlotData).chartId === 'string') {
      return { id: String((event.data as ChartPlotData).chartId), role: 'start' }
    }
    return null
  },
  start(_context, match) {
    return match.event.data as ChartPlotData
  },
  update(_context, _match) {
    return _context.state
  },
  buildViewNode(context) {
    if (!context.state) return null
    const state = context.state
    const anchorSeq = context.start?.event.seq ?? 0
    return {
      key: context.key,
      kind: 'chart.plot',
      id: context.id,
      target: 'chat',
      anchorSeq,
      location: context.start?.location ?? { kind: 'step', turn: 0, step: 0, key: 'chart.plot' },
      visibility: 'visible' as const,
      data: { title: state.title, series: state.series },
    }
  },
}
