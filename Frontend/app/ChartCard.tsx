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
import { AreaChart as AreaIcon, BarChart3, LineChart as LineIcon, PieChart as PieIcon, TrendingUp, Maximize2, X } from 'lucide-react'

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

const COLORS = ['#c4b5fd', '#f9a8d4', '#fbbf24', '#86efac', '#93c5fd', '#fda4af', '#a5b4fc', '#fdba74']

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
        <p className="chart-tooltip-label" style={{ color: 'var(--foreground)' }}>{String(name)}</p>
        <p className="chart-tooltip-value" style={{ color: 'var(--muted-foreground)' }}>
          {humanise(yKey)}: {typeof value === 'number' && !Number.isNaN(value) ? value.toLocaleString() : String(value ?? '')}
        </p>
      </div>
    )
  }

  const axisProps = {
    stroke: 'var(--muted-foreground)',
    fontSize: 11,
    tickLine: false,
  } as const

  const renderChart = (expanded: boolean) => {
    const shouldHideTicks = !expanded && data.length > 8
    const xAxisProps = expanded 
      ? { tick: true, angle: -45, textAnchor: 'end', height: 80, interval: 0 as const } 
      : { tick: shouldHideTicks ? false : undefined, height: shouldHideTicks ? 10 : 30 }

    return (
      <ResponsiveContainer width="100%" height="100%">
        {activeType === 'bar' ? (
          <BarChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 24 }}>
            <defs>
              <linearGradient id={`ciraBarGradient-${expanded ? 'exp' : 'norm'}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#c4b5fd" stopOpacity={0.9} />
                <stop offset="100%" stopColor="#f9a8d4" stopOpacity={0.45} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={64} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--secondary)' }} />
            <Bar dataKey={yKey} fill={`url(#ciraBarGradient-${expanded ? 'exp' : 'norm'})`} radius={[8, 8, 0, 0]} maxBarSize={expanded ? 100 : 64} />
          </BarChart>
        ) : activeType === 'line' ? (
          <LineChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={64} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey={yKey}
              stroke="#a78bfa"
              strokeWidth={3}
              dot={data.length <= (expanded ? 60 : 30) ? { fill: '#a78bfa', r: expanded ? 5 : 3 } : false}
              activeDot={{ r: expanded ? 8 : 6 }}
            />
          </LineChart>
        ) : activeType === 'area' ? (
          <AreaChart data={data} margin={{ top: 10, right: 12, left: 4, bottom: expanded ? 40 : 24 }}>
            <defs>
              <linearGradient id={`ciraAreaGradient-${expanded ? 'exp' : 'norm'}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#c4b5fd" stopOpacity={0.6} />
                <stop offset="100%" stopColor="#c4b5fd" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey={xKey} {...axisProps} dy={8} {...xAxisProps} />
            <YAxis {...axisProps} tickFormatter={compact} width={64} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey={yKey} stroke="#a78bfa" strokeWidth={2} fill={`url(#ciraAreaGradient-${expanded ? 'exp' : 'norm'})`} />
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
              outerRadius={expanded ? 200 : 110}
              innerRadius={expanded ? 120 : 60}
              paddingAngle={3}
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Legend
              formatter={(value) => <span className="chart-legend-label" style={{ color: 'var(--foreground)' }}>{String(value)}</span>}
              wrapperStyle={{ fontSize: expanded ? 14 : 11, maxHeight: expanded ? 120 : 72, overflowY: 'auto' }}
            />
          </PieChart>
        )}
      </ResponsiveContainer>
    )
  }

  return (
    <>
      <div className="chart-card">
        <div className="chart-card-head">
          <div>
            <span className="data-label">
              <TrendingUp size={13} /> {payload.category || 'ANALYTICS VISUALIZATION'}
            </span>
            <strong style={{ color: 'var(--foreground)' }}>{payload.title || `${humanise(yKey)} by ${humanise(xKey)}`}</strong>
            {payload.aggregated && payload.sourceRows ? (
              <span className="chart-subtitle">
                {payload.points} groups aggregated from {payload.sourceRows.toLocaleString()} rows
              </span>
            ) : null}
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
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
            <button 
              className="icon-button" 
              onClick={() => setIsExpanded(true)}
              aria-label="Expand chart"
              style={{ width: 32, height: 32 }}
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </div>

        {/* flex: 1 allows the container to stretch and match the data card height */}
        <div style={{ width: '100%', flex: 1, minHeight: 280 }}>
          {renderChart(false)}
        </div>
      </div>

      {isExpanded && (
        <div className="chart-modal-overlay" onClick={() => setIsExpanded(false)}>
          <div className="chart-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="chart-modal-header">
              <h3>{payload.title || `${humanise(yKey)} by ${humanise(xKey)}`}</h3>
              <button className="icon-button" onClick={() => setIsExpanded(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="chart-modal-body">
              {renderChart(true)}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default ChartCard
