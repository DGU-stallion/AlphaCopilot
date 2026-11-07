/**
 * AgentSessionList（ROUND3 C4）：会话历史列表。
 *
 * 这是「挑会话」的界面，不是展示界面，所以每个决定的判据都是「能不能一眼挑对」：
 *
 *   · 空标题 → 「未命名会话」。空字符串渲染成一行空白，列表看上去像坏了
 *   · 带 `message_count` → 只看标题和时间的话，「聊了 30 轮的」和「误点开一次
 *     空着的」长得一模一样
 *   · 相对时间（3 分钟前）→ 看列表时关心的是「新不新」；一条 40 天前的会话
 *     显示「09-12」比「40 天前」更好定位
 *   · 删除按钮 `stopPropagation` → 点删除却把会话切走，是真实会踩的坑
 *
 * 删除的撤销由调用方实现（硬规则 14：破坏性操作必须可撤销）。本组件只负责
 * 把「删哪一条」报上去，不自己弹确认框 —— 确认框防手滑，防不了「确认完才想错」。
 */
import type { JSX } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { SessionSummary } from "@/lib/api";
import { Num } from "@/components/Num";
import { cn } from "@/lib/utils";
import { usePalette } from "@/theme/usePalette";

export interface AgentSessionListProps {
  sessions: SessionSummary[];
  activeId: string | null;
  onPick: (sid: string) => void;
  /**
   * 列表读取失败的原因。非空时**不要**显示「还没有会话」——
   * 「查不到」和「确实没有」是两件事，混在一起会把一次 404 说成
   * 「你没有历史」（实测踩过：接口路径写错，界面理直气壮地说没有会话，
   * 而库里躺着 17 条）。
   */
  error?: string | null;
  onDelete: (sid: string) => void;
  onNew: () => void;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const pad2 = (n: number) => String(n).padStart(2, "0");

/**
 * 相对时间。`created_at` 是**秒**（后端 `time.time()`，见 store.py）。
 *
 * 超过 7 天就退化成日期：一直往上写「123 天前」，用户还得心算。
 * 跨年才带年份 —— 同年会话带年份只是让每一行更长。
 */
export function relativeTime(sec: number, now: number = Date.now()): string {
  if (!Number.isFinite(sec)) return "—";
  const t = sec * 1000;
  const diff = now - t;
  if (diff < MINUTE) return "刚刚"; // 含轻微的未来时间（时钟偏差）
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} 分钟前`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)} 小时前`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)} 天前`;

  const d = new Date(t);
  const sameYear = d.getFullYear() === new Date(now).getFullYear();
  const md = `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  return sameYear ? md : `${d.getFullYear()}-${md}`;
}

/** 标题兜底：空标题显示「未命名会话」（trim 后为空也算空）。 */
export function sessionLabel(s: Pick<SessionSummary, "title">): string {
  const t = (s.title ?? "").trim();
  return t || "未命名会话";
}

export function AgentSessionList({
  sessions,
  activeId,
  onPick,
  onDelete,
  onNew,
  error,
}: AgentSessionListProps): JSX.Element {
  const pal = usePalette();
  return (
    <div data-region="agent-session-list" className="flex min-h-0 flex-col gap-2">
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/70">历史会话</span>
        <button
          type="button"
          onClick={onNew}
          title="开一个新会话"
          className="ml-auto inline-flex items-center gap-1 rounded-[3px] border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          新对话
        </button>
      </div>

      {error ? (
        <p
          data-session-error="true"
          className="px-1 py-3 text-[11px] leading-relaxed"
          style={{ color: pal.down }}
        >
          读取会话列表失败：{error}
        </p>
      ) : sessions.length === 0 ? (
        <p className="px-1 py-3 text-[11px] leading-relaxed text-muted-foreground">
          还没有会话。发一句话就会自动开一个。
        </p>
      ) : (
        <ul className="flex min-h-0 flex-col gap-0.5 overflow-y-auto">
          {sessions.map((s) => {
            const label = sessionLabel(s);
            const active = s.id === activeId;
            return (
              <li key={s.id} className="group relative">
                <button
                  type="button"
                  data-session-id={s.id}
                  aria-current={active ? "true" : undefined}
                  onClick={() => onPick(s.id)}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 rounded-[4px] border px-2 py-1.5 pr-8 text-left transition-colors",
                    active
                      ? "border-border bg-[hsl(var(--muted))] text-foreground"
                      : "border-transparent text-muted-foreground hover:bg-[hsl(var(--muted))] hover:text-foreground",
                  )}
                >
                  <span className="w-full truncate text-[12px]">{label}</span>
                  <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
                    {/* suffix 里带「条」：一个 span 一个文本，读屏也读成「12 条」 */}
                    <Num v={s.message_count} digits={0} size="xs" inheritColor suffix=" 条" />
                    <span>·</span>
                    <span>{relativeTime(s.created_at)}</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    // 不做 stopPropagation 的话，点删除会把会话也切走
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                  title="删除会话"
                  aria-label={`删除会话 ${label}`}
                  className="absolute right-1 top-1.5 rounded-[3px] p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
