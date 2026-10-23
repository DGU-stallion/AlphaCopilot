/**
 * AgentWindow（ROUND3 C2）：Agent 浮窗外壳。
 *
 * 只负责「一个能被拖动/缩放/记住位置的容器」，对话内容由主控经 children 塞进来
 * （C-render 的 ChatMessage 在气泡层，与这里无关）。
 *
 * 几个非显然的决定，写在代码旁边免得被后来的重构抹掉：
 *
 * 1. **pointer events 而不是 mouse events**：mousedown 在触屏上不触发，
 *    手机上这个窗就完全拖不动。`setPointerCapture` 让指针划出标题栏之后
 *    事件仍然回到标题栏 —— 否则快速拖动时指针跑到内容区，拖动就"断"了。
 *
 * 2. **吸附阈值 16px**：用户把窗拖到离边 10px 松手，视觉上就是"没对齐"，
 *    会反复微调。吸附把「差一点」变成「对齐」，成本是一个 if。
 *
 * 3. **松手才写 localStorage**：pointermove 每帧一次，每次都落盘是无意义的写。
 *
 * 4. **窄屏不写 localStorage**（< 768px 退化为全屏抽屉）：手机上的位置/尺寸
 *    写到同一把键里，下次在桌面端打开会拿到一个"贴边窄窗"，而且用户会以为
 *    窗口坏了 —— 这属于「记录状态」反而制造 bug 的典型场景。
 *
 * 5. **标题栏键盘可达**：方向键移 8px。无障碍的最低要求（纯拖拽界面键盘用户
 *    完全用不了），顺带让测试可以确定性地验证"移动"。
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { GripHorizontal, X } from "lucide-react";
import { cn } from "@/lib/utils";

/** 最小尺寸。再小就连 resize 把手（16px）都抓不到了。 */
export const AGENT_WINDOW_MIN = { width: 320, height: 360 } as const;
/** 浮层与视口之间至少留这么宽，否则边缘与窗口边框糊在一起。 */
const VIEWPORT_GAP = 32;
/** 默认离右下角的距离（与 Layout 侧栏的观感一致）。 */
const DEFAULT_EDGE = 24;
/** 吸附阈值：距边 < 16px 视为"想贴边"。 */
const SNAP = 16;
/** 键盘每次移动量。 */
const STEP = 8;
/** 窄屏断点：低于它退化为全屏抽屉。 */
const DRAWER_BP = 768;
/** 默认存储键前缀；调用方可传不同的值避免互相覆盖（测试也靠它隔离）。 */
const DEFAULT_STORAGE_KEY = "ac-agent-window";

const DEFAULT_SIZE = { width: 420, height: 560 };

export interface AgentWindowProps {
  title?: string;
  onClose: () => void;
  /** 对话内容（主控塞 AiMessages / ChatMessage / 输入框） */
  children: ReactNode;
  /** 头部右侧额外按钮（主控用来塞「历史」开关） */
  headerExtra?: ReactNode;
  /** 本地存储键前缀，默认 `ac-agent-window`；实际写入键是 `${storageKey}.rect` */
  storageKey?: string;
}

interface Size {
  width: number;
  height: number;
}

interface Rect extends Size {
  left: number;
  top: number;
}

function viewport(): { vw: number; vh: number } {
  return {
    vw: window.innerWidth || document.documentElement.clientWidth || 1024,
    vh: window.innerHeight || document.documentElement.clientHeight || 768,
  };
}

/** 尺寸夹到 [最小, 视口 − 32]。视口比最小值还小时以最小值为准（宁可溢出也不给 40px 窗）。 */
function clampSize(width: number, height: number, vw: number, vh: number): Size {
  const maxW = Math.max(AGENT_WINDOW_MIN.width, vw - VIEWPORT_GAP);
  const maxH = Math.max(AGENT_WINDOW_MIN.height, vh - VIEWPORT_GAP);
  return {
    width: Math.min(Math.max(width, AGENT_WINDOW_MIN.width), maxW),
    height: Math.min(Math.max(height, AGENT_WINDOW_MIN.height), maxH),
  };
}

/** 位置夹到「完全可见」。只夹位置不夹尺寸：尺寸约束是 clampSize 的事。 */
function clampPos(rect: Rect, vw: number, vh: number): Rect {
  const maxLeft = Math.max(0, vw - rect.width);
  const maxTop = Math.max(0, vh - rect.height);
  return {
    ...rect,
    left: Math.min(Math.max(rect.left, 0), maxLeft),
    top: Math.min(Math.max(rect.top, 0), maxTop),
  };
}

/** 整份布局约束一次做完（读存储、视口变化、松手时都用同一条路径）。 */
function clampRect(rect: Rect, vw: number, vh: number): Rect {
  const size = clampSize(rect.width, rect.height, vw, vh);
  return clampPos({ ...rect, ...size }, vw, vh);
}

