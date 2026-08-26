'use client'

import React, { useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AreaChart as AreaIcon,
  BarChart3,
  LineChart as LineIcon,
  PieChart as PieIcon,
  TrendingUp,
  Maximize2,
  X,
} from 'lucide-react'

export type ChartType = 'bar' | 'line' | 'pie' | 'area'

export interface ChartPayload {
  chartType?: ChartType
  title?: string
  data: Array<Record<string, any>>
  xKey?: string
  yKey?: string
  category?: string
  aggregated?: boolean
  points?: number
  sourceRows?: number
}

/* Vibrant Neon Palette — high contrast, stunning, modern */
const COLORS = [
  '#ff007f', /* Neon Pink */
  '#00f0ff', /* Electric Cyan */
  '#8a2be2', /* Neon Purple */
  '#39ff14', /* Lime Green */
  '#ffae42', /* Bright Amber */
  '#ff003c', /* Laser Red */
  '#9d00ff', /* Deep Neon Violet */
  '#00ff9d', /* Mint Neon */
]

const CHART_TYPES: Array<{ id: ChartType; label: string; icon: React.ReactNode }> = [
  { id: 'bar', label: 'Bar', icon: <BarChart3 size={13} /> },
  { id: 'line', label: 'Line', icon: <LineIcon size={13} /> },
  { id: 'area', label: 'Area', icon: <AreaIcon size={13} /> },
  { id: 'pie', label: 'Pie', icon: <PieIcon size={13} /> },
]

function compact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(Math.round(value * 100) / 100)
}

function humanise(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
}

