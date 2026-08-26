/** Host entry for dsh-alphacopilot-chart-plot.

Registers the chart/plot session event family and a keyed ECharts renderer
for the dsh web chat UI.
*/
import type { Context } from '@deepseek-ai/cordis'
import { chartPlotDefinition } from './definition'

export const inject = ['slots', 'conversationEvents'] as const

export function apply(ctx: Context): void {
  ctx.conversationEvents.register(chartPlotDefinition)
  ctx.slots.inject('conversation.chat.node', () =>
    ctx.slots.register(
      { name: 'conversation.chat.node', key: 'chart.plot' },
      (_props: unknown) => null,
    ),
  )
}