function defaultRect(vw: number, vh: number): Rect {
  const size = clampSize(DEFAULT_SIZE.width, DEFAULT_SIZE.height, vw, vh);
  return clampPos(
    {
      ...size,
      left: vw - size.width - DEFAULT_EDGE,
      top: vh - size.height - DEFAULT_EDGE,
    },
    vw,
    vh,
  );
}

/** 松手时的吸附：16px 内贴边。bad 的输入（NaN）由调用方先 clamp。 */
function snapToEdges(rect: Rect, vw: number, vh: number): Rect {
  let { left, top } = rect;
  if (left <= SNAP) left = 0;
  else if (vw - (left + rect.width) <= SNAP) left = vw - rect.width;
  if (top <= SNAP) top = 0;
  else if (vh - (top + rect.height) <= SNAP) top = vh - rect.height;
  return { ...rect, left: Math.round(left), top: Math.round(top) };
}

function readRect(key: string, vw: number, vh: number): Rect {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return defaultRect(vw, vh);
    const parsed = JSON.parse(raw) as Partial<Rect>;
    const nums = [parsed.left, parsed.top, parsed.width, parsed.height];
    if (!nums.every((n) => typeof n === "number" && Number.isFinite(n))) {
      return defaultRect(vw, vh);
    }
    return clampRect(parsed as Rect, vw, vh);
  } catch {
    // 坏 JSON / 隐私模式禁 localStorage：静默回默认值，绝不能因此白屏
    return defaultRect(vw, vh);
  }
}

function writeRect(key: string, rect: Rect): void {
  try {
    const rounded: Rect = {
      left: Math.round(rect.left),
      top: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };
    localStorage.setItem(key, JSON.stringify(rounded));
  } catch {
    // 存储不可用只影响"记住位置"，不影响本次使用
  }
}

/** 窄屏判定（渲染与落盘用同一个判定，避免"渲染成抽屉却写了浮层位置"）。 */
function isDrawer(): boolean {
  return (window.innerWidth || document.documentElement.clientWidth || 1024) < DRAWER_BP;
}

const CURSOR_KEYS: Record<string, [number, number]> = {
  ArrowLeft: [-STEP, 0],
  ArrowRight: [STEP, 0],
  ArrowUp: [0, -STEP],
  ArrowDown: [0, STEP],
};

