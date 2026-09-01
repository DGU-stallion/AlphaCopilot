/**
 * ArtifactBlock — 按 kind 分发到对应 block 渲染器。artifact 形状（后端 GET 返回）：
 * {id, kind, title, payload, inputs, ...}。chart.payload=ECharts option；
 * table.payload={columns,rows}；markdown/metric.payload={text}。
 */

import { ChartBlock } from "@/components/blocks/ChartBlock";
import { MarkdownBlock } from "@/components/blocks/MarkdownBlock";
import { TableBlock } from "@/components/blocks/TableBlock";

export interface Artifact {
  id: string;
  kind: "chart" | "table" | "markdown" | "metric" | "image";
  title?: string;
  payload?: unknown;
}

export function ArtifactBlock({ artifact }: { artifact: Artifact }) {
  const { kind, title, payload } = artifact;
  switch (kind) {
    case "chart":
      return <ChartBlock option={(payload as Record<string, unknown>) ?? {}} title={title} />;
    case "table":
      return <TableBlock payload={(payload as never) ?? {}} title={title} />;
    case "markdown":
    case "metric":
      return <MarkdownBlock payload={(payload as never) ?? { text: "" }} title={title} />;
    default:
      return (
        <div className="glass rounded-lg p-3 text-sm text-muted-foreground">
          暂不支持的产出类型：{kind}
        </div>
      );
  }
}
