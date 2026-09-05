/**
 * ai-page-context — Agent 页面感知的**接口约定占位**（S1，ADR-0008）。
 *
 * 第一版不接任何 agent provider。此处只定义「页面向 Agent 暴露上下文」的接口形状，
 * 并提供一个 no-op 的 Provider/consumer，使各业务页现在就能登记自己的确定性数据快照，
 * 将来 S5 接入 agent 时只需把 consumer 换成真实实现（provider 中立：dsh/Codex/Claude CLI 均可）。
 *
 * 约定形状（S5 会消费）：{ key, title, context, suggestions }
 *   key         页面 + 关键参数的稳定标识（换页/换参即变）
 *   title       页面标题
 *   context     当前页面已展示的确定性数据快照（含标的/区间/来源/样本数/关键指标）
 *   suggestions 建议追问（占位期仅存储，不展示）
 */

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

export interface AiPageContextValue {
  key: string;
  title: string;
  context: Record<string, unknown>;
  suggestions?: string[];
}

type Sink = (v: AiPageContextValue | null) => void;

// 占位 sink：仅把最近一次页面上下文存到 ref，供将来 S5 读取；不触发任何 provider。
const AiPageSink = createContext<Sink>(() => {});

/** 全局最近一次页面上下文快照（占位存储，S5 接入 agent 时读取）。 */
export const _lastPageContext: { current: AiPageContextValue | null } = { current: null };

export function AiPageProvider({ children }: { children: ReactNode }) {
  const sink: Sink = (v) => {
    _lastPageContext.current = v;
  };
  return <AiPageSink.Provider value={sink}>{children}</AiPageSink.Provider>;
}

/**
 * useAiPage — 业务页调用以登记当前确定性数据快照。占位期为无副作用的存储。
 * 页面卸载或 key 变更时更新；S5 接 agent 后此 hook 会驱动 provider 的页面感知。
 */
export function useAiPage(value: AiPageContextValue | null): void {
  const sink = useContext(AiPageSink);
  const key = value?.key ?? null;
  const ref = useRef(value);
  ref.current = value;
  useEffect(() => {
    sink(ref.current);
    return () => sink(null);
    // 仅在 key 变化时重登记，避免每次 render 都触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, sink]);
}