export function ChartCard({ payload }: { payload: ChartPayload }) {
  const rows = Array.isArray(payload?.data) ? payload.data : []
  const [activeType, setActiveType] = useState<ChartType>(payload?.chartType || 'bar')
  const [isExpanded, setIsExpanded] = useState(false)

  const { xKey, yKey } = useMemo(() => {
    const first = rows[0] ?? {}
    const keys = Object.keys(first)
    const x =
      payload?.xKey && keys.includes(payload.xKey)
        ? payload.xKey
        : keys.find((k) => typeof first[k] === 'string') || keys[0]
    const y =
      payload?.yKey && keys.includes(payload.yKey)
        ? payload.yKey
        : keys.find((k) => typeof first[k] === 'number' && k !== x) || keys[1] || keys[0]
    return { xKey: x, yKey: y }
  }, [rows, payload?.xKey, payload?.yKey])

  const data = useMemo(
    () =>
      rows.map((row) => ({
        ...row,
        [yKey]: typeof row[yKey] === 'string' ? Number(row[yKey]) || 0 : row[yKey],
      })),
    [rows, yKey]
  )

  if (!payload || data.length === 0 || !xKey || !yKey) return null

  const CustomTooltip = ({ active, payload: tooltipPayload, label }: any) => {
    if (!active || !tooltipPayload?.length) return null
    const value = tooltipPayload[0].value
    const name = tooltipPayload[0].payload?.[xKey] ?? label
    return (
      <div className="bg-popover border border-border/80 text-popover-foreground px-3 py-2 rounded-xl shadow-xl text-xs font-semibold">
        <p className="font-bold text-foreground">{String(name)}</p>
        <p className="text-muted-foreground mt-0.5">
          {humanise(yKey)}:{' '}
          <span className="text-indigo-500 font-bold">
            {typeof value === 'number' && !Number.isNaN(value)
              ? value.toLocaleString()
              : String(value ?? '')}
          </span>
        </p>
      </div>
    )
  }

  const axisProps = {
    stroke: 'currentColor',
    className: 'text-muted-foreground/60 text-[11px]',
    tickLine: false,
  } as const

  const renderChart = (expanded: boolean) => {
    const shouldHideTicks = !expanded && data.length > 8
    const xAxisProps = expanded
      ? { tick: true, angle: -45, textAnchor: 'end' as const, height: 80, interval: 0 as const }
      : { tick: shouldHideTicks ? false : undefined, height: shouldHideTicks ? 10 : 30 }

    return (
      <ResponsiveContainer width="100%" height="100%">
        {activeType === 'bar' ? (
          <BarChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={50} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(99, 102, 241, 0.08)' }} />
            <Bar dataKey={yKey} fill="#818cf8" radius={[6, 6, 0, 0]} maxBarSize={expanded ? 80 : 52} />
          </BarChart>
        ) : activeType === 'line' ? (
          <LineChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={50} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey={yKey}
              stroke="#818cf8"
              strokeWidth={3}
              dot={data.length <= (expanded ? 60 : 30) ? { fill: '#818cf8', r: expanded ? 5 : 3, strokeWidth: 0 } : false}
              activeDot={{ r: expanded ? 8 : 6, fill: '#fb7185' }}
            />
          </LineChart>
        ) : activeType === 'area' ? (
          <AreaChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 20 }}>
            <defs>
              <linearGradient id="areaChartGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#818cf8" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#818cf8" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border/40" vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={50} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey={yKey} stroke="#818cf8" strokeWidth={2.5} fill="url(#areaChartGrad)" />
          </AreaChart>
        ) : (
          <PieChart>
            <Tooltip content={<CustomTooltip />} />
            <Pie
              data={data}
              dataKey={yKey}
              nameKey={xKey}
              cx="50%"
              cy="50%"
              outerRadius={expanded ? 180 : 85}
              innerRadius={expanded ? 100 : 45}
              paddingAngle={3}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Legend
              formatter={(value) => <span className="text-xs font-semibold text-foreground">{String(value)}</span>}
              wrapperStyle={{ fontSize: expanded ? 13 : 11, maxHeight: expanded ? 120 : 64, overflowY: 'auto' }}
            />
          </PieChart>
        )}
      </ResponsiveContainer>
    )
  }

  return (
    <>
      <div 
        className="chart-card-wrapper bg-white rounded-2xl shadow-lg border border-gray-100 w-full flex flex-col justify-between animate-fade-in text-gray-900 overflow-hidden transform hover:-rotate-1 hover:-translate-y-2 hover:shadow-xl transition-all duration-300"
        style={{ animationFillMode: 'both', animationDelay: '200ms' }}
      >
        <div className="bg-gradient-to-r from-rose-400 to-red-400 px-4 py-3 flex items-center justify-between text-white">
          <div>
            <span className="text-[10px] font-extrabold tracking-wider uppercase text-rose-100 flex items-center gap-1">
              <TrendingUp size={11} className="text-white" /> {payload.category || 'ANALYTICS'}
            </span>
            <strong className="text-xs md:text-sm font-black text-white line-clamp-1">
              {payload.title || `${humanise(yKey)} by ${humanise(xKey)}`}
            </strong>
          </div>

          <div className="flex items-center gap-1.5">
            <div className="flex items-center bg-black/10 p-0.5 rounded-xl border border-white/20 shadow-inner">
              {CHART_TYPES.map((type) => (
                <button
                  key={type.id}
                  onClick={() => setActiveType(type.id)}
                  className={`px-2 py-1 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    activeType === type.id
                      ? 'bg-white text-rose-600 shadow-sm'
                      : 'text-rose-100 hover:text-white'
                  }`}
                  title={type.label}
                >
                  {type.icon}
                </button>
              ))}
            </div>
            <button
              onClick={() => setIsExpanded(true)}
              className="p-1.5 rounded-xl text-rose-100 hover:text-white hover:bg-white/20 transition-colors"
              title="Expand chart"
            >
              <Maximize2 size={13} />
            </button>
          </div>
        </div>
        
        <div className="p-4">

        <div className="w-full h-[220px] min-h-[180px]">
          {renderChart(false)}
        </div>
        </div>
      </div>

      {/* Expanded Modal */}
      {isExpanded && (
        <div
          className="fixed inset-0 z-[100] bg-white animate-in fade-in flex flex-col p-6 md:p-10"
        >
          <div className="w-full max-w-7xl mx-auto flex flex-col h-full space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <h3 className="text-xl md:text-2xl font-black text-gray-900">
                {payload.title || `${humanise(yKey)} by ${humanise(xKey)}`}
              </h3>
              <button
                onClick={() => setIsExpanded(false)}
                className="p-2 rounded-xl hover:bg-gray-100 text-gray-400 hover:text-gray-900 transition-colors"
                title="Close fullscreen"
              >
                <X size={24} />
              </button>
            </div>
            <div className="flex-1 w-full flex items-center justify-center">
              <div className="w-full h-full max-h-[70vh]">
                {renderChart(true)}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default ChartCard
