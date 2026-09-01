/**
 * TableBlock — 渲染表格 artifact。payload 形状：{columns: string[], rows: (string|number)[][]}。
 * 兼容缺省：无 columns 时用第一行作表头。
 */

interface TablePayload {
  columns?: string[];
  rows?: (string | number)[][];
}

export function TableBlock({ payload, title }: { payload: TablePayload; title?: string }) {
  const rows = payload.rows ?? [];
  const columns = payload.columns ?? (rows.length ? rows[0].map((_, i) => `列${i + 1}`) : []);
  return (
    <div className="glass overflow-x-auto rounded-lg p-3">
      {title && <div className="mb-2 text-sm font-medium text-foreground">{title}</div>}
      <table className="w-full border-collapse text-sm" data-testid="table-block">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} className="border border-border px-2 py-1 text-left text-muted-foreground">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className={ri % 2 ? "bg-muted/20" : ""}>
              {r.map((cell, ci) => (
                <td key={ci} className="border border-border px-2 py-1">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
