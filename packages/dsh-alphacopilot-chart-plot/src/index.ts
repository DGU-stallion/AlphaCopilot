/** Host entry for dsh-alphacopilot-chart-plot.

Registers the chart/plot session event family and a keyed ECharts renderer
for the dsh web chat UI.
*/
import type { Context } from '@deepseek-ai/cordis'

export const inject = ['slots', 'conversationEvents'] as const

export function apply(_ctx: Context): void {
  // Host half: no-op in this skeleton. Actual chart rendering lives in the
  // client half (see cordis.patch.yml + separate client build).
}
