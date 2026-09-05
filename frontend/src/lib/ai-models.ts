// AI 模型/CLI 探测占位（S5 上线）。main.tsx 启动时会调 primeCliAvailability，
// 这里做成 no-op，不请求 /api/cli/available，返回 null 表示"还不知道/未接入"。

export interface CliAvailability {
  clis: { kind: string; allowed: boolean; installed: boolean; reason: string | null }[];
  optInEnv: string;
  optedIn: string[];
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function primeCliAvailability(_headers: Record<string, string> = {}): Promise<CliAvailability | null> {
  return null;
}