export function AgentWindow({
  title = "助手",
  onClose,
  children,
  headerExtra,
  storageKey = DEFAULT_STORAGE_KEY,
}: AgentWindowProps): JSX.Element {
  const rectKey = `${storageKey}.rect`;

  const [vp, setVp] = useState(viewport);
  const drawer = vp.vw < DRAWER_BP;

  // 只在首次挂载读存储：storageKey 是测试隔离用的，运行期不会变（变了也不重新读，
  // 否则主控改个 key 就会把用户正在拖的窗弹回旧位置）
  const [rect, setRect] = useState<Rect>(() => {
    const { vw, vh } = viewport();
    return readRect(rectKey, vw, vh);
  });
  // 事件回调里需要"当前几何"但不能依赖闭包里的旧 state（一次拖动会连发多帧）
  const rectRef = useRef<Rect>(rect);
  const [dragging, setDragging] = useState(false);

  const commit = useCallback(
    (next: Rect, persist: boolean) => {
      const rounded: Rect = {
        left: Math.round(next.left),
        top: Math.round(next.top),
        width: Math.round(next.width),
        height: Math.round(next.height),
      };
      rectRef.current = rounded;
      setRect(rounded);
      // 窄屏不落盘（见文件头第 4 条）。
      // 抽屉态下拖动/缩放/键盘三个入口都已提前返回，所以这里的 !isDrawer() 目前
      // 是一道**兜底**而不是主路径 —— 它防的是「以后有人加了一条新的落盘路径」。
      // 代价是一行 if，收益是手机上不会再写出一个把桌面端带歪的 rect。
      if (persist && !isDrawer()) writeRect(rectKey, rounded);
    },
    [rectKey],
  );

  // 视口变化：把窗夹回视口内，但**不落盘** —— 用户没表达"想放在这里"
  useEffect(() => {
    const onResize = () => {
      const { vw, vh } = viewport();
      setVp({ vw, vh });
      const fixed = clampRect(rectRef.current, vw, vh);
      const cur = rectRef.current;
      if (
        fixed.left !== cur.left ||
        fixed.top !== cur.top ||
        fixed.width !== cur.width ||
        fixed.height !== cur.height
      ) {
        rectRef.current = fixed;
        setRect(fixed);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // ---------------- 拖动标题栏 ----------------
  const drag = useRef<{ x: number; y: number; rect: Rect } | null>(null);

  const capture = (el: HTMLElement, pointerId: number) => {
    try {
      el.setPointerCapture?.(pointerId);
    } catch {
      // jsdom / 老浏览器没有 pointer capture：不影响逻辑，只是指针划出元素会断
    }
  };
  const release = (el: HTMLElement, pointerId: number) => {
    try {
      el.releasePointerCapture?.(pointerId);
    } catch {
      /* 同上 */
    }
  };

  const onBarPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drawer) return;
    // 标题栏上的按钮（历史/关闭…）不是拖拽区：否则点「历史」会把窗拖走
    if ((e.target as HTMLElement).closest("button,a,input,select,textarea")) return;
    drag.current = { x: e.clientX, y: e.clientY, rect: rectRef.current };
    capture(e.currentTarget, e.pointerId);
    setDragging(true);
  };

  const onBarPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || drawer) return;
    const { vw, vh } = viewport();
    commit(
      clampPos(
        {
          ...d.rect,
          left: d.rect.left + (e.clientX - d.x),
          top: d.rect.top + (e.clientY - d.y),
        },
        vw,
        vh,
      ),
      false,
    );
  };

  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setDragging(false);
    release(e.currentTarget, e.pointerId);
    const { vw, vh } = viewport();
    commit(snapToEdges(clampRect(rectRef.current, vw, vh), vw, vh), true);
  };

  // ---------------- 右下角 resize ----------------
  const resize = useRef<{ x: number; y: number; rect: Rect } | null>(null);

  const onGripPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (drawer) return;
    resize.current = { x: e.clientX, y: e.clientY, rect: rectRef.current };
    capture(e.currentTarget, e.pointerId);
    setDragging(true);
  };

  const onGripPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = resize.current;
    if (!r || drawer) return;
    const { vw, vh } = viewport();
    const size = clampSize(
      r.rect.width + (e.clientX - r.x),
      r.rect.height + (e.clientY - r.y),
      vw,
      vh,
    );
    // 放大到超出右/下边缘时不是"无视"，而是把整窗推回视口内（左边反而左移）
    commit(clampPos({ ...r.rect, ...size }, vw, vh), false);
  };

  const endResize = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = resize.current;
    if (!r) return;
    resize.current = null;
    setDragging(false);
    release(e.currentTarget, e.pointerId);
    const { vw, vh } = viewport();
    commit(clampRect(rectRef.current, vw, vh), true);
  };

  // ---------------- 键盘 ----------------
  const onBarKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (drawer) return;
    const delta = CURSOR_KEYS[e.key];
    if (!delta) return;
    e.preventDefault(); // 方向键不应该顺带滚动页面
    const { vw, vh } = viewport();
    const cur = rectRef.current;
    commit(
      clampPos({ ...cur, left: cur.left + delta[0], top: cur.top + delta[1] }, vw, vh),
      true,
    );
  };

  const style: CSSProperties = drawer
    ? { position: "fixed", left: 0, top: 0, width: "100%", height: "100%", zIndex: 50 }
    : {
        position: "fixed",
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        zIndex: 50,
      };

  return (
    <section
      data-region="agent-window"
      data-mode={drawer ? "drawer" : "floating"}
      role="dialog"
      aria-label={title}
      className="flex flex-col overflow-hidden border border-border bg-card shadow-lg"
      style={style}
    >
      <div
        data-region="agent-window-titlebar"
        // 可聚焦 + 方向键 = 不可拖拽场景（键盘用户）的唯一入口
        tabIndex={0}
        role="group"
        aria-label="窗口标题栏（方向键移动窗口）"
        onPointerDown={onBarPointerDown}
        onPointerMove={onBarPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onBarKeyDown}
        className={cn(
          "flex shrink-0 touch-none select-none items-center gap-2 border-b border-border px-3 py-2",
          drawer ? "cursor-default" : dragging ? "cursor-grabbing" : "cursor-grab",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[hsl(var(--primary))]",
        )}
      >
        <GripHorizontal className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
        <span className="truncate text-[13px] font-medium">{title}</span>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {headerExtra}
          <button
            type="button"
            onClick={onClose}
            title="关闭"
            aria-label="关闭助手窗"
            className="rounded-[3px] p-1 text-muted-foreground transition-colors hover:bg-[hsl(var(--muted))] hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">{children}</div>

      {!drawer && (
        <div
          data-region="agent-window-resize"
          role="separator"
          aria-label="拖动调整窗口大小"
          title="拖动调整大小"
          onPointerDown={onGripPointerDown}
          onPointerMove={onGripPointerMove}
          onPointerUp={endResize}
          onPointerCancel={endResize}
          className={cn(
            "absolute bottom-0 right-0 z-10 flex h-4 w-4 touch-none items-center justify-center text-muted-foreground/50",
            "cursor-nwse-resize transition-colors hover:text-primary",
          )}
        >
          {/* 一个角标就够，不用做大把手：大把手会盖住内容 */}
          <span className="block h-2 w-2 border-b border-r border-current" />
        </div>
      )}
    </section>
  );
}
