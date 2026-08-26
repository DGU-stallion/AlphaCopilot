/** Host entry for dsh-alphacopilot-chart-plot. */
import type { Context } from '@deepseek-ai/cordis'
import { chartPlotDefinition } from './definition'
import { RENDERER_KEY, RendererComponent } from './renderer'

export const inject = ['slots', 'conversationEvents'] as const

export function apply(ctx: Context): void {
  ctx.conversationEvents.register(chartPlotDefinition)
  ctx.slots.inject('conversation.chat.node', () =>
    ctx.slots.register({ name: 'conversation.chat.node', key: RENDERER_KEY }, RendererComponent),
  )
}
