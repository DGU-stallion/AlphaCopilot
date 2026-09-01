import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { jsx } from "react/jsx-runtime";
//#region src/definition.ts
const chartPlotDefinition = {
	kind: "chart.plot",
	target: "chat",
	match(event) {
		if (event.type === "chart/plot" && event.data && typeof event.data.chartId === "string") return {
			id: String(event.data.chartId),
			role: "start"
		};
		return null;
	},
	start(_context, match) {
		return match.event.data;
	},
	update(_context, _match) {
		return _context.state;
	},
	buildViewNode(context) {
		if (!context.state) return null;
		const state = context.state;
		const anchorSeq = context.start?.event.seq ?? 0;
		return {
			key: context.key,
			kind: "chart.plot",
			id: context.id,
			target: "chat",
			anchorSeq,
			location: context.start?.location ?? {
				kind: "step",
				turn: 0,
				step: 0,
				key: "chart.plot"
			},
			visibility: "visible",
			data: {
				title: state.title,
				series: state.series
			}
		};
	}
};
//#endregion
//#region src/components/ChartNodeView.tsx
/** ECharts-based chart renderer for dsh chat flow. */
function ChartNodeView({ node }) {
	const ref = useRef(null);
	const chartRef = useRef(null);
	useEffect(() => {
		if (!ref.current) return;
		if (!chartRef.current) chartRef.current = echarts.init(ref.current);
		const { title, series } = node.data;
		chartRef.current.setOption({
			title: { text: title },
			tooltip: { trigger: "axis" },
			legend: { data: series.map((s) => s.name) },
			xAxis: {
				type: "category",
				data: series[0]?.points?.map((p) => p.t) ?? []
			},
			yAxis: { type: "value" },
			series: series.map((s) => ({
				name: s.name,
				type: "line",
				data: s.points.map((p) => p.v)
			}))
		});
		return () => chartRef.current?.dispose();
	}, [node.data]);
	return /* @__PURE__ */ jsx("div", {
		ref,
		style: {
			width: "100%",
			height: 300
		}
	});
}
//#endregion
//#region src/renderer.ts
/** Keyed renderer for chart.plot nodes. */
const RENDERER_KEY = "chart.plot";
const RendererComponent = ChartNodeView;
//#endregion
//#region src/index.ts
const inject = ["slots", "conversationEvents"];
function apply(ctx) {
	ctx.conversationEvents.register(chartPlotDefinition);
	ctx.slots.inject("conversation.chat.node", () => ctx.slots.register({
		name: "conversation.chat.node",
		key: RENDERER_KEY
	}, RendererComponent));
}
//#endregion
export { apply, inject };
