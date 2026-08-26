import * as React from 'react'

type IndexQuote = { name: string; price: number; change_pct: number }
type GlobalIndex = { name: string; region: string; price: number | null; change_pct: number | null }
type SectorRow = {
  name: string
  pct: number
  net: number
  inflow: number
  outflow: number
  firms: number
}

const MOCK_INDICES: IndexQuote[] = [
  { name: '上证指数', price: 3428.62, change_pct: 0.82 },
  { name: '深证成指', price: 10845.31, change_pct: 1.24 },
  { name: '创业板指', price: 2198.45, change_pct: -0.31 },
  { name: '科创50', price: 892.15, change_pct: 0.45 },
]
const MOCK_GLOBAL: GlobalIndex[] = [
  { name: '纳斯达克', region: '美股', price: 18273.42, change_pct: 0.62 },
  { name: '恒生指数', region: '港股', price: 19842.11, change_pct: -0.18 },
  { name: '日经225', region: '日股', price: 38421.0, change_pct: 0.91 },
]
const MOCK_SECTORS: SectorRow[] = [
  { name: '半导体', pct: 3.21, net: 42.8, inflow: 58.2, outflow: 15.4, firms: 86 },
  { name: '计算机', pct: 2.84, net: 31.5, inflow: 44.1, outflow: 12.6, firms: 124 },
  { name: '电子', pct: 2.12, net: 28.3, inflow: 39.7, outflow: 11.4, firms: 98 },
  { name: '通信', pct: 1.95, net: 19.4, inflow: 27.8, outflow: 8.4, firms: 62 },
  { name: '传媒', pct: 1.42, net: 12.1, inflow: 18.9, outflow: 6.8, firms: 71 },
  { name: '电力设备', pct: 0.82, net: 5.3, inflow: 16.2, outflow: 10.9, firms: 102 },
  { name: '医药生物', pct: -0.21, net: -3.2, inflow: 12.4, outflow: 15.6, firms: 88 },
  { name: '银行', pct: -0.45, net: -8.7, inflow: 9.1, outflow: 17.8, firms: 42 },
  { name: '房地产', pct: -1.12, net: -14.2, inflow: 6.3, outflow: 20.5, firms: 54 },
  { name: '煤炭', pct: -1.84, net: -18.9, inflow: 4.2, outflow: 23.1, firms: 31 },
]

const pctClass = (p: number) => (p > 0 ? 'acp-up' : p < 0 ? 'acp-down' : 'acp-flat')
const fmt = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })

