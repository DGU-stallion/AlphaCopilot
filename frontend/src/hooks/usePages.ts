/**
 * usePages — 拉取 GET /api/pages，为 Sidebar 提供数据驱动的 tab 列表。
 * 失败时返回空，由调用方回退到 builtin 占位（AGENTS 硬规则 6：不为单页写组件）。
 */

import { useEffect, useState } from "react";
import { listPages, type PageListItem } from "@/lib/api";

export function usePages(): PageListItem[] {
  const [pages, setPages] = useState<PageListItem[]>([]);
  useEffect(() => {
    let alive = true;
    listPages()
      .then((p) => alive && setPages(p))
      .catch(() => alive && setPages([]));
    return () => {
      alive = false;
    };
  }, []);
  return pages;
}
