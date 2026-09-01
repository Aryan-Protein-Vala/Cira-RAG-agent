'use client'

import React from 'react'
import {
  Users,
  Award,
  XCircle,
  CheckCircle2,
  Calendar,
  MoreHorizontal,
  TrendingUp,
  Briefcase,
  Layers,
  Sparkles,
} from 'lucide-react'
import PipelineFunnelChart from './PipelineFunnelChart'

interface DashboardOverviewProps {
  onQuickQuery?: (query: string) => void
  onNavigateTab?: (tab: 'dashboard' | 'database' | 'chat') => void
}

export function DashboardOverview({
  onQuickQuery,
  onNavigateTab,
}: DashboardOverviewProps) {
  return (
    <div className="dashboard-overview-container space-y-6 animate-fade-in">
      {/* ── 4 Top KPI Metric Cards (Pastel Aesthetics) ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4.5">
        {/* Card 1: Total Candidates */}
        <div
          className="metric-card metric-card-purple relative overflow-hidden rounded-2xl p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
          onClick={() => onNavigateTab?.('database')}
        >
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-indigo-500/15 text-indigo-600 dark:text-indigo-300">
              <Users size={24} className="stroke-[2.2]" />
            </div>
            <div>
              <span className="text-[11px] font-bold tracking-wider uppercase text-muted-foreground/90">
                TOTAL CANDIDATES
              </span>
              <div className="text-3xl font-extrabold tracking-tight text-foreground">
                1255
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">
              <TrendingUp size={11} /> +1% conv rate
            </span>
          </div>
        </div>

        {/* Card 2: Candidates Hired */}
        <div
          className="metric-card metric-card-blue relative overflow-hidden rounded-2xl p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
          onClick={() => onQuickQuery?.('Show me all hired candidates')}
        >
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-sky-500/15 text-sky-600 dark:text-sky-300">
              <Award size={24} className="stroke-[2.2]" />
            </div>
            <div>
              <span className="text-[11px] font-bold tracking-wider uppercase text-muted-foreground/90">
                CANDIDATES HIRED
              </span>
              <div className="text-3xl font-extrabold tracking-tight text-foreground">
                10
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">
              +10 total
            </span>
          </div>
        </div>

        {/* Card 3: Rejections */}
        <div
          className="metric-card metric-card-rose relative overflow-hidden rounded-2xl p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
          onClick={() => onQuickQuery?.('Show rejected candidates summary by reason')}
        >
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-rose-500/15 text-rose-600 dark:text-rose-300">
              <XCircle size={24} className="stroke-[2.2]" />
            </div>
            <div>
              <span className="text-[11px] font-bold tracking-wider uppercase text-muted-foreground/90">
                REJECTIONS
              </span>
              <div className="text-3xl font-extrabold tracking-tight text-foreground">
                328
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-500/15 text-rose-600 dark:text-rose-300">
              Rejected
            </span>
          </div>
        </div>

        {/* Card 4: Offers Sent */}
        <div
          className="metric-card metric-card-mint relative overflow-hidden rounded-2xl p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
          onClick={() => onQuickQuery?.('Show all open candidate offers')}
        >
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-teal-500/15 text-teal-600 dark:text-teal-300">
              <CheckCircle2 size={24} className="stroke-[2.2]" />
            </div>
            <div>
              <span className="text-[11px] font-bold tracking-wider uppercase text-muted-foreground/90">
                OFFERS SENT
              </span>
              <div className="text-3xl font-extrabold tracking-tight text-foreground">
                0
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/15 text-emerald-600 dark:text-emerald-300">
              +0 today
            </span>
          </div>
        </div>
      </div>

      {/* ── Main 2-Column Dashboard Grid ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column (8 cols): Upcoming Interview + Pipeline Funnel */}
        <div className="lg:col-span-8 space-y-5">
          {/* Upcoming Interview Card */}
          <div className="upcoming-interview-card rounded-2xl bg-card p-5 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-foreground">Upcoming Interview</h3>
              <button
                className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"
                aria-label="Options"
              >
                <MoreHorizontal size={16} />
              </button>
            </div>
            <div className="min-h-[90px] flex flex-col items-center justify-center text-center py-4 rounded-xl bg-muted/30 shadow-inner">
              <div className="w-9 h-9 rounded-full bg-muted/60 flex items-center justify-center text-muted-foreground mb-2">
                <Calendar size={18} />
              </div>
              <p className="text-sm font-medium text-muted-foreground">
                No interviews scheduled today.
              </p>
              <button
                onClick={() => onQuickQuery?.('Show scheduled interviews and open candidate slots')}
                className="mt-2 text-xs font-bold text-indigo-500 hover:text-indigo-600 transition-colors"
              >
                Schedule via AI Assistant →
              </button>
            </div>
          </div>

          {/* Pipeline Funnel Wave Chart */}
          <PipelineFunnelChart />
        </div>

        {/* Right Column (4 cols): Source Breakdown + Top Performers */}
        <div className="lg:col-span-4 space-y-5">
          {/* Source Breakdown Card */}
          <div className="source-breakdown-card rounded-2xl bg-card p-5 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-foreground">Source Breakdown</h3>
              <button
                className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"
                aria-label="Options"
              >
                <MoreHorizontal size={16} />
              </button>
            </div>

            <div className="space-y-4">
              {/* Naukri */}
              <div>
                <div className="flex items-center justify-between text-xs font-bold text-foreground mb-1.5">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-lg bg-slate-700 text-white flex items-center justify-center text-[10px] font-bold">
                      N
                    </span>
                    <span className="tracking-wide">NAUKRI</span>
                  </div>
                  <span className="font-extrabold text-foreground">98%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-slate-700 transition-all duration-700 ease-out"
                    style={{ width: '98%' }}
                  />
                </div>
              </div>

              {/* LinkedIn */}
              <div>
                <div className="flex items-center justify-between text-xs font-bold text-foreground mb-1.5">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-lg bg-blue-600 text-white flex items-center justify-center text-[10px] font-bold">
                      L
                    </span>
                    <span className="tracking-wide">LINKEDIN</span>
                  </div>
                  <span className="font-extrabold text-foreground">2%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-blue-600 transition-all duration-700 ease-out"
                    style={{ width: '2%' }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Top Performers Card */}
          <div className="top-performers-card rounded-2xl bg-card p-5 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-foreground">Top Performers</h3>
              <button
                className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted transition-colors"
                aria-label="Options"
              >
                <MoreHorizontal size={16} />
              </button>
            </div>

            <div className="space-y-3.5">
              {[
                {
                  id: 1,
                  initials: 'NR',
                  name: 'Nadeem Raza',
                  badge: '#1',
                  count: 14,
                  conv: '0% conv',
                  color: 'bg-cyan-500 text-white',
                },
                {
                  id: 2,
                  initials: 'TC',
                  name: 'Taru Chaudhari',
                  badge: '#2',
                  count: 9,
                  conv: '0% conv',
                  color: 'bg-amber-500 text-white',
                },
                {
                  id: 3,
                  initials: 'PP',
                  name: 'Priya Patel',
                  badge: '#3',
                  count: 0,
                  conv: '0% conv',
                  color: 'bg-rose-500 text-white',
                },
                {
                  id: 4,
                  initials: 'SS',
                  name: 'Shailly Saraswat',
                  badge: '#4',
                  count: 0,
                  conv: '0% conv',
                  color: 'bg-emerald-500 text-white',
                },
              ].map((performer) => (
                <div
                  key={performer.id}
                  className="flex items-center justify-between p-2 rounded-xl hover:bg-muted/40 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold ${performer.color}`}
                    >
                      {performer.initials}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-bold text-indigo-500 bg-indigo-500/10 px-1.5 py-0.2 rounded">
                          {performer.badge}
                        </span>
                        <span className="text-xs font-bold text-foreground">
                          {performer.name}
                        </span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        {performer.count} candidates · {performer.conv}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DashboardOverview