export function DailyReviewPage() {
  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return (
    <div className="acp-daily-review">
      <style>{`
        .acp-daily-review{--acp-up:var(--dsw-static-red-500, #e5484d);--acp-down:var(--dsw-static-green-500, #30a46c);--acp-card-bg:var(--dsw-alias-bg-layer-2, #fff);--acp-border:var(--dsw-alias-border-l2, rgba(0,0,0,0.08));}
        .acp-up{color:var(--acp-up)!important}.acp-down{color:var(--acp-down)!important}.acp-flat{color:var(--dsw-alias-label-secondary)}
        .acp-card{background:var(--acp-card-bg);border:1px solid var(--acp-border);border-radius:16px;box-shadow:var(--dsw-shadow-lv2, 0 1px 3px rgba(0,0,0,0.08));}
      `}</style>

      {/* Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: -0.5,
              color: 'var(--dsw-alias-label-primary)',
              margin: 0,
            }}
          >
            每日复盘
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--dsw-alias-label-secondary)' }}>
            {today} · 大盘 / 情绪 / 板块资金一屏看全
          </p>
        </div>
        <span
          style={{
            fontSize: 11,
            color: 'var(--dsw-alias-label-tertiary)',
            background: 'var(--dsw-alias-bg-layer-1)',
            border: '1px solid var(--acp-border)',
            borderRadius: 20,
            padding: '4px 10px',
          }}
        >
          S4 静态 mock · 接入 REST 后替换为实时数据
        </span>
      </div>

      {/* 1. 大盘指数 + 全球 */}
      <h3
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--dsw-alias-label-secondary)',
          margin: '0 0 8px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span>📈</span> 大盘指数
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--dsw-alias-label-tertiary)' }}>
          · 实时 · 红涨绿跌
        </span>
      </h3>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px,1fr))',
          gap: 10,
          marginBottom: 16,
        }}
      >
        {MOCK_INDICES.map((it) => (
          <div key={it.name} className="acp-card" style={{ padding: 14 }}>
            <div
              style={{
                fontSize: 12,
                color: 'var(--dsw-alias-label-tertiary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {it.name}
            </div>
            <div
              className={pctClass(it.change_pct)}
              style={{
                fontFamily: 'var(--ds-font-family-code, monospace)',
                fontSize: 18,
                fontWeight: 700,
                marginTop: 4,
              }}
            >
              {fmt(it.price)}
            </div>
            <div
              className={pctClass(it.change_pct)}
              style={{ fontFamily: 'monospace', fontSize: 12, marginTop: 2 }}
            >
              {it.change_pct > 0 ? '+' : ''}
              {it.change_pct.toFixed(2)}%
            </div>
          </div>
        ))}
        {MOCK_GLOBAL.map((it) => (
          <div key={it.name} className="acp-card" style={{ padding: 14, opacity: 0.92 }}>
            <div style={{ fontSize: 12, color: 'var(--dsw-alias-label-tertiary)' }}>
              {it.name} <span style={{ fontSize: 10, opacity: 0.6 }}>{it.region}</span>
            </div>
            <div
              className={it.change_pct !== null ? pctClass(it.change_pct) : undefined}
              style={{ fontFamily: 'monospace', fontSize: 18, fontWeight: 700, marginTop: 4 }}
            >
              {it.price !== null ? fmt(it.price) : '—'}
            </div>
            <div
              className={it.change_pct !== null ? pctClass(it.change_pct) : undefined}
              style={{ fontFamily: 'monospace', fontSize: 12, marginTop: 2 }}
            >
              {it.change_pct === null
                ? '—'
                : `${it.change_pct > 0 ? '+' : ''}${it.change_pct.toFixed(2)}%`}
            </div>
          </div>
        ))}
      </div>

      {/* 2. 市场情绪 */}
      <h3
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--dsw-alias-label-secondary)',
          margin: '0 0 8px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span>⚡</span> 市场情绪
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--dsw-alias-label-tertiary)' }}>
          · 2026-08-27
        </span>
      </h3>
      <div className="acp-card" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8 }}>
          {[
            { k: '涨停', v: '42', cls: 'acp-up' },
            { k: '跌停', v: '5', cls: 'acp-down' },
            { k: '最高连板', v: '5 板', cls: '' },
            { k: '连板(2板+)', v: '12 家', cls: '' },
          ].map((c) => (
            <div
              key={c.k}
              style={{
                background: 'var(--dsw-alias-bg-layer-1)',
                borderRadius: 12,
                padding: '12px 8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--dsw-alias-label-tertiary)' }}>{c.k}</div>
              <div
                className={c.cls}
                style={{
                  fontFamily: 'monospace',
                  fontSize: 18,
                  fontWeight: 700,
                  marginTop: 4,
                  color: c.cls ? undefined : 'var(--dsw-alias-label-primary)',
                }}
              >
                {c.v}
              </div>
            </div>
          ))}
        </div>
        <div
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginTop: 10 }}
        >
          {[
            { k: '封板率', v: '82.4%', hint: '封住/尝试涨停' },
            { k: '炸板率', v: '17.6%', hint: '炸板/尝试涨停' },
            { k: '晋级率', v: '38.2%', hint: '昨涨停今又停' },
          ].map((c) => (
            <div
              key={c.k}
              style={{
                background: 'var(--dsw-alias-bg-layer-1)',
                borderRadius: 10,
                padding: '10px 8px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 11, color: 'var(--dsw-alias-label-tertiary)' }}>{c.k}</div>
              <div
                style={{
                  fontFamily: 'monospace',
                  fontSize: 13,
                  fontWeight: 700,
                  marginTop: 4,
                  color: 'var(--dsw-alias-label-primary)',
                }}
              >
                {c.v}
              </div>
              <div style={{ fontSize: 10, color: 'var(--dsw-alias-label-tertiary)', marginTop: 2 }}>
                {c.hint}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 3. 板块资金 */}
      <h3
        style={{
          fontSize: 13,
          fontWeight: 600,
          color: 'var(--dsw-alias-label-secondary)',
          margin: '0 0 8px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <span>💰</span> 板块资金趋势榜
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--dsw-alias-label-tertiary)' }}>
          · 行业 · 按今日净流入排序
        </span>
      </h3>
      <div className="acp-card" style={{ padding: 0, overflow: 'hidden', marginBottom: 16 }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr
                style={{
                  textAlign: 'left',
                  fontSize: 11,
                  color: 'var(--dsw-alias-label-tertiary)',
                  borderBottom: '1px solid var(--acp-border)',
                }}
              >
                {['行业', '涨跌%', '今日净流入', '流入', '流出', '家数'].map((h) => (
                  <th
                    key={h}
                    style={{ whiteSpace: 'nowrap', padding: '10px 12px', fontWeight: 500 }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MOCK_SECTORS.map((s) => (
                <tr
                  key={s.name}
                  style={{ borderBottom: '1px solid var(--dsw-alias-border-l1, rgba(0,0,0,0.04))' }}
                >
                  <td
                    style={{
                      padding: '10px 12px',
                      fontWeight: 500,
                      color: 'var(--dsw-alias-label-primary)',
                    }}
                  >
                    {s.name}
                  </td>
                  <td
                    className={pctClass(s.pct)}
                    style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 12 }}
                  >
                    {s.pct > 0 ? '+' : ''}
                    {s.pct.toFixed(2)}%
                  </td>
                  <td
                    className={pctClass(s.net)}
                    style={{
                      padding: '10px 12px',
                      fontFamily: 'monospace',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {s.net > 0 ? '+' : ''}
                    {fmt(s.net)} 亿
                  </td>
                  <td
                    style={{
                      padding: '10px 12px',
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: 'var(--dsw-alias-label-secondary)',
                    }}
                  >
                    {fmt(s.inflow)}
                  </td>
                  <td
                    style={{
                      padding: '10px 12px',
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: 'var(--dsw-alias-label-secondary)',
                    }}
                  >
                    {fmt(s.outflow)}
                  </td>
                  <td
                    style={{
                      padding: '10px 12px',
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: 'var(--dsw-alias-label-tertiary)',
                    }}
                  >
                    {s.firms}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Disclaimer */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          border: '1px solid var(--dsw-alias-border-l2)',
          background: 'var(--dsw-alias-bg-layer-1)',
          borderRadius: 12,
          padding: 12,
          fontSize: 11,
          lineHeight: 1.6,
          color: 'var(--dsw-alias-label-tertiary)',
          marginTop: 8,
        }}
      >
        <span>ℹ️</span>
        <span>
          AlphaCopilot
          中立呈现客观数据，不荐股、不预测涨跌、不给买卖时机。板块资金为公开净流入统计，非推荐。`每日复盘`
          当前为静态 mock，接入 `dsh-alphacopilot-research` REST 后替换为实时数据。
        </span>
      </div>
    </div>
  )
}
