// AI 助手占位实现（S5 上线）。保留类型与函数签名让引用它的组件能编译，
// 但不真正调用后端 /api/chat 或任何 CLI —— hasLlm() 恒为 false，chatStream/chat 抛错。
// 原实现（loadLlm/saveLlm + 流式 NDJSON + ai-models CLI 探测）在接入 AI 时再恢复。

export type ProviderId =
  | "deepseek" | "silicon" | "openai" | "minimax" | "openrouter" | "groq"
  | "together" | "mimo" | "openai-compatible"
  | "cli-claude" | "cli-qwen" | "cli-deepseek" | "cli-codex"
  | "cli-opencode" | "cli-cursor" | "cli-kimi";

export interface LlmConfig {
  provider: ProviderId;
  baseURL: string;
  apiKey: string;
  model: string;
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResult {
  content: string;
  trace: { tool: string; args: Record<string, unknown> }[];
  rounds: number;
}

export interface ChatHandlers {
  onDelta?: (text: string) => void;
  onTool?: (tool: string, args: Record<string, unknown>) => void;
}

const NOT_READY = "AI 助手即将上线(S5)";

export function staleBlockedProvider(): string | null {
  return null;
}

export function loadLlm(): LlmConfig | null {
  return null;
}

export function saveLlm(_cfg: LlmConfig) {
  /* 占位：AI 接入 S5 上线，暂不保存配置 */
}

export function clearLlm() {
  /* 占位 */
}

export function hasLlm(): boolean {
  return false;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function chatStream(_messages: ChatMsg[], _context: string, _handlers: ChatHandlers = {}, _signal?: AbortSignal): Promise<ChatResult> {
  throw new Error(NOT_READY);
}

export function chat(messages: ChatMsg[], context: string): Promise<ChatResult> {
  return chatStream(messages, context);
}
