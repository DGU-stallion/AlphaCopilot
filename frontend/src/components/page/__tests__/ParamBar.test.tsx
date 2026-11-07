/**
 * 参数栏（ADR-0016 决定 2）：按 spec.params 自动生成控件。
 *
 * 为什么必须自动生成：`Backtest.tsx` 里有一整段手写的「标的/快线/慢线/区间/策略」
 * 输入框（40 行 state + 40 行 JSX）。加一个分析页就要再抄一遍，且很容易抄漏一个
 * 参数 —— 漏了页面能开但永远用默认值算，看不出哪里错。
 *
 * 控件类型与 backend/alpha/registry.py 的 ParamSpec 一一对应：
 *   int / float / str / enum / date_range / symbol_list
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DATE_RANGE_PRESETS, type PageParam } from "@/lib/page-spec";

import { ParamBar } from "../ParamBar";

const p = (over: Partial<PageParam> & { name: string; type: PageParam["type"] }): PageParam =>
  ({ label: over.name, default: undefined, ...over }) as PageParam;

describe("ParamBar 的控件生成", () => {
  it("int 参数给数字输入框，值变化回调成 number", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "fast", type: "int", label: "快线", default: 20 })]}
        values={{ fast: 20 }}
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText("快线") as HTMLInputElement;
    expect(input.type).toBe("number");
    fireEvent.change(input, { target: { value: "30" } });
    expect(onChange).toHaveBeenCalledWith("fast", 30);
  });

  it("float 参数也回调成 number（不是字符串）", () => {
    // 回调成字符串的话后端 ParamSpec.coerce 能兜住，但前端后续比较会出错。
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "thr", type: "float", label: "阈值", default: 0.5 })]}
        values={{ thr: 0.5 }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("阈值"), { target: { value: "0.8" } });
    expect(onChange).toHaveBeenCalledWith("thr", 0.8);
  });

  it("enum 参数生成下拉，选项来自 choices", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "mode", type: "enum", label: "模式", choices: ["a", "b"], default: "a" })]}
        values={{ mode: "a" }}
        onChange={onChange}
      />,
    );
    const sel = screen.getByLabelText("模式") as HTMLSelectElement;
    expect(sel.tagName).toBe("SELECT");
    expect(sel.options).toHaveLength(2);
    fireEvent.change(sel, { target: { value: "b" } });
    expect(onChange).toHaveBeenCalledWith("mode", "b");
  });

  it("date_range 生成区间选择，提交预设字符串", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "range", type: "date_range", label: "区间", default: "1y" })]}
        values={{ range: "1y" }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("区间"), { target: { value: "3m" } });
    expect(onChange).toHaveBeenCalledWith("range", "3m");
  });

  it("symbol_list 显示为可编辑的代码串，逗号分隔提交成数组", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "symbols", type: "symbol_list", label: "标的",
                    default: ["600519", "000858"] })]}
        values={{ symbols: ["600519", "000858"] }}
        onChange={onChange}
      />,
    );
    const input = screen.getByLabelText("标的") as HTMLInputElement;
    expect(input.value).toBe("600519, 000858");
    fireEvent.change(input, { target: { value: "600519, 000858, 000568" } });
    expect(onChange).toHaveBeenCalledWith("symbols", ["600519", "000858", "000568"]);
  });

  it("symbol_list 过滤掉空段与空白（末尾多个逗号不该产生空标的）", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "symbols", type: "symbol_list", label: "标的", default: [] })]}
        values={{ symbols: [] }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("标的"), { target: { value: "600519,, 000858, " } });
    expect(onChange).toHaveBeenCalledWith("symbols", ["600519", "000858"]);
  });

  it("没有参数时不渲染任何东西（不留空 bar）", () => {
    const { container } = render(<ParamBar params={[]} values={{}} onChange={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("date_range 的预设与自定义区间（ROUND2 A5）", () => {
  it("预设里**不能**有后端不认的值（2y/3y 曾导致 400）", () => {
    // 后端 alpha/registry.py 的 _coerce_date_range 只认 1y / 6m / 3m 或 ISO 区间。
    // 前端多给的选项就是「UI 撒谎」——用户选了必然失败。
    const values = DATE_RANGE_PRESETS.map((p) => p.value);
    expect(values).toEqual(["3m", "6m", "1y"]);
    expect(values).not.toContain("2y");
    expect(values).not.toContain("3y");
  });

  it("开始/截止都取到后提交 'start:end'（后端认的 ISO 形态）", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "range", type: "date_range", label: "区间", default: "1y" })]}
        values={{ range: "2025-01-01:2025-06-30" }}
        onChange={onChange}
      />,
    );
    // 已有 ISO 值时，选择器应显示「自定义」并露出两个日期框
    const start = screen.getByLabelText("区间 起") as HTMLInputElement;
    expect(start.value).toBe("2025-01-01");

    fireEvent.change(screen.getByLabelText("区间 止"), { target: { value: "2025-12-31" } });
    expect(onChange).toHaveBeenCalledWith("range", "2025-01-01:2025-12-31");
  });

  it("预设值不露出日期框（保持紧凑）", () => {
    render(
      <ParamBar
        params={[p({ name: "range", type: "date_range", label: "区间", default: "1y" })]}
        values={{ range: "1y" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText("区间 起")).toBeNull();
  });

  it("选「自定义」时给一个合法初值，而不是空串（空值提交会被后端拒）", () => {
    const onChange = vi.fn();
    render(
      <ParamBar
        params={[p({ name: "range", type: "date_range", label: "区间", default: "1y" })]}
        values={{ range: "1y" }}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("区间"), { target: { value: "__custom__" } });
    const arg = onChange.mock.calls.at(-1)[1] as string;
    // 形态必须是 start:end 且两端都是 ISO 日期
    expect(arg).toMatch(/^\d{4}-\d{2}-\d{2}:\d{4}-\d{2}-\d{2}$/);
  });
});
