/**
 * PageView — 展示页路由入口（ADR-0007：页面驱动）。
 * 从路由拿 slug，交给数据驱动的 <PageRenderer/>（AGENTS 硬规则 6：不为单页写组件）。
 */

import { useParams } from "react-router-dom";
import { PageRenderer } from "@/components/PageRenderer";

export function PageView() {
  const { slug } = useParams<{ slug: string }>();
  if (!slug) return null;
  return <PageRenderer slug={slug} />;
}
