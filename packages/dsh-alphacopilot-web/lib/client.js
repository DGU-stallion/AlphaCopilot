window.__ModuleLoader__.load({
	id: "dsh-alphacopilot-web",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		//#region \0rolldown/runtime.js
		var __create = Object.create;
		var __defProp = Object.defineProperty;
		var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
		var __getOwnPropNames = Object.getOwnPropertyNames;
		var __getProtoOf = Object.getPrototypeOf;
		var __hasOwnProp = Object.prototype.hasOwnProperty;
		var __copyProps = (to, from, except, desc) => {
			if (from && typeof from === "object" || typeof from === "function") for (var keys = __getOwnPropNames(from), i = 0, n = keys.length, key; i < n; i++) {
				key = keys[i];
				if (!__hasOwnProp.call(to, key) && key !== except) __defProp(to, key, {
					get: ((k) => from[k]).bind(null, key),
					enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable
				});
			}
			return to;
		};
		var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(isNodeMode || !mod || !mod.__esModule || !__hasOwnProp.call(mod, "default") ? __defProp(target, "default", {
			value: mod,
			enumerable: true
		}) : target, mod));
		//#endregion
		let react = require("react");
		react = __toESM(react, 1);
		let react_jsx_runtime = require("react/jsx-runtime");
		//#region src/client/DailyReviewPage.tsx
		const MOCK_INDICES = [
			{
				name: "上证指数",
				price: 3428.62,
				change_pct: .82
			},
			{
				name: "深证成指",
				price: 10845.31,
				change_pct: 1.24
			},
			{
				name: "创业板指",
				price: 2198.45,
				change_pct: -.31
			},
			{
				name: "科创50",
				price: 892.15,
				change_pct: .45
			}
		];
		const MOCK_GLOBAL = [
			{
				name: "纳斯达克",
				region: "美股",
				price: 18273.42,
				change_pct: .62
			},
			{
				name: "恒生指数",
				region: "港股",
				price: 19842.11,
				change_pct: -.18
			},
			{
				name: "日经225",
				region: "日股",
				price: 38421,
				change_pct: .91
			}
		];
		const MOCK_SECTORS = [
			{
				name: "半导体",
				pct: 3.21,
				net: 42.8,
				inflow: 58.2,
				outflow: 15.4,
				firms: 86
			},
			{
				name: "计算机",
				pct: 2.84,
				net: 31.5,
				inflow: 44.1,
				outflow: 12.6,
				firms: 124
			},
			{
				name: "电子",
				pct: 2.12,
				net: 28.3,
				inflow: 39.7,
				outflow: 11.4,
				firms: 98
			},
			{
				name: "通信",
				pct: 1.95,
				net: 19.4,
				inflow: 27.8,
				outflow: 8.4,
				firms: 62
			},
			{
				name: "传媒",
				pct: 1.42,
				net: 12.1,
				inflow: 18.9,
				outflow: 6.8,
				firms: 71
			},
			{
				name: "电力设备",
				pct: .82,
				net: 5.3,
				inflow: 16.2,
				outflow: 10.9,
				firms: 102
			},
			{
				name: "医药生物",
				pct: -.21,
				net: -3.2,
				inflow: 12.4,
				outflow: 15.6,
				firms: 88
			},
			{
				name: "银行",
				pct: -.45,
				net: -8.7,
				inflow: 9.1,
				outflow: 17.8,
				firms: 42
			},
			{
				name: "房地产",
				pct: -1.12,
				net: -14.2,
				inflow: 6.3,
				outflow: 20.5,
				firms: 54
			},
			{
				name: "煤炭",
				pct: -1.84,
				net: -18.9,
				inflow: 4.2,
				outflow: 23.1,
				firms: 31
			}
		];
		const pctClass = (p) => p > 0 ? "acp-up" : p < 0 ? "acp-down" : "acp-flat";
		const fmt = (v) => v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
		function DailyReviewPage() {
			const today = (/* @__PURE__ */ new Date()).toLocaleDateString("zh-CN", {
				year: "numeric",
				month: "2-digit",
				day: "2-digit"
			});
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: "acp-daily-review",
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("style", { children: `
        .acp-daily-review{--acp-up:var(--dsw-static-red-500, #e5484d);--acp-down:var(--dsw-static-green-500, #30a46c);--acp-card-bg:var(--dsw-alias-bg-layer-2, #fff);--acp-border:var(--dsw-alias-border-l2, rgba(0,0,0,0.08));}
        .acp-up{color:var(--acp-up)!important}.acp-down{color:var(--acp-down)!important}.acp-flat{color:var(--dsw-alias-label-secondary)}
        .acp-card{background:var(--acp-card-bg);border:1px solid var(--acp-border);border-radius:16px;box-shadow:var(--dsw-shadow-lv2, 0 1px 3px rgba(0,0,0,0.08));}
      ` }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							display: "flex",
							flexWrap: "wrap",
							alignItems: "flex-end",
							justifyContent: "space-between",
							gap: 12,
							marginBottom: 20
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h1", {
							style: {
								fontSize: 22,
								fontWeight: 700,
								letterSpacing: -.5,
								color: "var(--dsw-alias-label-primary)",
								margin: 0
							},
							children: "每日复盘"
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
							style: {
								margin: "4px 0 0",
								fontSize: 13,
								color: "var(--dsw-alias-label-secondary)"
							},
							children: [today, " · 大盘 / 情绪 / 板块资金一屏看全"]
						})] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
							style: {
								fontSize: 11,
								color: "var(--dsw-alias-label-tertiary)",
								background: "var(--dsw-alias-bg-layer-1)",
								border: "1px solid var(--acp-border)",
								borderRadius: 20,
								padding: "4px 10px"
							},
							children: "S4 静态 mock · 接入 REST 后替换为实时数据"
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("h3", {
						style: {
							fontSize: 13,
							fontWeight: 600,
							color: "var(--dsw-alias-label-secondary)",
							margin: "0 0 8px",
							display: "flex",
							alignItems: "center",
							gap: 6
						},
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "📈" }),
							" 大盘指数",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									fontSize: 11,
									fontWeight: 400,
									color: "var(--dsw-alias-label-tertiary)"
								},
								children: "· 实时 · 红涨绿跌"
							})
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							display: "grid",
							gridTemplateColumns: "repeat(auto-fill, minmax(160px,1fr))",
							gap: 10,
							marginBottom: 16
						},
						children: [MOCK_INDICES.map((it) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							className: "acp-card",
							style: { padding: 14 },
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									style: {
										fontSize: 12,
										color: "var(--dsw-alias-label-tertiary)",
										whiteSpace: "nowrap",
										overflow: "hidden",
										textOverflow: "ellipsis"
									},
									children: it.name
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									className: pctClass(it.change_pct),
									style: {
										fontFamily: "var(--ds-font-family-code, monospace)",
										fontSize: 18,
										fontWeight: 700,
										marginTop: 4
									},
									children: fmt(it.price)
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									className: pctClass(it.change_pct),
									style: {
										fontFamily: "monospace",
										fontSize: 12,
										marginTop: 2
									},
									children: [
										it.change_pct > 0 ? "+" : "",
										it.change_pct.toFixed(2),
										"%"
									]
								})
							]
						}, it.name)), MOCK_GLOBAL.map((it) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							className: "acp-card",
							style: {
								padding: 14,
								opacity: .92
							},
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									style: {
										fontSize: 12,
										color: "var(--dsw-alias-label-tertiary)"
									},
									children: [
										it.name,
										" ",
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											style: {
												fontSize: 10,
												opacity: .6
											},
											children: it.region
										})
									]
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									className: it.change_pct !== null ? pctClass(it.change_pct) : void 0,
									style: {
										fontFamily: "monospace",
										fontSize: 18,
										fontWeight: 700,
										marginTop: 4
									},
									children: it.price !== null ? fmt(it.price) : "—"
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									className: it.change_pct !== null ? pctClass(it.change_pct) : void 0,
									style: {
										fontFamily: "monospace",
										fontSize: 12,
										marginTop: 2
									},
									children: it.change_pct === null ? "—" : `${it.change_pct > 0 ? "+" : ""}${it.change_pct.toFixed(2)}%`
								})
							]
						}, it.name))]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("h3", {
						style: {
							fontSize: 13,
							fontWeight: 600,
							color: "var(--dsw-alias-label-secondary)",
							margin: "0 0 8px",
							display: "flex",
							alignItems: "center",
							gap: 6
						},
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "⚡" }),
							" 市场情绪",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									fontSize: 11,
									fontWeight: 400,
									color: "var(--dsw-alias-label-tertiary)"
								},
								children: "· 2026-08-27"
							})
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: "acp-card",
						style: {
							padding: 16,
							marginBottom: 16
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: {
								display: "grid",
								gridTemplateColumns: "repeat(4,1fr)",
								gap: 8
							},
							children: [
								{
									k: "涨停",
									v: "42",
									cls: "acp-up"
								},
								{
									k: "跌停",
									v: "5",
									cls: "acp-down"
								},
								{
									k: "最高连板",
									v: "5 板",
									cls: ""
								},
								{
									k: "连板(2板+)",
									v: "12 家",
									cls: ""
								}
							].map((c) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: {
									background: "var(--dsw-alias-bg-layer-1)",
									borderRadius: 12,
									padding: "12px 8px",
									textAlign: "center"
								},
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									style: {
										fontSize: 11,
										color: "var(--dsw-alias-label-tertiary)"
									},
									children: c.k
								}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
									className: c.cls,
									style: {
										fontFamily: "monospace",
										fontSize: 18,
										fontWeight: 700,
										marginTop: 4,
										color: c.cls ? void 0 : "var(--dsw-alias-label-primary)"
									},
									children: c.v
								})]
							}, c.k))
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: {
								display: "grid",
								gridTemplateColumns: "repeat(3,1fr)",
								gap: 8,
								marginTop: 10
							},
							children: [
								{
									k: "封板率",
									v: "82.4%",
									hint: "封住/尝试涨停"
								},
								{
									k: "炸板率",
									v: "17.6%",
									hint: "炸板/尝试涨停"
								},
								{
									k: "晋级率",
									v: "38.2%",
									hint: "昨涨停今又停"
								}
							].map((c) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
								style: {
									background: "var(--dsw-alias-bg-layer-1)",
									borderRadius: 10,
									padding: "10px 8px",
									textAlign: "center"
								},
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
										style: {
											fontSize: 11,
											color: "var(--dsw-alias-label-tertiary)"
										},
										children: c.k
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
										style: {
											fontFamily: "monospace",
											fontSize: 13,
											fontWeight: 700,
											marginTop: 4,
											color: "var(--dsw-alias-label-primary)"
										},
										children: c.v
									}),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
										style: {
											fontSize: 10,
											color: "var(--dsw-alias-label-tertiary)",
											marginTop: 2
										},
										children: c.hint
									})
								]
							}, c.k))
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("h3", {
						style: {
							fontSize: 13,
							fontWeight: 600,
							color: "var(--dsw-alias-label-secondary)",
							margin: "0 0 8px",
							display: "flex",
							alignItems: "center",
							gap: 6
						},
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "💰" }),
							" 板块资金趋势榜",
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									fontSize: 11,
									fontWeight: 400,
									color: "var(--dsw-alias-label-tertiary)"
								},
								children: "· 行业 · 按今日净流入排序"
							})
						]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						className: "acp-card",
						style: {
							padding: 0,
							overflow: "hidden",
							marginBottom: 16
						},
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: { overflowX: "auto" },
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("table", {
								style: {
									width: "100%",
									fontSize: 13,
									borderCollapse: "collapse"
								},
								children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("thead", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("tr", {
									style: {
										textAlign: "left",
										fontSize: 11,
										color: "var(--dsw-alias-label-tertiary)",
										borderBottom: "1px solid var(--acp-border)"
									},
									children: [
										"行业",
										"涨跌%",
										"今日净流入",
										"流入",
										"流出",
										"家数"
									].map((h) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("th", {
										style: {
											whiteSpace: "nowrap",
											padding: "10px 12px",
											fontWeight: 500
										},
										children: h
									}, h))
								}) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("tbody", { children: MOCK_SECTORS.map((s) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("tr", {
									style: { borderBottom: "1px solid var(--dsw-alias-border-l1, rgba(0,0,0,0.04))" },
									children: [
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
											style: {
												padding: "10px 12px",
												fontWeight: 500,
												color: "var(--dsw-alias-label-primary)"
											},
											children: s.name
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("td", {
											className: pctClass(s.pct),
											style: {
												padding: "10px 12px",
												fontFamily: "monospace",
												fontSize: 12
											},
											children: [
												s.pct > 0 ? "+" : "",
												s.pct.toFixed(2),
												"%"
											]
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("td", {
											className: pctClass(s.net),
											style: {
												padding: "10px 12px",
												fontFamily: "monospace",
												fontSize: 12,
												fontWeight: 600
											},
											children: [
												s.net > 0 ? "+" : "",
												fmt(s.net),
												" 亿"
											]
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
											style: {
												padding: "10px 12px",
												fontFamily: "monospace",
												fontSize: 12,
												color: "var(--dsw-alias-label-secondary)"
											},
											children: fmt(s.inflow)
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
											style: {
												padding: "10px 12px",
												fontFamily: "monospace",
												fontSize: 12,
												color: "var(--dsw-alias-label-secondary)"
											},
											children: fmt(s.outflow)
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("td", {
											style: {
												padding: "10px 12px",
												fontFamily: "monospace",
												fontSize: 12,
												color: "var(--dsw-alias-label-tertiary)"
											},
											children: s.firms
										})
									]
								}, s.name)) })]
							})
						})
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							display: "flex",
							gap: 8,
							border: "1px solid var(--dsw-alias-border-l2)",
							background: "var(--dsw-alias-bg-layer-1)",
							borderRadius: 12,
							padding: 12,
							fontSize: 11,
							lineHeight: 1.6,
							color: "var(--dsw-alias-label-tertiary)",
							marginTop: 8
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "ℹ️" }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "AlphaCopilot 中立呈现客观数据，不荐股、不预测涨跌、不给买卖时机。板块资金为公开净流入统计，非推荐。`每日复盘` 当前为静态 mock，接入 `dsh-alphacopilot-research` REST 后替换为实时数据。" })]
					})
				]
			});
		}
		//#endregion
		//#region src/client/Sidebar.tsx
		function createPageStore(initial = "chat") {
			let page = initial;
			const listeners = /* @__PURE__ */ new Set();
			return {
				get: () => page,
				set: (p) => {
					if (p === page) return;
					page = p;
					for (const fn of listeners) fn();
				},
				subscribe: (fn) => {
					listeners.add(fn);
					return () => listeners.delete(fn);
				}
			};
		}
		const NAV_ITEMS = [{
			id: "chat",
			label: "Agent 对话",
			icon: "💬"
		}, {
			id: "daily-review",
			label: "每日复盘",
			icon: "📊"
		}];
		const FUTURE_ITEMS = [
			{
				id: "chat",
				label: "板块中心",
				icon: "🏢",
				disabled: true
			},
			{
				id: "chat",
				label: "个股数据",
				icon: "📈",
				disabled: true
			},
			{
				id: "chat",
				label: "自选股",
				icon: "⭐",
				disabled: true
			}
		];
		function CustomSidebar({ collapsed, width, startSession, toggleSidebar, t: tProp, renderSlot, pageStore }) {
			const t = tProp ?? ((k) => k);
			const [settled, setSettled] = react.useState(collapsed);
			const [page, setPage] = react.useState(() => pageStore.get());
			react.useEffect(() => pageStore.subscribe(() => setPage(pageStore.get())), [pageStore]);
			react.useEffect(() => {
				if (!collapsed) {
					setSettled(false);
					return;
				}
				const timer = window.setTimeout(() => setSettled(true), 150);
				return () => window.clearTimeout(timer);
			}, [collapsed]);
			const wide = !collapsed || !settled;
			const lastWideWidth = react.useRef(width);
			if (!collapsed) lastWideWidth.current = width;
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				style: {
					display: "flex",
					flexDirection: "column",
					height: "100%",
					background: "var(--dsw-specific-sidebar-fill, var(--dsw-alias-bg-layer-1))",
					borderRight: "1px solid var(--dsw-alias-border-l1)",
					overflow: "hidden",
					width: wide ? collapsed ? lastWideWidth.current : width : void 0
				},
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						style: {
							background: "#f97316",
							color: "#fff",
							fontSize: 10,
							textAlign: "center",
							padding: "2px 0",
							flexShrink: 0
						},
						children: "ACP WEB ✓"
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							display: "flex",
							alignItems: "center",
							height: 48,
							padding: "0 10px",
							gap: 8,
							flexShrink: 0
						},
						children: [wide && /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: () => startSession(),
							style: {
								display: "flex",
								alignItems: "center",
								gap: 8,
								background: "transparent",
								border: "none",
								cursor: "pointer",
								flex: 1,
								minWidth: 0
							},
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									width: 24,
									height: 24,
									display: "inline-flex",
									alignItems: "center",
									justifyContent: "center"
								},
								children: renderSlot("sidebar.brand.mark", { size: 24 }, { fallback: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "🐟" }) })
							}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: {
									fontSize: 13,
									fontWeight: 700,
									color: "var(--dsw-alias-label-primary)",
									whiteSpace: "nowrap"
								},
								children: renderSlot("sidebar.brand.name", {}, { fallback: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "AlphaCopilot" }) })
							})]
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
							type: "button",
							"aria-label": collapsed ? t("toggle.open") : t("toggle.collapse"),
							onClick: () => toggleSidebar(),
							style: {
								width: 28,
								height: 28,
								borderRadius: 8,
								border: "1px solid var(--dsw-alias-border-l2)",
								background: "var(--dsw-alias-bg-layer-2)",
								display: "inline-flex",
								alignItems: "center",
								justifyContent: "center",
								cursor: "pointer",
								flexShrink: 0
							},
							children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
								style: { fontSize: 12 },
								children: collapsed ? "→" : "←"
							})
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						style: {
							padding: "8px 10px",
							flexShrink: 0
						},
						children: /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
							type: "button",
							onClick: () => {
								pageStore.set("chat");
								startSession();
							},
							style: {
								width: "100%",
								height: 36,
								borderRadius: 12,
								border: "1px solid var(--dsw-alias-border-l2)",
								background: "var(--dsw-alias-bg-layer-2)",
								display: "flex",
								alignItems: "center",
								justifyContent: wide ? "flex-start" : "center",
								gap: 8,
								padding: wide ? "0 12px" : 0,
								cursor: "pointer",
								fontSize: 13,
								color: "var(--dsw-alias-label-primary)"
							},
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: "＋" }), wide && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("session.new") })]
						})
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						style: {
							padding: "8px 8px 10px",
							borderBottom: "1px solid var(--dsw-alias-border-l1)",
							flexShrink: 0
						},
						children: !wide ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: {
								display: "flex",
								flexDirection: "column",
								gap: 6,
								alignItems: "center"
							},
							children: NAV_ITEMS.map((it) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("button", {
								type: "button",
								onClick: () => !it.disabled && pageStore.set(it.id),
								title: it.label,
								style: {
									width: 36,
									height: 36,
									borderRadius: 10,
									border: "1px solid transparent",
									background: page === it.id ? "var(--dsw-specific-sidebar-nav-item-active, var(--dsw-alias-bg-layer-2))" : "transparent",
									display: "inline-flex",
									alignItems: "center",
									justifyContent: "center",
									cursor: it.disabled ? "not-allowed" : "pointer",
									opacity: it.disabled ? .5 : 1
								},
								children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
									style: { fontSize: 16 },
									children: it.icon
								})
							}, it.label))
						}) : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							style: {
								display: "flex",
								flexDirection: "column",
								gap: 4
							},
							children: [
								NAV_ITEMS.map((it) => {
									const active = page === it.id;
									return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("button", {
										type: "button",
										onClick: () => !it.disabled && pageStore.set(it.id),
										style: {
											display: "flex",
											alignItems: "center",
											gap: 10,
											width: "100%",
											height: 36,
											borderRadius: 10,
											padding: "0 10px",
											border: "1px solid transparent",
											background: active ? "var(--dsw-specific-sidebar-nav-item-active, var(--dsw-alias-bg-layer-2))" : "transparent",
											color: active ? "var(--dsw-alias-label-primary)" : "var(--dsw-alias-label-secondary)",
											cursor: it.disabled ? "not-allowed" : "pointer",
											fontSize: 13,
											fontWeight: active ? 600 : 400,
											textAlign: "left"
										},
										children: [
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
												style: {
													fontSize: 14,
													width: 18,
													textAlign: "center"
												},
												children: it.icon
											}),
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
												style: {
													flex: 1,
													whiteSpace: "nowrap",
													overflow: "hidden",
													textOverflow: "ellipsis"
												},
												children: it.label
											}),
											active && /* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { style: {
												width: 6,
												height: 6,
												borderRadius: 6,
												background: "var(--dsw-alias-button-info-fill, #4a7cff)",
												flexShrink: 0
											} })
										]
									}, it.label);
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { style: {
									height: 1,
									background: "var(--dsw-alias-border-l1)",
									margin: "6px 0"
								} }),
								FUTURE_ITEMS.map((it) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
									style: {
										display: "flex",
										alignItems: "center",
										gap: 10,
										width: "100%",
										height: 32,
										borderRadius: 10,
										padding: "0 10px",
										color: "var(--dsw-alias-label-tertiary)",
										fontSize: 13,
										opacity: .6
									},
									children: [
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											style: {
												fontSize: 14,
												width: 18,
												textAlign: "center"
											},
											children: it.icon
										}),
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: it.label }),
										/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", {
											style: {
												marginLeft: "auto",
												fontSize: 10,
												background: "var(--dsw-alias-bg-layer-1)",
												border: "1px solid var(--dsw-alias-border-l1)",
												borderRadius: 20,
												padding: "1px 6px"
											},
											children: "soon"
										})
									]
								}, it.label))
							]
						})
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
						style: {
							flex: 1,
							minHeight: 0,
							overflow: "hidden",
							display: "flex",
							flexDirection: "column"
						},
						children: renderSlot("sidebar.workspaces", {
							wide,
							expandSidebar: () => {
								if (collapsed) toggleSidebar();
							}
						})
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						style: {
							flexShrink: 0,
							borderTop: "1px solid var(--dsw-alias-border-l1)",
							padding: "8px 8px",
							display: "flex",
							flexDirection: "column",
							gap: 6
						},
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
							style: {
								display: "flex",
								gap: 6,
								justifyContent: wide ? "flex-start" : "center"
							},
							children: renderSlot("sidebar.footer.action", { wide })
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children: renderSlot("sidebar.settings", { wide }) })]
					})
				]
			});
		}
		//#endregion
		//#region src/client/index.ts
		const inject = [
			"slots",
			"layout",
			"sessions",
			"workspaces",
			"locale"
		];
		function apply(ctx) {
			console.log("[acp-web] apply: registering sidebar + overlay");
			const store = createPageStore("chat");
			ctx.effect(() => {
				const style = document.createElement("style");
				style.dataset.plugin = "dsh-alphacopilot-web/theme";
				style.textContent = `:root{--acp-up:var(--dsw-static-red-500, #e5484d);--acp-down:var(--dsw-static-green-500, #30a46c);}`;
				document.head.appendChild(style);
				return () => {
					style.remove();
				};
			}, "acp theme vars");
			ctx.slots.inject("sidebar", () => {
				return ctx.slots.register({
					name: "sidebar",
					priority: -10,
					inject: () => ({
						startSession: () => ctx.workspaces?.startSession?.(),
						toggleSidebar: () => ctx.layout?.toggleSidebar?.()
					})
				}, (props) => react.createElement(CustomSidebar, {
					...props,
					pageStore: store
				}));
			});
			ctx.slots.inject("shell.overlay", () => {
				return ctx.slots.register({
					name: "shell.overlay",
					id: "acp-daily-review",
					order: 10
				}, () => react.createElement(OverlayPage, { store }));
			});
		}
		function OverlayPage({ store }) {
			const [page, setPage] = react.useState(() => store.get());
			react.useEffect(() => store.subscribe(() => setPage(store.get())), [store]);
			if (page !== "daily-review") return null;
			return react.createElement("div", {
				style: {
					position: "absolute",
					inset: 0,
					left: 240,
					background: "var(--dsw-alias-bg-base, #f6f7f8)",
					overflowY: "auto",
					pointerEvents: "auto",
					zIndex: 5,
					borderLeft: "1px solid var(--dsw-alias-border-l1)"
				},
				onClick: (e) => e.stopPropagation()
			}, react.createElement("div", { style: {
				maxWidth: 960,
				margin: "0 auto",
				padding: "20px 24px 32px"
			} }, react.createElement("div", { style: {
				display: "flex",
				justifyContent: "flex-end",
				marginBottom: 8
			} }, react.createElement("button", {
				type: "button",
				onClick: () => store.set("chat"),
				style: {
					fontSize: 12,
					padding: "6px 12px",
					borderRadius: 20,
					border: "1px solid var(--dsw-alias-border-l2)",
					background: "var(--dsw-alias-bg-layer-2)",
					color: "var(--dsw-alias-label-secondary)",
					cursor: "pointer"
				}
			}, "← 返回对话")), react.createElement(DailyReviewPage, null)));
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
