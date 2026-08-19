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
import { AreaChart as AreaIcon, BarChart3, LineChart as LineIcon, PieChart as PieIcon, TrendingUp } from 'lucide-react'

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

const COLORS = ['#38bdf8', '#818cf8', '#c084fc', '#34d399', '#fbbf24', '#f87171', '#60a5fa', '#f472b6']

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
  // IMPORTANT: hooks must run on every render — the old component returned
  // early *before* useState, which crashed React ("rendered fewer hooks than
  // expected") as soon as a chart-less answer followed a chart answer.
  const rows = Array.isArray(payload?.data) ? payload.data : []
  const [activeType, setActiveType] = useState<ChartType>(payload?.chartType || 'bar')

  const { xKey, yKey } = useMemo(() => {
    const first = rows[0] ?? {}
    const keys = Object.keys(first)
    const x = payload?.xKey && keys.includes(payload.xKey)
      ? payload.xKey
      : keys.find((k) => typeof first[k] === 'string') || keys[0]
    const y = payload?.yKey && keys.includes(payload.yKey)
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
    [rows, yKey],
  )

  if (!payload || data.length === 0 || !xKey || !yKey) return null

  const axisColor = 'var(--chart-axis)'
  const gridColor = 'var(--chart-grid)'

  const CustomTooltip = ({ active, payload: tooltipPayload, label }: any) => {
    if (!active || !tooltipPayload?.length) return null
    const value = tooltipPayload[0].value
    const name = tooltipPayload[0].payload?.[xKey] ?? label
    return (
      <div className="chart-tooltip">
        <p className="chart-tooltip-label">{String(name)}</p>
        <p className="chart-tooltip-value">
          {humanise(yKey)}: {typeof value === 'number' && !Number.isNaN(value) ? value.toLocaleString() : String(value ?? '')}
        </p>
      </div>
    )
  }

  const axisProps = {
    stroke: axisColor,
    fontSize: 11,
    tickLine: false,
  } as const

  return (
    <div className="chart-card">
      <div className="chart-card-head">
        <div>
          <span className="data-label">
            <TrendingUp size={13} /> {payload.category || 'ANALYTICS VISUALIZATION'}
          </span>
          <strong>{payload.title || `${humanise(yKey)} by ${humanise(xKey)}`}</strong>
          {payload.aggregated && payload.sourceRows ? (
            <span className="chart-subtitle">
              {payload.points} groups aggregated from {payload.sourceRows.toLocaleString()} rows
            </span>
          ) : null}
        </div>

        <div className="chart-switcher" role="group" aria-label="Chart type">
          {CHART_TYPES.map((type) => (
            <button
              key={type.id}
              onClick={() => setActiveType(type.id)}
              className={activeType === type.id ? 'active' : ''}
              aria-pressed={activeType === type.id}
            >
              {type.icon} {type.label}
            </button>
          ))}
        </div>
      </div>

      {/* explicit height: ResponsiveContainer measures 0px inside a flex parent */}
      <div style={{ width: '100%', height: 280, minHeight: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          {activeType === 'bar' ? (
            <BarChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: 24 }}>
              <defs>
                <linearGradient id="ciraBarGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.95} />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity={0.45} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey={xKey} {...axisProps} dy={8} interval="preserveStartEnd" angle={data.length > 8 ? -20 : 0} textAnchor={data.length > 8 ? 'end' : 'middle'} height={data.length > 8 ? 60 : 30} />
              <YAxis {...axisProps} tickFormatter={compact} width={64} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(125, 165, 255, 0.08)' }} />
              <Bar dataKey={yKey} fill="url(#ciraBarGradient)" radius={[8, 8, 0, 0]} maxBarSize={64} />
            </BarChart>
          ) : activeType === 'line' ? (
            <LineChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey={xKey} {...axisProps} dy={8} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={compact} width={64} />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey={yKey}
                stroke="#38bdf8"
                strokeWidth={3}
                dot={data.length <= 30 ? { fill: '#38bdf8', r: 3 } : false}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          ) : activeType === 'area' ? (
            <AreaChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: 24 }}>
              <defs>
                <linearGradient id="ciraAreaGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.7} />
                  <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey={xKey} {...axisProps} dy={8} interval="preserveStartEnd" />
              <YAxis {...axisProps} tickFormatter={compact} width={64} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey={yKey} stroke="#38bdf8" strokeWidth={2} fill="url(#ciraAreaGradient)" />
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
                outerRadius={92}
                innerRadius={52}
                paddingAngle={3}
              >
                {data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Legend
                formatter={(value) => <span className="chart-legend-label">{String(value)}</span>}
                wrapperStyle={{ fontSize: 11, maxHeight: 72, overflowY: 'auto' }}
              />
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default ChartCard
