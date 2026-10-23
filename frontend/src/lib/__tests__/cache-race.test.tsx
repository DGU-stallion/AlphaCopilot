/**
 * `useCachedResource` 的响应乱序（ROUND2 A5 修）。
 *
 * 真 bug（浏览器实测发现）：快速改参数时，**先发的慢请求后回来，会覆盖
 * 后发的快请求的结果**，界面停在一个「用户已经改掉」的参数上。
 *
 * 触发路径：回测页连续改区间（1 → 1.8 年 → 半年）。半年那次最快回来，
 * 1.8 年那次最慢，于是最后显示的是 1.8 年的图 —— 而参数框里写的是半年。
 * 数值审计场景里这是致命的：图看起来完全合理，只是不是你要的那次。
 *
 * 同样的竞态影响任何快速改参（快线/慢线/标的），不只是日期。
 */
import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { _resetCache, useCachedResource } from "@/lib/cache";

/** 手动控制 resolve 时机的 deferred。 */
function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

function Probe({ k, fetcher }: { k: string; fetcher: () => Promise<string> }) {
  const { data, loading } = useCachedResource(k, fetcher, { ttlMs: 60_000 });
  return <div data-testid="out">{loading ? "loading" : (data ?? "none")}</div>;
}

describe("useCachedResource 响应乱序", () => {
  it("慢的旧请求不得覆盖快的新请求", async () => {
    _resetCache();
    const a = deferred<string>();   // 旧 key，慢
    const b = deferred<string>();   // 新 key，快

    const { rerender, getByTestId } = render(
      <Probe k="k-a" fetcher={() => a.promise} />,
    );
    // 切到新 key（旧请求仍在飞）
    rerender(<Probe k="k-b" fetcher={() => b.promise} />);

    // 新的先回来
    b.resolve("B-data");
    await waitFor(() => expect(getByTestId("out").textContent).toBe("B-data"));

    // 旧的后回来 —— 必须被丢弃
    a.resolve("A-data");
    // 给它几轮微任务，确认状态没有被写回 A
    await new Promise((r) => setTimeout(r, 30));
    expect(getByTestId("out").textContent).toBe("B-data");
  });

  it("同一个 key 不会被乱序影响（正常路径不受损）", async () => {
    _resetCache();
    const a = deferred<string>();
    const { getByTestId } = render(<Probe k="k-same" fetcher={() => a.promise} />);
    a.resolve("only");
    await waitFor(() => expect(getByTestId("out").textContent).toBe("only"));
  });
});
