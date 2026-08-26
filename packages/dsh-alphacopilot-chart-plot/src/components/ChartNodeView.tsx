/** ECharts-based chart renderer for dsh chat flow. */
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

interface ChartNodeViewProps {
  node: {
    data: { title: string; series: Array<{ code: string; name: string; points: Array<{ t: string; v: number }> }> }
  }
}

export function ChartNodeView({ node }: ChartNodeViewProps) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current)
    }
    const { title, series } = node.data
    chartRef.current.setOption({
      title: { text: title },
      tooltip: { trigger: 'axis' },
      legend: { data: series.map(s => s.name) },
      xAxis: { type: 'category', data: series[0]?.points?.map(p => p.t) ?? [] },
      yAxis: { type: 'value' },
      series: series.map(s => ({ name: s.name, type: 'line', data: s.points.map(p => p.v) })),
    })
    return () => chartRef.current?.dispose()
  }, [node.data])

  return <div ref={ref} style={{ width: '100%', height: 300 }} />
}
