/** chart/plot 会话事件族类型定义。*/
export interface ChartPlotData {
  chartId: string
  title: string
  norm?: 'abs' | 'pct_change' | 'normalize'
  series: Array<{
    code: string
    name: string
    points: Array<{ t: string; v: number }>
  }>
}

export interface ChartPlotStartEvent {
  type: 'chart/plot'
  data: ChartPlotData
}
