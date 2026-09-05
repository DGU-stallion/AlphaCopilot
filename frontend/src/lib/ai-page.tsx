/**
 * 「当前这一页要给 AI 看什么」的登记处（页面感知）。
 *
 * 右下角全局浮标由外壳渲染一份、覆盖所有页；页面只**登记**自己的确定性数据快照，
 * 浮标从这里读，显示「当前页面: XXX」并把快照作为将来（S5）对话的上下文。
 *
 * 移植自 Vibe-Research/desktop 的 core/ai/pageContext，按本项目精简。
 */
import {
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export interface AiPage {
  /** 这份快照的归属。换页要换 key，否则将来对话会把上一页历史带进来。 */
  key: string;
  /** 浮标上显示的「当前页面」 */
  title: string;
  /** 本页确定性数据快照，作为将来对话的上下文（现在只展示、不发给 provider） */
  context: string;
  /** 空对话时给几个可点的问题 */
  suggestions?: string[];
}

interface Store {
  page: AiPage | null;
  set: Dispatch<SetStateAction<AiPage | null>>;
}

const Ctx = createContext<Store | null>(null);

export function AiPageProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<AiPage | null>(null);
  const value = useMemo<Store>(() => ({ page, set: setPage }), [page]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** 浮标读当前页快照；Provider 没挂上时返回 null（浮标显示「无可聊内容」）。 */
export function useCurrentAiPage(): AiPage | null {
  return useContext(Ctx)?.page ?? null;
}

/**
 * 页面登记自己的快照。传 `null` = 这一页暂时没什么可聊的。
 *
 * 🔴 依赖按**内容**比、不按对象比：`context` 每次渲染都是新拼的字符串，把对象直接
 *    放进依赖数组会每帧 setState 一次（死循环，表现只是"有点卡"）。
 * 🔴 卸载时**只清掉自己登记的那份**：无条件清空会在"旧页卸载晚于新页挂载"的切页顺序里
 *    把新页刚登记的快照抹掉，表现是换页之后浮标说"这页没有数据"。
 */
export function useAiPage(page: AiPage | null): void {
  const set = useContext(Ctx)?.set;
  const mine = useRef<AiPage | null>(null);

  const has = page !== null;
  const key = page?.key ?? "";
  const title = page?.title ?? "";
  const context = page?.context ?? "";
  // 只为比较用：把建议压成一个字符串，免得数组每次都是新对象
  const sig = page?.suggestions?.join("\u0000") ?? "";

  useEffect(() => {
    if (!set) return;
    const next: AiPage | null = has
      ? { key, title, context, suggestions: sig ? sig.split("\u0000") : [] }
      : null;
    mine.current = next;
    set(next);
    return () => {
      set((prev) => (prev === mine.current ? null : prev));
    };
  }, [set, has, key, title, context, sig]);
}
