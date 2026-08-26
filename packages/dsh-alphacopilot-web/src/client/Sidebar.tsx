import * as React from 'react'

type PageId = 'chat' | 'daily-review'

export type PageStore = {
  get: () => PageId
  set: (p: PageId) => void
  subscribe: (fn: () => void) => () => void
}

export function createPageStore(initial: PageId = 'chat'): PageStore {
  let page: PageId = initial
  const listeners = new Set<() => void>()
  return {
    get: () => page,
    set: (p) => {
      if (p === page) return
      page = p
      for (const fn of listeners) fn()
    },
    subscribe: (fn) => {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
  }
}

type NavItem = { id: PageId; label: string; icon: string; disabled?: boolean }

const NAV_ITEMS: NavItem[] = [
  { id: 'chat', label: 'Agent 对话', icon: '💬' },
  { id: 'daily-review', label: '每日复盘', icon: '📊' },
]

const FUTURE_ITEMS: NavItem[] = [
  { id: 'chat', label: '板块中心', icon: '🏢', disabled: true },
  { id: 'chat', label: '个股数据', icon: '📈', disabled: true },
  { id: 'chat', label: '自选股', icon: '⭐', disabled: true },
]

type SidebarProps = {
  collapsed: boolean
  width: number
  startSession: () => void
  toggleSidebar: () => void
  t?: (key: string) => string
  renderSlot: (slot: string, props?: any, opts?: any) => React.ReactNode
  pageStore: PageStore
}

export function CustomSidebar({
  collapsed,
  width,
  startSession,
  toggleSidebar,
  t: tProp,
  renderSlot,
  pageStore,
}: SidebarProps) {
  const t = tProp ?? ((k: string) => k)
  const [settled, setSettled] = React.useState(collapsed)
  const [page, setPage] = React.useState<PageId>(() => pageStore.get())

  React.useEffect(() => pageStore.subscribe(() => setPage(pageStore.get())), [pageStore])

  React.useEffect(() => {
    if (!collapsed) {
      setSettled(false)
      return
    }
    const timer = window.setTimeout(() => setSettled(true), 150)
    return () => window.clearTimeout(timer)
  }, [collapsed])

  const wide = !collapsed || !settled
  const lastWideWidth = React.useRef(width)
  if (!collapsed) lastWideWidth.current = width

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--dsw-specific-sidebar-fill, var(--dsw-alias-bg-layer-1))',
        borderRight: '1px solid var(--dsw-alias-border-l1)',
        overflow: 'hidden',
        width: wide ? (collapsed ? lastWideWidth.current : width) : undefined,
      }}
    >
      {/* DEBUG banner — proves custom sidebar rendered */}
      <div style={{ background: '#f97316', color: '#fff', fontSize: 10, textAlign: 'center', padding: '2px 0', flexShrink: 0 }}>ACP WEB ✓</div>
      {/* Logo row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          height: 48,
          padding: '0 10px',
          gap: 8,
          flexShrink: 0,
        }}
      >
        {wide && (
          <button
            type="button"
            onClick={() => startSession()}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              flex: 1,
              minWidth: 0,
            }}
          >
            <span
              style={{
                width: 24,
                height: 24,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {renderSlot('sidebar.brand.mark', { size: 24 }, { fallback: <span>🐟</span> })}
            </span>
            <span
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: 'var(--dsw-alias-label-primary)',
                whiteSpace: 'nowrap',
              }}
            >
              {renderSlot('sidebar.brand.name', {}, { fallback: <span>AlphaCopilot</span> })}
            </span>
          </button>
        )}
        <button
          type="button"
          aria-label={collapsed ? t('toggle.open') : t('toggle.collapse')}
          onClick={() => toggleSidebar()}
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            border: '1px solid var(--dsw-alias-border-l2)',
            background: 'var(--dsw-alias-bg-layer-2)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: 12 }}>{collapsed ? '→' : '←'}</span>
        </button>
      </div>

      {/* New session */}
      <div style={{ padding: '8px 10px', flexShrink: 0 }}>
        <button
          type="button"
          onClick={() => {
            pageStore.set('chat')
            startSession()
          }}
          style={{
            width: '100%',
            height: 36,
            borderRadius: 12,
            border: '1px solid var(--dsw-alias-border-l2)',
            background: 'var(--dsw-alias-bg-layer-2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: wide ? 'flex-start' : 'center',
            gap: 8,
            padding: wide ? '0 12px' : 0,
            cursor: 'pointer',
            fontSize: 13,
            color: 'var(--dsw-alias-label-primary)',
          }}
        >
          <span>＋</span>
          {wide && <span>{t('session.new')}</span>}
        </button>
      </div>

      {/* Nav — first-class pages */}
      <div
        style={{
          padding: '8px 8px 10px',
          borderBottom: '1px solid var(--dsw-alias-border-l1)',
          flexShrink: 0,
        }}
      >
        {!wide ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'center' }}>
            {NAV_ITEMS.map((it) => (
              <button
                key={it.label}
                type="button"
                onClick={() => !it.disabled && pageStore.set(it.id)}
                title={it.label}
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  border: '1px solid transparent',
                  background:
                    page === it.id
                      ? 'var(--dsw-specific-sidebar-nav-item-active, var(--dsw-alias-bg-layer-2))'
                      : 'transparent',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: it.disabled ? 'not-allowed' : 'pointer',
                  opacity: it.disabled ? 0.5 : 1,
                }}
              >
                <span style={{ fontSize: 16 }}>{it.icon}</span>
              </button>
            ))}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {NAV_ITEMS.map((it) => {
              const active = page === it.id
              return (
                <button
                  key={it.label}
                  type="button"
                  onClick={() => !it.disabled && pageStore.set(it.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    width: '100%',
                    height: 36,
                    borderRadius: 10,
                    padding: '0 10px',
                    border: '1px solid transparent',
                    background: active
                      ? 'var(--dsw-specific-sidebar-nav-item-active, var(--dsw-alias-bg-layer-2))'
                      : 'transparent',
                    color: active
                      ? 'var(--dsw-alias-label-primary)'
                      : 'var(--dsw-alias-label-secondary)',
                    cursor: it.disabled ? 'not-allowed' : 'pointer',
                    fontSize: 13,
                    fontWeight: active ? 600 : 400,
                    textAlign: 'left',
                  }}
                >
                  <span style={{ fontSize: 14, width: 18, textAlign: 'center' }}>{it.icon}</span>
                  <span
                    style={{
                      flex: 1,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {it.label}
                  </span>
                  {active && (
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: 6,
                        background: 'var(--dsw-alias-button-info-fill, #4a7cff)',
                        flexShrink: 0,
                      }}
                    />
                  )}
                </button>
              )
            })}
            <div style={{ height: 1, background: 'var(--dsw-alias-border-l1)', margin: '6px 0' }} />
            {FUTURE_ITEMS.map((it) => (
              <div
                key={it.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  height: 32,
                  borderRadius: 10,
                  padding: '0 10px',
                  color: 'var(--dsw-alias-label-tertiary)',
                  fontSize: 13,
                  opacity: 0.6,
                }}
              >
                <span style={{ fontSize: 14, width: 18, textAlign: 'center' }}>{it.icon}</span>
                <span>{it.label}</span>
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: 10,
                    background: 'var(--dsw-alias-bg-layer-1)',
                    border: '1px solid var(--dsw-alias-border-l1)',
                    borderRadius: 20,
                    padding: '1px 6px',
                  }}
                >
                  soon
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Workspaces */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {renderSlot('sidebar.workspaces', {
          wide,
          expandSidebar: () => {
            if (collapsed) toggleSidebar()
          },
        })}
      </div>

      {/* Foot */}
      <div
        style={{
          flexShrink: 0,
          borderTop: '1px solid var(--dsw-alias-border-l1)',
          padding: '8px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        <div style={{ display: 'flex', gap: 6, justifyContent: wide ? 'flex-start' : 'center' }}>
          {renderSlot('sidebar.footer.action', { wide })}
        </div>
        <div>{renderSlot('sidebar.settings', { wide })}</div>
      </div>
    </div>
  )
}
