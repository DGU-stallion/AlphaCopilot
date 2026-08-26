// dsh-acp-chart-demo — host half (S2 spike, T06)
// Registers the `/chart-demo` user command; appends a `chart/plot` session
// event into the current session. Pure JS on purpose: SessionEventMap type
// merging is deferred to the production TS package (chart-plot).

const name = "dsh-acp-chart-demo";
const inject = ["commands"];

const DEMO_CHART_ID = "demo-1";
const POINT_COUNT = 20;
// 2026-07-01 UTC as epoch ms; spike data needs no timezone correctness.
const BASE_DAY_MS = Date.UTC(2026, 6, 1);

function isoDay(offset) {
	return new Date(BASE_DAY_MS + offset * 86400000).toISOString().slice(0, 10);
}

function demoPoints(seed, count) {
	const points = [];
	for (let i = 0; i < count; i += 1) {
		const phase = (i / count) * Math.PI * 2;
		points.push({
			t: isoDay(i),
			v: Number((Math.sin(phase + seed) * 3 + Math.sin(phase * 0.5 + seed * 0.3) + i * 0.08).toFixed(2))
		});
	}
	return points;
}

function demoPayload(chartId) {
	return {
		chartId,
		title: "对比走势(demo)",
		norm: "pct_change",
		series: [
			{ code: "600519", name: "贵州茅台", points: demoPoints(0, POINT_COUNT) },
			{ code: "000858", name: "五粮液", points: demoPoints(0.9, POINT_COUNT) }
		]
	};
}

function apply(ctx) {
	ctx.commands.register({
		name: "chart-demo",
		description: "append a demo chart/plot event into the current session",
		handler: async (invocation) => {
			try {
				await invocation.agent.session.append("chart/plot", demoPayload(DEMO_CHART_ID));
				return { kind: "success", text: `chart/plot appended (chartId=${DEMO_CHART_ID})` };
			} catch (error) {
				const message = error instanceof Error ? error.message : String(error);
				ctx.logger?.warn?.(`[dsh-acp-chart-demo] chart/plot append failed: ${message}`);
				return { kind: "error", text: `chart/plot append failed: ${message}` };
			}
		}
	});
}

export { apply, inject, name };
