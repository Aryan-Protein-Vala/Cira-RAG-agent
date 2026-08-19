'use client';

import React, { useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from 'recharts';
import { BarChart3, LineChart as LineIcon, PieChart as PieIcon, TrendingUp } from 'lucide-react';

export interface ChartPayload {
  chartType?: 'bar' | 'line' | 'pie' | 'area';
  title?: string;
  data: Array<Record<string, any>>;
  xKey?: string;
  yKey?: string;
  category?: string;
}

const COLORS = ['#38bdf8', '#818cf8', '#c084fc', '#34d399', '#fbbf24', '#f87171'];

export function ChartCard({ payload }: { payload: ChartPayload }) {
  if (!payload || !payload.data || payload.data.length === 0) return null;

  const initialType = payload.chartType || 'bar';
  const [activeType, setActiveType] = useState<'bar' | 'line' | 'pie' | 'area'>(initialType);

  // Auto-detect keys if not provided
  const keys = Object.keys(payload.data[0]);
  const xKey = payload.xKey || keys.find(k => typeof payload.data[0][k] === 'string') || keys[0];
  const yKey = payload.yKey || keys.find(k => typeof payload.data[0][k] === 'number') || keys[1] || keys[0];

  const CustomTooltip = ({ active, payload: tooltipPayload, label }: any) => {
    if (active && tooltipPayload && tooltipPayload.length) {
      return (
        <div style={{
          background: 'rgba(25, 25, 30, 0.9)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: '12px',
          padding: '10px 14px',
          color: '#fff',
          boxShadow: '0 10px 25px rgba(0,0,0,0.5)',
          fontSize: '12px',
          lineHeight: '1.4'
        }}>
          <p style={{ margin: '0 0 4px', fontWeight: 600, color: 'rgba(255, 255, 255, 0.7)' }}>{label}</p>
          <p style={{ margin: 0, fontWeight: 700, color: '#38bdf8' }}>
            {yKey}: {Number(tooltipPayload[0].value).toLocaleString()}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="chart-card" style={{
      width: 'min(680px, 100%)',
      marginTop: '16px',
      padding: '20px',
      borderRadius: '20px',
      background: 'rgba(255, 255, 255, 0.04)',
      border: '1px solid rgba(255, 255, 255, 0.1)',
      backdropFilter: 'blur(16px)',
      boxShadow: '0 12px 30px rgba(0, 0, 0, 0.25), inset 0 1px 1px rgba(255, 255, 255, 0.15)',
      transition: 'all 0.25s ease'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '18px',
        flexWrap: 'wrap',
        gap: '10px'
      }}>
        <div>
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            color: '#38bdf8',
            fontSize: '10px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.15em'
          }}>
            <TrendingUp size={13} /> {payload.category || 'ANALYTICS VISUALIZATION'}
          </span>
          <strong style={{ display: 'block', fontSize: '15px', fontWeight: 600, marginTop: '4px', color: '#fff' }}>
            {payload.title || `${yKey} by ${xKey}`}
          </strong>
        </div>

        {/* Chart View Switcher */}
        <div style={{
          display: 'flex',
          gap: '4px',
          background: 'rgba(0, 0, 0, 0.25)',
          padding: '4px',
          borderRadius: '10px',
          border: '1px solid rgba(255, 255, 255, 0.08)'
        }}>
          <button
            onClick={() => setActiveType('bar')}
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              border: 'none',
              background: activeType === 'bar' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
              color: activeType === 'bar' ? '#38bdf8' : 'rgba(255, 255, 255, 0.6)',
              cursor: 'var(--cursor-pointer)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontWeight: 600
            }}
          >
            <BarChart3 size={13} /> Bar
          </button>
          <button
            onClick={() => setActiveType('line')}
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              border: 'none',
              background: activeType === 'line' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
              color: activeType === 'line' ? '#38bdf8' : 'rgba(255, 255, 255, 0.6)',
              cursor: 'var(--cursor-pointer)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontWeight: 600
            }}
          >
            <LineIcon size={13} /> Line
          </button>
          <button
            onClick={() => setActiveType('pie')}
            style={{
              padding: '6px 10px',
              borderRadius: '8px',
              border: 'none',
              background: activeType === 'pie' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
              color: activeType === 'pie' ? '#38bdf8' : 'rgba(255, 255, 255, 0.6)',
              cursor: 'var(--cursor-pointer)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontWeight: 600
            }}
          >
            <PieIcon size={13} /> Pie
          </button>
        </div>
      </div>

      {/* Chart Canvas */}
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          {activeType === 'bar' ? (
            <BarChart data={payload.data} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
              <defs>
                <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.9} />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity={0.4} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.05)" vertical={false} />
              <XAxis dataKey={xKey} stroke="rgba(255, 255, 255, 0.4)" fontSize={11} tickLine={false} dy={8} />
              <YAxis stroke="rgba(255, 255, 255, 0.4)" fontSize={11} tickLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255, 255, 255, 0.03)' }} />
              <Bar dataKey={yKey} fill="url(#barGradient)" radius={[8, 8, 0, 0]} />
            </BarChart>
          ) : activeType === 'line' ? (
            <LineChart data={payload.data} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.05)" vertical={false} />
              <XAxis dataKey={xKey} stroke="rgba(255, 255, 255, 0.4)" fontSize={11} tickLine={false} dy={8} />
              <YAxis stroke="rgba(255, 255, 255, 0.4)" fontSize={11} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey={yKey}
                stroke="#38bdf8"
                strokeWidth={3}
                dot={{ fill: '#38bdf8', r: 4, stroke: '#fff', strokeWidth: 2 }}
                activeDot={{ r: 7, fill: '#38bdf8', stroke: '#fff', strokeWidth: 2 }}
              />
            </LineChart>
          ) : (
            <PieChart>
              <Tooltip content={<CustomTooltip />} />
              <Pie
                data={payload.data}
                dataKey={yKey}
                nameKey={xKey}
                cx="50%"
                cy="50%"
                outerRadius={90}
                innerRadius={50}
                paddingAngle={4}
              >
                {payload.data.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Legend
                formatter={(val) => <span style={{ color: 'rgba(255, 255, 255, 0.7)', fontSize: '11px' }}>{val}</span>}
              />
            </PieChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
