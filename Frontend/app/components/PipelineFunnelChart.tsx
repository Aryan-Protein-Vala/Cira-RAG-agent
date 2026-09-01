'use client'

import React, { useState } from 'react'

interface FunnelPoint {
  stage: string
  active: number
  rejected: number
  total: number
}

const DEFAULT_FUNNEL_DATA: FunnelPoint[] = [
  { stage: 'Applied', active: 180, rejected: 340, total: 520 },
  { stage: 'Screening', active: 1255, rejected: 328, total: 1583 },
  { stage: 'Interview', active: 95, rejected: 210, total: 305 },
  { stage: 'Offer', active: 28, rejected: 45, total: 73 },
  { stage: 'Hired', active: 10, rejected: 8, total: 18 },
]

export function PipelineFunnelChart({ data = DEFAULT_FUNNEL_DATA }: { data?: FunnelPoint[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(1) // Default to peak (Screening)

  // SVG dimensions
  const width = 640
  const height = 240
  const paddingX = 45
  const paddingY = 40
  const chartW = width - paddingX * 2
  const chartH = height - paddingY * 2

  const maxVal = 1400

  // Points for Active Curve (smooth bell curve peaking at Screening)
  // Stage coordinates along X
  const step = chartW / (data.length - 1)
  const activePoints = data.map((d, i) => ({
    x: paddingX + i * step,
    y: height - paddingY - (d.active / maxVal) * chartH,
    val: d.active,
    stage: d.stage,
  }))

  // Points for Rejected Wave (oscillating wavy ribbon across the top)
  const rejectedPoints = [
    { x: paddingX, y: 72 },
    { x: paddingX + step * 0.4, y: 64 },
    { x: paddingX + step * 1.0, y: 60 },
    { x: paddingX + step * 1.5, y: 76 },
    { x: paddingX + step * 2.0, y: 62 },
    { x: paddingX + step * 2.5, y: 70 },
    { x: paddingX + step * 3.0, y: 64 },
    { x: paddingX + step * 3.5, y: 72 },
    { x: paddingX + step * 4.0, y: 66 },
  ]

  // Generate smooth SVG Catmull-Rom or Cubic Bezier path
  const generateSmoothPath = (pts: { x: number; y: number }[]) => {
    if (pts.length === 0) return ''
    let d = `M ${pts[0].x} ${pts[0].y}`
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i === 0 ? 0 : i - 1]
      const p1 = pts[i]
      const p2 = pts[i + 1]
      const p3 = pts[i + 2] || p2
      const cp1x = p1.x + (p2.x - p0.x) / 6
      const cp1y = p1.y + (p2.y - p0.y) / 6
      const cp2x = p2.x - (p3.x - p1.x) / 6
      const cp2y = p2.y - (p3.y - p1.y) / 6
      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`
    }
    return d
  }

  // Active Bell Curve with high peak at index 1
  const activePath = `M ${activePoints[0].x} ${activePoints[0].y} 
    C ${activePoints[0].x + 40} ${activePoints[0].y}, ${activePoints[1].x - 60} ${activePoints[1].y}, ${activePoints[1].x} ${activePoints[1].y}
    C ${activePoints[1].x + 60} ${activePoints[1].y}, ${activePoints[2].x - 40} ${activePoints[2].y}, ${activePoints[2].x} ${activePoints[2].y}
    C ${activePoints[2].x + 40} ${activePoints[2].y}, ${activePoints[3].x - 40} ${activePoints[3].y}, ${activePoints[3].x} ${activePoints[3].y}
    C ${activePoints[3].x + 40} ${activePoints[3].y}, ${activePoints[4].x - 30} ${activePoints[4].y}, ${activePoints[4].x} ${activePoints[4].y}`

  const activeFillPath = `${activePath} L ${activePoints[activePoints.length - 1].x} ${height - paddingY} L ${activePoints[0].x} ${height - paddingY} Z`

  const rejectedPath = generateSmoothPath(rejectedPoints)
  const rejectedFillPath = `${rejectedPath} L ${rejectedPoints[rejectedPoints.length - 1].x} 115 C ${paddingX + step * 2.5} 125, ${paddingX + step * 1} 120, ${paddingX} 115 Z`

  const peakPoint = activePoints[1] // Screening peak

  return (
    <div className="pipeline-funnel-card relative w-full overflow-hidden rounded-2xl bg-card p-5 shadow-md">
      {/* Header with Title and Legend Pills */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-base font-bold tracking-tight text-foreground">Pipeline Funnel</h3>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 shadow-sm" />
            <span>Active</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400 shadow-sm" />
            <span>Rejected</span>
          </div>
        </div>
      </div>

      {/* SVG Canvas */}
      <div className="relative w-full h-[220px]">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full overflow-visible select-none"
          preserveAspectRatio="none"
        >
          <defs>
            {/* Active Gradient Fill */}
            <linearGradient id="activeFunnelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#818cf8" stopOpacity="0.45" />
              <stop offset="60%" stopColor="#c084fc" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#e0e7ff" stopOpacity="0.02" />
            </linearGradient>

            {/* Rejected Gradient Fill */}
            <linearGradient id="rejectedFunnelGrad" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#fb7185" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#fda4af" stopOpacity="0.04" />
            </linearGradient>

            {/* Glowing drop shadow */}
            <filter id="waveGlow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="3" stdDeviation="3" floodColor="#6366f1" floodOpacity="0.3" />
            </filter>
            <filter id="roseGlow" x="-10%" y="-10%" width="120%" height="120%">
              <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#f43f5e" floodOpacity="0.2" />
            </filter>
          </defs>

          {/* Grid lines (horizontal baseline) */}
          <line
            x1={paddingX}
            y1={height - paddingY}
            x2={width - paddingX}
            y2={height - paddingY}
            stroke="currentColor"
            className="text-border/60"
            strokeWidth="1"
          />

          {/* Rejected Wave Fill & Stroke */}
          <path d={rejectedFillPath} fill="url(#rejectedFunnelGrad)" />
          <path
            d={rejectedPath}
            fill="none"
            stroke="#fb7185"
            strokeWidth="2.5"
            strokeLinecap="round"
            filter="url(#roseGlow)"
          />

          {/* Active Curve Fill & Stroke */}
          <path d={activeFillPath} fill="url(#activeFunnelGrad)" />
          <path
            d={activePath}
            fill="none"
            stroke="#6366f1"
            strokeWidth="3.5"
            strokeLinecap="round"
            filter="url(#waveGlow)"
          />

          {/* Dashed vertical indicator line at peak */}
          <line
            x1={peakPoint.x}
            y1={peakPoint.y}
            x2={peakPoint.x}
            y2={height - paddingY}
            stroke="#6366f1"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            opacity="0.8"
          />

          {/* Peak Value Pill (1255 badge matching Reference Image 1) */}
          <g transform={`translate(${peakPoint.x}, ${peakPoint.y - 12})`}>
            {/* Pill Container */}
            <rect
              x="-24"
              y="-14"
              width="48"
              height="24"
              rx="12"
              fill="#524eee"
              className="filter drop-shadow-md"
            />
            {/* Pill Text */}
            <text
              x="0"
              y="2"
              textAnchor="middle"
              fill="#ffffff"
              fontSize="12"
              fontWeight="700"
              fontFamily="sans-serif"
            >
              1255
            </text>
            {/* Pulsing Dot */}
            <circle cx="0" cy="14" r="3.5" fill="#6366f1" stroke="#ffffff" strokeWidth="1.5" />
          </g>

          {/* Interactive Stage Points */}
          {activePoints.map((pt, idx) => (
            <g
              key={pt.stage}
              className="cursor-pointer group"
              onMouseEnter={() => setHoveredIndex(idx)}
            >
              {/* Hover highlight circle */}
              {hoveredIndex === idx && idx !== 1 && (
                <circle
                  cx={pt.x}
                  cy={pt.y}
                  r="6"
                  fill="#818cf8"
                  stroke="#ffffff"
                  strokeWidth="2"
                  className="animate-ping origin-center"
                />
              )}
              {idx !== 1 && (
                <circle
                  cx={pt.x}
                  cy={pt.y}
                  r="4"
                  fill={hoveredIndex === idx ? '#4f46e5' : '#818cf8'}
                  stroke="#ffffff"
                  strokeWidth="1.5"
                />
              )}

              {/* Stage Label on X-Axis */}
              <text
                x={pt.x}
                y={height - 12}
                textAnchor="middle"
                className={`text-[12px] font-semibold transition-colors ${
                  hoveredIndex === idx
                    ? 'fill-foreground font-bold'
                    : 'fill-muted-foreground/80'
                }`}
              >
                {pt.stage}
              </text>
            </g>
          ))}
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredIndex !== null && hoveredIndex !== 1 && (
          <div
            className="absolute -top-1 pointer-events-none px-2.5 py-1 rounded-lg bg-popover text-popover-foreground text-xs font-semibold shadow-xl transition-all -translate-x-1/2 flex items-center gap-2"
            style={{
              left: `${(activePoints[hoveredIndex].x / width) * 100}%`,
            }}
          >
            <span>{data[hoveredIndex].stage}:</span>
            <span className="text-indigo-500 font-bold">{data[hoveredIndex].active}</span>
            <span className="text-muted-foreground text-[10px]">({data[hoveredIndex].rejected} rej)</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default PipelineFunnelChart
