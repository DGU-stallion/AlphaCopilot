/**
 * ChatMessage（ROUND3 C5）—— agent 栏的单条消息渲染。
 *
 * 输入是 `api.ts` 的 SessionMessage 三件套：role / content / meta。
 * 铺开为：
 *   · content          → react-markdown + remark-gfm（与 MyReports 同一个引擎，
 *                        避免两套 markdown 渲染出不一致的结果）
 *   · meta.thinking    → <details> 折叠块，默认收起，标题「思考过程（N 字）」
 *   · meta.tool_calls  → <details> 折叠块，每条：工具名 + 参数 + 结果摘要
 *
 * 安全面：**禁止 dangerouslySetInnerHTML**。react-markdown 默认不渲染裸 HTML；
 * 链接再过一道 MD_COMPONENTS.a，非 http(s) 协议（javascript:/data:）降级成纯文本。
 * 颜色全部来自 usePalette()（ADR-0014 单一真源），不出现 hex 字面量。
 */
import {
  useEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from "react";
import { FONT, SIZE } from "@/theme/tokens";
import { usePalette } from "@/theme/usePalette";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { SessionMessage } from "@/lib/api";

// ---------------------------------------------------------------- props 契约

export interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  meta?: SessionMessage["meta"];
  /** 流式中（显示光标 / 未完成态） */
  streaming?: boolean;
}

type Palette = ReturnType<typeof usePalette>;

/** 工具结果只显示摘要，超过这个长度截断（agent 回参动辄几百行 JSON）。 */
const RESULT_SUMMARY_MAX = 400;

/**
 * markdown → 组件映射。
 *
 * 为什么用 **react-markdown + remark-gfm** 而不是手写解析器（ROUND3 C5 的决定）：
 * 仓库里本来就有它（`MyReports.tsx` 也在用）。C-render 那一版手写了解析器，
 * 但它不支持嵌套列表/引用/斜体/删除线 —— 两套引擎并存的结果一定是
 * 「同一个回答在研报页和对话页长得不一样」，而这种不一致没人会去修。
 * 所以只保留**一个** markdown 引擎，把 ChatMessage 独有的东西（思考过程/
 * 工具调用/复制按钮）作为组件映射叠上来。
 *
 * 不用 dangerouslySetInnerHTML：react-markdown 默认不渲染裸 HTML，XSS 面最小。
 */
