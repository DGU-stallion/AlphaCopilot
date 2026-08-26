// dsh-acp-chart-demo — client half (S2 spike, T06)
// Registers the `chart/plot` conversation-event family (Definition) plus a
// keyed `conversation.chat.node` renderer that draws a pure-SVG line chart.
// Classic single-file script for window.__ModuleLoader__; only seed requires.

window.__ModuleLoader__.load({
	id: "dsh-acp-chart-demo",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		const react_jsx_runtime = require("react/jsx-runtime");

		const COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706"];
		const WIDTH = 640;
		const HEIGHT = 300;
		const PAD = { top: 36, right: 20, bottom: 34, left: 52 };

		//#region chart/plot Definition
		/** Single-event family: one `chart/plot` append owns the whole node. */
		const chartPlotDefinition = {
			kind: "chart.plot",
			target: "chat",
			match: (event) => {
				if (event.type === "chart/plot" && event.data && event.data.chartId !== void 0) {
					return { id: String(event.data.chartId), role: "start" };
				}
				return null;
			},
			start: (_context, match) => ({
				title: match.event.data.title,
				norm: match.event.data.norm,
				series: match.event.data.series
			}),
			update: (context, _match) => context.state,
			buildViewNode: (context) => {
				if (context.start === void 0 || context.state === void 0) return null;
				return {
					key: context.key,
					kind: "chart.plot",
					id: context.id,
					target: "chat",
					anchorSeq: context.start.event.seq,
					location: context.start.location,
					visibility: "visible",
					data: {
						title: context.state.title,
						norm: context.state.norm,
						series: context.state.series
					}
				};
			}
		};
		//#endregion

		//#region pure-SVG line chart
		function domainOf(series) {
			let min = Number.POSITIVE_INFINITY;
			let max = Number.NEGATIVE_INFINITY;
			let count = 0;
			for (const line of series) for (const point of line.points) {
				if (typeof point.v !== "number" || !Number.isFinite(point.v)) continue;
				min = Math.min(min, point.v);
				max = Math.max(max, point.v);
				count += 1;
			}
			if (count === 0) return { min: 0, max: 1 };
			if (min === max) return { min: min - 1, max: max + 1 };
			const pad = (max - min) * 0.08;
			return { min: min - pad, max: max + pad };
		}

		function niceTicks(min, max, steps) {
			const ticks = [];
			for (let i = 0; i <= steps; i += 1) ticks.push(min + ((max - min) * i) / steps);
			return ticks;
		}

		function buildSvg(data) {
			const series = Array.isArray(data.series) ? data.series : [];
			const plotW = WIDTH - PAD.left - PAD.right;
			const plotH = HEIGHT - PAD.top - PAD.bottom;
			const { min, max } = domainOf(series);
			const xOf = (index, total) => PAD.left + (total <= 1 ? plotW / 2 : (plotW * index) / (total - 1));
			const yOf = (v) => PAD.top + plotH - ((v - min) / (max - min)) * plotH;

			const children = [];

			// horizontal gridlines + y tick labels
			const ticks = niceTicks(min, max, 4);
			for (const tick of ticks) {
				const y = yOf(tick);
				children.push(react_jsx_runtime.jsx("line", {
					x1: PAD.left, x2: WIDTH - PAD.right, y1: y, y2: y,
					stroke: "#e2e8f0", "stroke-width": 1
				}, `grid-${tick}`));
				children.push(react_jsx_runtime.jsx("text", {
					x: PAD.left - 8, y: y + 4, "text-anchor": "end",
					"font-size": 10, fill: "#64748b",
					children: tick.toFixed(1)
				}, `ytick-${tick}`));
			}

			// axes
			children.push(react_jsx_runtime.jsx("line", {
				x1: PAD.left, x2: PAD.left, y1: PAD.top, y2: HEIGHT - PAD.bottom,
				stroke: "#94a3b8", "stroke-width": 1
			}, "axis-y"));
			children.push(react_jsx_runtime.jsx("line", {
				x1: PAD.left, x2: WIDTH - PAD.right, y1: HEIGHT - PAD.bottom, y2: HEIGHT - PAD.bottom,
				stroke: "#94a3b8", "stroke-width": 1
			}, "axis-x"));

			// series polylines + points + legend
			series.forEach((line, index) => {
				const color = COLORS[index % COLORS.length];
				const total = Array.isArray(line.points) ? line.points.length : 0;
				if (total > 0) {
					const path = line.points.map((point, i) => `${xOf(i, total).toFixed(1)},${yOf(point.v).toFixed(1)}`).join(" ");
					children.push(react_jsx_runtime.jsx("polyline", {
						points: path, fill: "none", stroke: color,
						"stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"
					}, `line-${index}`));
					line.points.forEach((point, i) => {
						children.push(react_jsx_runtime.jsx("circle", {
							cx: xOf(i, total).toFixed(1), cy: yOf(point.v).toFixed(1), r: 2.5, fill: color
						}, `dot-${index}-${i}`));
					});
				}
				children.push(react_jsx_runtime.jsx("g", {
					children: [
						react_jsx_runtime.jsx("line", {
							x1: PAD.left + 8 + index * 110, x2: PAD.left + 32 + index * 110,
							y1: 16, y2: 16, stroke: color, "stroke-width": 3
						}, `legend-swatch-${index}`),
						react_jsx_runtime.jsx("text", {
							x: PAD.left + 38 + index * 110, y: 20,
							"font-size": 12, fill: "#334155",
							children: `${line.name ?? line.code ?? "?"}(${line.code ?? "-"})`
						}, `legend-label-${index}`)
					]
				}, `legend-${index}`));
			});

			// x labels: first / middle / last day
			const longest = series.reduce((best, line) => (Array.isArray(line.points) && line.points.length > best.length ? line.points : best), []);
			if (longest.length > 0) {
				const marks = [[0, longest[0].t], [Math.floor((longest.length - 1) / 2), longest[Math.floor((longest.length - 1) / 2)].t], [longest.length - 1, longest[longest.length - 1].t]];
				for (const [i, label] of marks) {
					children.push(react_jsx_runtime.jsx("text", {
						x: xOf(i, longest.length).toFixed(1), y: HEIGHT - PAD.bottom + 18,
						"text-anchor": i === 0 ? "start" : i === longest.length - 1 ? "end" : "middle",
						"font-size": 10, fill: "#64748b",
						children: label
					}, `xtick-${i}`));
				}
			}

			return react_jsx_runtime.jsx("svg", {
				width: "100%", viewBox: `0 0 ${WIDTH} ${HEIGHT}`, role: "img",
				style: { display: "block", background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8 },
				children
			}, "chart-svg");
		}
		//#endregion

		//#region keyed chat-node renderer
		function ChartNodeView(props) {
			const node = props.node;
			if (!node || !node.data || !Array.isArray(node.data.series)) return null;
			return react_jsx_runtime.jsx("div", {
				style: { maxWidth: 720, margin: "4px 0" },
				children: [
					react_jsx_runtime.jsx("div", {
						style: { fontSize: 13, fontWeight: 600, color: "#0f172a", margin: "0 0 4px 2px" },
						children: `${node.data.title}${node.data.norm ? ` · ${node.data.norm}` : ""}`
					}, "chart-title"),
					buildSvg(node.data)
				]
			}, "chart-node");
		}
		//#endregion

		const inject = ["conversationEvents", "slots"];

		function apply(ctx) {
			ctx.conversationEvents.register(chartPlotDefinition);
			ctx.slots.inject("conversation.chat.node", () => ctx.slots.register({
				name: "conversation.chat.node",
				key: "chart.plot"
			}, ChartNodeView));
		}

		module.exports = { name: "dsh-acp-chart-demo", inject, apply };
		return module.exports;
	}
});
