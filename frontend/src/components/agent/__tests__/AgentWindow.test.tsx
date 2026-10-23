/**
 * AgentWindow（ROUND3 C2 浮动窗）。
 *
 * 这里测的都是**几何事实**，不是「好不好看」：
 *
 *   1. 拖动改的是 style.left/top，resize 改的是宽高 —— 松手后要能记住
 *   2. 松手时离边 < 16px 吸附到边 —— 差 10px 的窗口看起来就是没对齐，
 *      用户会反复微调，这比「不能拖」更烦人
 *   3. 尺寸有上下界（320×360 / 视口 − 32）—— 没有下界拖到 40×50 就再也
 *      抓不到 resize 把手了（把手只有 14px）
 *   4. 位置/尺寸进 localStorage，刷新后还在；但**窄屏不写** ——
 *      手机上的位置写进去，下次桌面端打开会是个贴边的窄窗
 *   5. 键盘可达：聚焦标题栏后方向键每次移 8px。这既是无障碍，也让
 *      「拖拽」这件事有一个不依赖坐标舍入的确定性验证入口
 *
 * 全部交互走 pointer events（触屏要能拖；mousedown 在触屏上根本不触发）。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentWindow } from "@/components/agent/AgentWindow";

// jsdom 只有 MouseEvent，没有 PointerEvent。没有它的时候 fireEvent.pointerDown
// 会退化成不携带 clientX 的 Event，拖动测试就变成「永远不动」的假绿。
// 补一个最小实现（只补本测试文件用得到的那几个字段）。
beforeAll(() => {
  if (typeof window.PointerEvent !== "undefined") return;
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number;
    readonly pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  Object.defineProperty(window, "PointerEvent", {
    value: PointerEventPolyfill,
    writable: true,
    configurable: true,
  });
});

const KEY = "t-agent-window";
const VW = 1024; // jsdom 默认视口
const VH = 768;

function setViewport(vw: number, vh: number) {
  Object.defineProperty(window, "innerWidth", { value: vw, writable: true, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: vh, writable: true, configurable: true });
}

function win(): HTMLElement {
  const el = document.querySelector('[data-region="agent-window"]');
  if (!el) throw new Error("没有渲染出 [data-region=agent-window]");
  return el as HTMLElement;
}
function bar(): HTMLElement {
  return document.querySelector('[data-region="agent-window-titlebar"]') as HTMLElement;
}
function grip(): HTMLElement {
  return document.querySelector('[data-region="agent-window-resize"]') as HTMLElement;
}
/** 从 inline style 取像素数（不经过 getBoundingClientRect：jsdom 里永远是 0）。 */
function px(el: HTMLElement, prop: "left" | "top" | "width" | "height"): number {
  const raw = (el.style as unknown as Record<string, string>)[prop] ?? "";
  return Number.parseFloat(raw);
}

function mount(onClose = () => {}) {
  return render(
    <AgentWindow title="助手" onClose={onClose} storageKey={KEY}>
      <div data-testid="body">对话内容</div>
    </AgentWindow>,
  );
}

/** 写一份初始 rect，用于「吸附」「往返」这类需要确定起点的用例。 */
function seed(rect: { left: number; top: number; width: number; height: number }) {
  localStorage.setItem(`${KEY}.rect`, JSON.stringify(rect));
}

beforeEach(() => {
  localStorage.clear();
  setViewport(VW, VH);
  document.documentElement.className = "dark";
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
  setViewport(VW, VH);
});

