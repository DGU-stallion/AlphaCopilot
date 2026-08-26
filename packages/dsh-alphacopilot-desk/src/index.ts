/** Desk plugin: registers compliance prompt fragments for dsh agent. */
import type { Context } from '@deepseek-ai/cordis'

export const inject = [] as const

export function apply(_ctx: Context): void {
  // Prompt injection happens via systemPrompt seam in production.
  // This is a stub; full implementation in T16/T17.
}