const MD_COMPONENTS = {
  code({ className, children }: { className?: string; children?: ReactNode }) {
    const raw = String(children ?? "");
    // 行内代码：没有 language-xxx 类名且不含换行
    const m = /language-(\w+)/.exec(className ?? "");
    if (!m && !raw.includes("\n")) {
      return <InlineCode>{raw}</InlineCode>;
    }
    return <MarkdownCodeBlock code={raw.replace(/\n$/, "")} lang={m?.[1] ?? ""} />;
  },
  table({ children }: { children?: ReactNode }) {
    // 表格要能横向滚动：窄浮窗里宽表会撑破气泡（实测过）
    return (
      <div data-table-scroll="true" style={{ overflowX: "auto", margin: "4px 0" }}>
        <table style={{ borderCollapse: "collapse", fontSize: SIZE.xs }}>{children}</table>
      </div>
    );
  },
  a({ href, children }: { href?: string; children?: ReactNode }) {
    // 只放行 http(s)：javascript:/data: 一律降级成纯文本（与手写版同一纪律）
    if (!href || !/^https?:\/\//i.test(href)) return <span>{children}</span>;
    return <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>;
  },
};

/** 行内代码：等宽 + 淡底。 */
function InlineCode({ children }: { children?: ReactNode }) {
  const pal = usePalette();
  return (
    <code
      style={{
        fontFamily: FONT.mono,
        fontSize: SIZE.xs,
        padding: "0 3px",
        borderRadius: 2,
        backgroundColor: pal.raised,
        border: `1px solid ${pal.border}`,
      }}
    >
      {children}
    </code>
  );
}

/**
 * 代码块：react-markdown 的 `code` 组件拿不到 `palette`（组件映射是模块级常量，
 * 拿不到 hook），所以这里单独包一层组件去取。
 */
function MarkdownCodeBlock({ code, lang }: { code: string; lang: string }) {
  const pal = usePalette();
  return <CodeBlock code={code} lang={lang} pal={pal} />;
}

// ---------------------------------------------------------------- 行内

function CodeBlock({
  code,
  lang,
  pal,
}: {
  code: string;
  lang: string;
  pal: Palette;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  const copy = () => {
    try {
      const done = navigator.clipboard?.writeText(code);
      if (done && typeof done.catch === "function") {
        done
          .then(() => {
            setCopied(true);
            timer.current = window.setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => undefined); // 失败静默：无权限 / 无 clipboard 属正常场景
      }
    } catch {
      // 某些环境 navigator.clipboard 直接 getter throw —— 吃掉
    }
  };

  return (
    <div
      className="relative rounded"
      style={{
        backgroundColor: "var(--ac-bg, transparent)",
        border: `1px solid ${pal.border}`,
      }}
    >
      <div
        className="flex items-center justify-between px-2"
        style={{ borderBottom: `1px solid ${pal.border}`, height: 26 }}
      >
        <span style={{ color: pal.textTertiary, fontSize: SIZE.xs }}>
          {lang || "text"}
        </span>
        <button
          type="button"
          onClick={copy}
          className="cursor-pointer"
          style={{
            color: copied ? pal.success : pal.textSecondary,
            fontSize: SIZE.xs,
            background: "none",
            border: "none",
          }}
          aria-label={`复制代码块${copied ? "（已复制）" : ""}`}
        >
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre
        className="overflow-x-auto px-2 py-1"
        style={{ margin: 0, fontSize: SIZE.xs, lineHeight: 1.5 }}
      >
        <code style={{ fontFamily: FONT.mono }}>{code}</code>
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------- 块级

// ---------------------------------------------------------------- 折叠块

function Collapsible({
  title,
  children,
  pal,
}: {
  title: string;
  children: ReactNode;
  pal: Palette;
}) {
  return (
    <details
      className="rounded"
      style={{
        border: `1px solid ${pal.border}`,
        margin: "4px 0",
        backgroundColor: "var(--ac-bg, transparent)",
      }}
    >
      <summary
        className="cursor-pointer select-none px-2 py-1"
        style={{
          color: pal.textSecondary,
          fontSize: SIZE.xs,
          userSelect: "none",
        }}
      >
        {title}
      </summary>
      <div className="px-2 pb-2">{children}</div>
    </details>
  );
}

// ---------------------------------------------------------------- 主组件

export function ChatMessage({
  role,
  content,
  meta,
  streaming = false,
}: ChatMessageProps): JSX.Element {
  const pal = usePalette();
  const isUser = role === "user";
  const thinking = meta?.thinking;
  const toolCalls = meta?.tool_calls;

  return (
    // data-role / data-streaming 放在**承载对齐的 flex 行**上，而不是外层壳：
    // 外层壳没有 justifyContent，把语义挂在它上面会让「靠左/靠右」这个契约
    // 在测试和调试工具里都看不见（测试曾因此误判成没实现）。
    <div
      data-role={role}
      data-streaming={streaming ? "true" : undefined}
      className="flex gap-2"
      style={{ justifyContent: isUser ? "flex-end" : "flex-start" }}
    >
      {/* 消息气泡：整列左/右对齐，气泡占满本列宽 */}
      <div
        data-bubble="true"
        className="min-w-0 flex-1 rounded p-2 max-w-full"
        style={{
          backgroundColor: pal.raised,
          border: `1px solid ${pal.border}`,
          flexGrow: 1,
        }}
      >
        {/* 思考过程：折叠、总在最前 */}
        {thinking ? (
          <Collapsible title={`思考过程（${thinking.length} 字）`} pal={pal}>
            <p
              className="whitespace-pre-wrap break-words"
              style={{
                color: pal.textSecondary,
                fontSize: SIZE.xs,
                margin: 0,
                lineHeight: 1.6,
              }}
            >
              {thinking}
            </p>
          </Collapsible>
        ) : null}

        {content ? (
          <div
            data-md="true"
            className="prose prose-sm dark:prose-invert max-w-none break-words"
            style={{ color: pal.text, fontSize: SIZE.sm }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
              {content}
            </ReactMarkdown>
          </div>
        ) : null}

        {streaming ? (
          content.length === 0 ? (
            <p
              data-skeleton="true"
              style={{ color: pal.textTertiary, fontSize: SIZE.sm, margin: 0 }}
            >
              …
            </p>
          ) : (
            <span
              data-stream-cursor="true"
              style={{ color: pal.accent, fontSize: SIZE.sm }}
            >
              ▍
            </span>
          )
        ) : null}

        {/* 工具调用：折叠、逐条摘要 */}
        {toolCalls && toolCalls.length > 0 ? (
          <Collapsible title={`工具调用（${toolCalls.length}）`} pal={pal}>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {toolCalls.map((t, i) => (
                <li
                  key={i}
                  style={{
                    padding: "3px 0",
                    borderTop: i > 0 ? `1px solid ${pal.border}` : undefined,
                  }}
                >
                  <strong
                    style={{
                      color: pal.text,
                      fontSize: SIZE.xs,
                      fontFamily: FONT.mono,
                    }}
                  >
                    {t.name}
                  </strong>
                  {t.args ? (
                    <pre
                      className="overflow-x-auto whitespace-pre-wrap break-words"
                      style={{
                        color: pal.textTertiary,
                        fontSize: SIZE.xs,
                        margin: "2px 0 0",
                        fontFamily: FONT.mono,
                      }}
                    >
                      {t.args}
                    </pre>
                  ) : null}
                  {t.result ? (
                    <p
                      className="whitespace-pre-wrap break-words"
                      style={{
                        color: pal.textSecondary,
                        fontSize: SIZE.xs,
                        margin: "2px 0 0",
                        fontFamily: FONT.mono,
                        lineHeight: 1.5,
                      }}
                    >
                      {t.result.length > RESULT_SUMMARY_MAX
                        ? `${t.result.slice(0, RESULT_SUMMARY_MAX)}…`
                        : t.result}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </Collapsible>
        ) : null}
      </div>
    </div>
  );
}