describe("浮层与内容", () => {
  it("是 position:fixed 浮层，渲染标题 / children / headerExtra", () => {
    render(
      <AgentWindow
        title="助手"
        onClose={() => {}}
        storageKey="t-extra"
        headerExtra={<button>历史</button>}
      >
        <div data-testid="body">对话内容</div>
      </AgentWindow>,
    );
    expect(win().style.position).toBe("fixed");
    expect(screen.getByText("助手")).toBeTruthy();
    expect(screen.getByTestId("body").textContent).toBe("对话内容");
    expect(screen.getByText("历史")).toBeTruthy();
  });

  it("关闭按钮调用 onClose", () => {
    const onClose = vi.fn();
    mount(onClose);
    fireEvent.click(screen.getByLabelText("关闭助手窗"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("默认尺寸 420×560，且落在视口内（右下角留 24px 边距）", () => {
    mount();
    expect(px(win(), "width")).toBe(420);
    expect(px(win(), "height")).toBe(560);
    expect(px(win(), "left")).toBe(VW - 420 - 24);
    expect(px(win(), "top")).toBe(VH - 560 - 24);
  });
});

describe("拖动标题栏", () => {
  it("pointerDown + pointerMove 改变 style.left/top（位移等于指针位移）", () => {
    mount();
    const before = { left: px(win(), "left"), top: px(win(), "top") };

    fireEvent.pointerDown(bar(), { clientX: 600, clientY: 300, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 560, clientY: 270, pointerId: 1 });

    expect(px(win(), "left")).toBe(before.left - 40);
    expect(px(win(), "top")).toBe(before.top - 30);
  });

  it("拖动过程中不写 localStorage，松手才写（否则每次 pointermove 都落盘）", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(bar(), { clientX: 300, clientY: 120, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 340, clientY: 140, pointerId: 1 });

    // 拖动中：left 已经在变，但存储里还是旧值
    expect(px(win(), "left")).toBe(140);
    expect(JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}").left).toBe(100);

    fireEvent.pointerUp(bar(), { clientX: 340, clientY: 140, pointerId: 1 });
    expect(JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}").left).toBe(140);
  });

  it("松手后拖动结束：再 pointerMove 不再移动（不能漏掉 dragRef 复位）", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(bar(), { clientX: 300, clientY: 120, pointerId: 1 });
    fireEvent.pointerUp(bar(), { clientX: 300, clientY: 120, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 500, clientY: 300, pointerId: 1 });
    expect(px(win(), "left")).toBe(100);
    expect(px(win(), "top")).toBe(100);
  });

  it("点标题栏上的按钮不算拖动（否则点「历史」会把窗拖走）", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    render(
      <AgentWindow title="助手" onClose={() => {}} storageKey={KEY} headerExtra={<button>历史</button>}>
        <div />
      </AgentWindow>,
    );
    fireEvent.pointerDown(screen.getByText("历史"), { clientX: 300, clientY: 120, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 500, clientY: 400, pointerId: 1 });
    expect(px(win(), "left")).toBe(100);
  });
});

describe("吸附（16px 内贴边）", () => {
  it("拖到距左边 10px → 松手贴到 0", () => {
    seed({ left: 20, top: 200, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(bar(), { clientX: 100, clientY: 220, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 90, clientY: 220, pointerId: 1 }); // left = 10
    expect(px(win(), "left")).toBe(10);
    fireEvent.pointerUp(bar(), { clientX: 90, clientY: 220, pointerId: 1 });
    expect(px(win(), "left")).toBe(0);
    expect(JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}").left).toBe(0);
  });

  it("距右边 10px → 松手右边缘贴视口右缘", () => {
    seed({ left: VW - 400 - 20, top: 100, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(bar(), { clientX: 800, clientY: 120, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 810, clientY: 120, pointerId: 1 }); // left = VW-400-10
    fireEvent.pointerUp(bar(), { clientX: 810, clientY: 120, pointerId: 1 });
    expect(px(win(), "left")).toBe(VW - 400);
  });

  it("离边超过 16px 不吸附（不然每次拖动都会被强行吸住）", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(bar(), { clientX: 300, clientY: 120, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 240, clientY: 120, pointerId: 1 }); // left = 40
    fireEvent.pointerUp(bar(), { clientX: 240, clientY: 120, pointerId: 1 });
    expect(px(win(), "left")).toBe(40);
  });
});

describe("右下角 resize", () => {
  it("pointerMove 改变宽高", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(grip(), { clientX: 500, clientY: 500, pointerId: 1 });
    fireEvent.pointerMove(grip(), { clientX: 560, clientY: 530, pointerId: 1 });
    expect(px(win(), "width")).toBe(460);
    expect(px(win(), "height")).toBe(430);

    fireEvent.pointerUp(grip(), { clientX: 560, clientY: 530, pointerId: 1 });
    const saved = JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}");
    expect(saved.width).toBe(460);
    expect(saved.height).toBe(430);
  });

  it("最小 320×360（再往里拖也不会更小）", () => {
    seed({ left: 100, top: 100, width: 420, height: 560 });
    mount();
    fireEvent.pointerDown(grip(), { clientX: 500, clientY: 600, pointerId: 1 });
    fireEvent.pointerMove(grip(), { clientX: -5000, clientY: -5000, pointerId: 1 });
    expect(px(win(), "width")).toBe(320);
    expect(px(win(), "height")).toBe(360);
  });

  it("最大不超过视口 − 32", () => {
    seed({ left: 0, top: 0, width: 400, height: 400 });
    mount();
    fireEvent.pointerDown(grip(), { clientX: 400, clientY: 400, pointerId: 1 });
    fireEvent.pointerMove(grip(), { clientX: 5000, clientY: 5000, pointerId: 1 });
    expect(px(win(), "width")).toBe(VW - 32);
    expect(px(win(), "height")).toBe(VH - 32);
    // 放大后仍在视口内
    expect(px(win(), "left")).toBeGreaterThanOrEqual(0);
    expect(px(win(), "top")).toBeGreaterThanOrEqual(0);
  });
});

describe("localStorage 往返", () => {
  it("挂载时恢复上次的 rect", () => {
    seed({ left: 40, top: 60, width: 500, height: 450 });
    mount();
    expect(px(win(), "left")).toBe(40);
    expect(px(win(), "top")).toBe(60);
    expect(px(win(), "width")).toBe(500);
    expect(px(win(), "height")).toBe(450);
  });

  it("卸载后重新挂载仍在上次的位置（真实刷新路径）", () => {
    const first = mount();
    fireEvent.pointerDown(bar(), { clientX: 600, clientY: 300, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 520, clientY: 250, pointerId: 1 });
    fireEvent.pointerUp(bar(), { clientX: 520, clientY: 250, pointerId: 1 });
    const left = px(win(), "left");
    const top = px(win(), "top");
    first.unmount();

    mount();
    expect(px(win(), "left")).toBe(left);
    expect(px(win(), "top")).toBe(top);
  });

  it("存储里的坏数据不炸：回落到默认位置", () => {
    localStorage.setItem(`${KEY}.rect`, "{ 不是 json");
    mount();
    expect(px(win(), "width")).toBe(420);
    expect(Number.isFinite(px(win(), "left"))).toBe(true);
  });

  it("存储里的尺寸小于下界时抬到 320×360", () => {
    seed({ left: 40, top: 60, width: 10, height: 10 });
    mount();
    expect(px(win(), "width")).toBe(320);
    expect(px(win(), "height")).toBe(360);
  });

  it("不同 storageKey 互不污染", () => {
    seed({ left: 40, top: 60, width: 500, height: 450 });
    render(
      <AgentWindow title="另一个" onClose={() => {}} storageKey="other-window">
        <div />
      </AgentWindow>,
    );
    const other = document.querySelectorAll('[data-region="agent-window"]');
    const el = other[other.length - 1] as HTMLElement;
    expect(Number.parseFloat(el.style.left)).not.toBe(40);
  });
});

describe("键盘可达（方向键 8px）", () => {
  it("标题栏可聚焦，方向键每次移 8px，并落盘", () => {
    seed({ left: 100, top: 100, width: 400, height: 400 });
    mount();
    expect(bar().getAttribute("tabindex")).toBe("0");

    bar().focus();
    fireEvent.keyDown(bar(), { key: "ArrowRight" });
    expect(px(win(), "left")).toBe(108);
    fireEvent.keyDown(bar(), { key: "ArrowDown" });
    expect(px(win(), "top")).toBe(108);
    fireEvent.keyDown(bar(), { key: "ArrowLeft" });
    expect(px(win(), "left")).toBe(100);
    fireEvent.keyDown(bar(), { key: "ArrowUp" });
    expect(px(win(), "top")).toBe(100);

    expect(JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}").left).toBe(100);
  });

  it("方向键不把窗口推出视口", () => {
    seed({ left: 0, top: 0, width: 400, height: 400 });
    mount();
    fireEvent.keyDown(bar(), { key: "ArrowLeft" });
    fireEvent.keyDown(bar(), { key: "ArrowUp" });
    expect(px(win(), "left")).toBe(0);
    expect(px(win(), "top")).toBe(0);
  });
});

describe("窄屏（< 768px）退化为全屏抽屉", () => {
  beforeEach(() => setViewport(480, 720));

  it("铺满视口、不渲染 resize 把手", () => {
    mount();
    const el = win();
    expect(el.dataset.mode).toBe("drawer");
    expect(el.style.width).toBe("100%");
    expect(el.style.height).toBe("100%");
    expect(px(el, "left")).toBe(0);
    expect(px(el, "top")).toBe(0);
    expect(document.querySelector('[data-region="agent-window-resize"]')).toBeNull();
  });

  it("拖动 / 方向键都不生效，且不写 localStorage", () => {
    mount();
    fireEvent.pointerDown(bar(), { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(bar(), { clientX: 300, clientY: 300, pointerId: 1 });
    fireEvent.pointerUp(bar(), { clientX: 300, clientY: 300, pointerId: 1 });
    fireEvent.keyDown(bar(), { key: "ArrowRight" });

    expect(px(win(), "left")).toBe(0);
    expect(localStorage.getItem(`${KEY}.rect`)).toBeNull();
  });

  it("窄屏不读也不污染桌面端的 rect", () => {
    seed({ left: 300, top: 200, width: 500, height: 500 });
    mount();
    expect(px(win(), "left")).toBe(0);
    expect(localStorage.getItem(`${KEY}.rect`)).not.toBeNull();
    expect(JSON.parse(localStorage.getItem(`${KEY}.rect`) ?? "{}").left).toBe(300);
  });
});

describe("视口变化（换显示器 / 缩小窗口）", () => {
  it("视口变小后窗口被夹回视口内，但不写存储（用户没表达「想放这里」）", () => {
    seed({ left: 600, top: 400, width: 400, height: 400 });
    mount();
    const storedBefore = localStorage.getItem(`${KEY}.rect`);

    setViewport(800, 600);
    fireEvent(window, new Event("resize"));

    // 800 - 400 = 400：右边缘不能超出视口
    expect(px(win(), "left")).toBe(400);
    expect(px(win(), "top")).toBe(200);
    expect(localStorage.getItem(`${KEY}.rect`)).toBe(storedBefore);
  });

  it("跨过断点后变成全屏抽屉（resize 把手随之消失）", () => {
    mount();
    expect(win().dataset.mode).toBe("floating");
    expect(grip()).toBeTruthy();

    setViewport(600, 800);
    fireEvent(window, new Event("resize"));

    expect(win().dataset.mode).toBe("drawer");
    expect(document.querySelector('[data-region="agent-window-resize"]')).toBeNull();
  });
});
