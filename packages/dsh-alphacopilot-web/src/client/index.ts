import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import * as React from 'react'
import { DailyReviewPage } from './DailyReviewPage.tsx'
import { CustomSidebar, createPageStore } from './Sidebar.tsx'

export const inject = ['slots', 'layout', 'sessions', 'workspaces', 'locale'] as const

export function apply(ctx: ClientContext): void {
  // eslint-disable-next-line no-console
  console.log('[acp-web] apply: registering sidebar + overlay')
  const store = createPageStore('chat')

  // Inject global theme vars once
  ctx.effect(() => {
    const style = document.createElement('style')
    style.dataset.plugin = 'dsh-alphacopilot-web/theme'
    style.textContent = `:root{--acp-up:var(--dsw-static-red-500, #e5484d);--acp-down:var(--dsw-static-green-500, #30a46c);}`
    document.head.appendChild(style)
    return () => {
      style.remove()
    }
  }, 'acp theme vars')

  // Sidebar replacement — shadow original at lower priority (lowest renders)
  // Do not re-declare children (already declared by original sidebar, would collide)
  ctx.slots.inject('sidebar', () => {
    return ctx.slots.register(
      {
        name: 'sidebar',
        priority: -10,
        inject: () => ({
          startSession: () => (ctx as any).workspaces?.startSession?.(),
          toggleSidebar: () => (ctx as any).layout?.toggleSidebar?.(),
        }),
      } as any,
      (props: any) => React.createElement(CustomSidebar, { ...props, pageStore: store }),
    )
  })

  // Center page — shell.overlay covers center column when daily-review active
  ctx.slots.inject('shell.overlay', () => {
    return ctx.slots.register(
      { name: 'shell.overlay', id: 'acp-daily-review', order: 10 } as any,
      () => React.createElement(OverlayPage, { store }),
    )
  })
}

function OverlayPage({ store }: { store: ReturnType<typeof createPageStore> }) {
  const [page, setPage] = React.useState(() => store.get())
  React.useEffect(() => store.subscribe(() => setPage(store.get())), [store])
  if (page !== 'daily-review') return null
  return React.createElement(
    'div',
    {
      style: {
        position: 'absolute',
        inset: 0,
        left: 240,
        background: 'var(--dsw-alias-bg-base, #f6f7f8)',
        overflowY: 'auto',
        pointerEvents: 'auto',
        zIndex: 5,
        borderLeft: '1px solid var(--dsw-alias-border-l1)',
      } as React.CSSProperties,
      onClick: (e: React.MouseEvent) => e.stopPropagation(),
    },
    React.createElement(
      'div',
      { style: { maxWidth: 960, margin: '0 auto', padding: '20px 24px 32px' } },
      React.createElement(
        'div',
        { style: { display: 'flex', justifyContent: 'flex-end', marginBottom: 8 } },
        React.createElement(
          'button',
          {
            type: 'button',
            onClick: () => store.set('chat'),
            style: {
              fontSize: 12,
              padding: '6px 12px',
              borderRadius: 20,
              border: '1px solid var(--dsw-alias-border-l2)',
              background: 'var(--dsw-alias-bg-layer-2)',
              color: 'var(--dsw-alias-label-secondary)',
              cursor: 'pointer',
            },
          },
          '← 返回对话',
        ),
      ),
      React.createElement(DailyReviewPage, null),
    ),
  )
}
