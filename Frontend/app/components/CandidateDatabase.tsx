'use client'

import React, { useState, useMemo } from 'react'
import {
  Search,
  MapPin,
  Calendar,
  SlidersHorizontal,
  Download,
  UploadCloud,
  Plus,
  Briefcase,
  Mail,
  Clock,
  ExternalLink,
  ChevronDown,
  Filter,
  Check,
  Building,
} from 'lucide-react'
import { exportToCsv, exportToExcel, exportToJson } from '@/lib/export'

export interface Candidate {
  id: string
  name: string
  initials: string
  avatarBg: string
  status: 'New Lead' | 'Screening' | 'In Interview' | 'Offer' | 'Selected' | 'Rejected'
  statusColor: string
  company: string
  experience: string
  source: string
  skills: string[]
  email: string
  phone?: string
  city: string
  followUp: 'Overdue' | 'Scheduled' | 'Pending Response' | 'Completed'
  followUpColor: string
  date: string
  groupDate: string
}

const SAMPLE_CANDIDATES: Candidate[] = [
  {
    id: 'c1',
    name: 'Nitya jain',
    initials: 'NJ',
    avatarBg: 'bg-rose-100 dark:bg-rose-950/40 text-rose-600 dark:text-rose-300',
    status: 'Rejected',
    statusColor: 'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800',
    company: 'Samishti Infotech',
    experience: '3.1 yrs',
    source: 'NAUKRI',
    skills: ['SAP ABAP', 'OData', 'ALV Reports'],
    email: 'nityajain196@gmail.com',
    city: 'Pune',
    followUp: 'Overdue',
    followUpColor: 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800',
    date: '29 Jul',
    groupDate: '29 JULY 2026',
  },
  {
    id: 'c2',
    name: 'Sankark',
    initials: 'S',
    avatarBg: 'bg-blue-100 dark:bg-blue-950/40 text-blue-600 dark:text-blue-300',
    status: 'New Lead',
    statusColor: 'bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800',
    company: 'Atos',
    experience: '11.0 yrs',
    source: 'NAUKRI',
    skills: ['SAP FICO', 'General Ledger', 'Asset Accounting'],
    email: 'karasankar98@gmail.com',
    city: 'Hyderabad',
    followUp: 'Overdue',
    followUpColor: 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800',
    date: '29 Jul',
    groupDate: '29 JULY 2026',
  },
  {
    id: 'c3',
    name: 'Rahul Kumar',
    initials: 'RK',
    avatarBg: 'bg-purple-100 dark:bg-purple-950/40 text-purple-600 dark:text-purple-300',
    status: 'In Interview',
    statusColor: 'bg-cyan-50 dark:bg-cyan-950/40 text-cyan-600 dark:text-cyan-400 border border-cyan-200 dark:border-cyan-800',
    company: 'Infosys',
    experience: '5.4 yrs',
    source: 'LINKEDIN',
    skills: ['SAP HANA', 'SAP MM', 'Inventory Mgmt'],
    email: 'rahul.k@outlook.com',
    city: 'Bangalore',
    followUp: 'Scheduled',
    followUpColor: 'bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800',
    date: '28 Jul',
    groupDate: '28 JULY 2026',
  },
  {
    id: 'c4',
    name: 'Ananya Patel',
    initials: 'AP',
    avatarBg: 'bg-amber-100 dark:bg-amber-950/40 text-amber-600 dark:text-amber-300',
    status: 'Offer',
    statusColor: 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800',
    company: 'Wipro Technologies',
    experience: '7.0 yrs',
    source: 'NAUKRI',
    skills: ['SAP SD', 'Pricing Procedures', 'S/4HANA'],
    email: 'ananya.p@gmail.com',
    city: 'Mumbai',
    followUp: 'Pending Response',
    followUpColor: 'bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800',
    date: '27 Jul',
    groupDate: '27 JULY 2026',
  },
  {
    id: 'c5',
    name: 'Vikram Singh',
    initials: 'VS',
    avatarBg: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-300',
    status: 'Selected',
    statusColor: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800',
    company: 'TCS',
    experience: '4.2 yrs',
    source: 'DIRECT ERP',
    skills: ['SAP ABAP', 'SAP Fiori', 'UI5'],
    email: 'vikram.singh@gmail.com',
    city: 'Delhi NCR',
    followUp: 'Completed',
    followUpColor: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800',
    date: '26 Jul',
    groupDate: '26 JULY 2026',
  },
  {
    id: 'c6',
    name: 'Pooja Sharma',
    initials: 'PS',
    avatarBg: 'bg-pink-100 dark:bg-pink-950/40 text-pink-600 dark:text-pink-300',
    status: 'Screening',
    statusColor: 'bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800',
    company: 'Cognizant',
    experience: '6.0 yrs',
    source: 'NAUKRI',
    skills: ['SAP PP', 'Production Planning', 'MRP'],
    email: 'pooja.sharma@gmail.com',
    city: 'Pune',
    followUp: 'Scheduled',
    followUpColor: 'bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800',
    date: '25 Jul',
    groupDate: '25 JULY 2026',
  },
]

const STATUS_TABS = [
  { id: 'All', label: 'All candidates', dotColor: '' },
  { id: 'New Lead', label: 'New Leads', dotColor: 'bg-blue-500' },
  { id: 'Screening', label: 'Screening', dotColor: 'bg-purple-500' },
  { id: 'In Interview', label: 'In Interview', dotColor: 'bg-cyan-500' },
  { id: 'Offer', label: 'Offer', dotColor: 'bg-amber-500' },
  { id: 'Selected', label: 'Selected', dotColor: 'bg-emerald-500' },
  { id: 'Rejected', label: 'Rejected', dotColor: 'bg-rose-500' },
]

export function CandidateDatabase({
  onSelectCandidate,
}: {
  onSelectCandidate?: (candidate: Candidate) => void
}) {
  const [activeTab, setActiveTab] = useState('All')
  const [search, setSearch] = useState('')
  const [cityFilter, setCityFilter] = useState('')
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)

  // Filtering
  const filteredCandidates = useMemo(() => {
    return SAMPLE_CANDIDATES.filter((c) => {
      if (activeTab !== 'All' && c.status !== activeTab) return false
      if (search.trim()) {
        const q = search.toLowerCase()
        const match =
          c.name.toLowerCase().includes(q) ||
          c.email.toLowerCase().includes(q) ||
          c.company.toLowerCase().includes(q) ||
          c.skills.some((s) => s.toLowerCase().includes(q))
        if (!match) return false
      }
      if (cityFilter.trim() && !c.city.toLowerCase().includes(cityFilter.toLowerCase())) {
        return false
      }
      return true
    })
  }, [activeTab, search, cityFilter])

  // Group by date
  const groupedCandidates = useMemo(() => {
    const groups: { [date: string]: Candidate[] } = {}
    for (const c of filteredCandidates) {
      if (!groups[c.groupDate]) groups[c.groupDate] = []
      groups[c.groupDate].push(c)
    }
    return groups
  }, [filteredCandidates])

  const handleExport = (type: 'excel' | 'csv' | 'json') => {
    const exportRows = filteredCandidates.map((c) => ({
      ID: c.id,
      Name: c.name,
      Status: c.status,
      Company: c.company,
      Experience: c.experience,
      Source: c.source,
      Skills: c.skills.join(', '),
      Email: c.email,
      City: c.city,
      FollowUp: c.followUp,
      Date: c.date,
    }))
    if (type === 'excel') exportToExcel(exportRows, 'Candidate_Database.xlsx')
    else if (type === 'csv') exportToCsv(exportRows, 'Candidate_Database.csv')
    else exportToJson(exportRows, 'Candidate_Database.json')
    setShowExportMenu(false)
  }

  return (
    <div className="candidate-database-view space-y-6 animate-fade-in">
      {/* ── Top Header and Action Buttons (Matching Reference Image 2) ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <span className="text-[11px] font-extrabold tracking-widest uppercase text-muted-foreground/80">
            TALENT PIPELINE
          </span>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground">
            Candidate Database
          </h1>
        </div>

        <div className="flex items-center gap-2.5">
          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-card border border-border/60 hover:bg-muted/60 text-foreground transition-all shadow-sm"
            >
              <Download size={14} /> Export
            </button>
            {showExportMenu && (
              <div
                className="absolute right-0 mt-1.5 w-36 bg-popover border border-border rounded-xl shadow-xl py-1 z-30 animate-in fade-in zoom-in-95"
                onMouseLeave={() => setShowExportMenu(false)}
              >
                <button
                  onClick={() => handleExport('excel')}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted flex items-center gap-2"
                >
                  Excel (.xlsx)
                </button>
                <button
                  onClick={() => handleExport('csv')}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted flex items-center gap-2"
                >
                  CSV (.csv)
                </button>
                <button
                  onClick={() => handleExport('json')}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted flex items-center gap-2"
                >
                  JSON (.json)
                </button>
              </div>
            )}
          </div>

          <button className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-card border border-border/60 hover:bg-muted/60 text-foreground transition-all shadow-sm">
            <UploadCloud size={14} /> Bulk Import
          </button>

          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 transition-all shadow-md"
          >
            <Plus size={15} /> Add Candidate
          </button>
        </div>
      </div>

      {/* ── Status Tabs (Pill Navigation) ── */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
        {STATUS_TABS.map((tab) => {
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900 shadow-sm'
                  : 'bg-card text-muted-foreground hover:text-foreground border border-border/50 hover:bg-muted/50'
              }`}
            >
              {tab.dotColor && (
                <span className={`w-2 h-2 rounded-full ${tab.dotColor}`} />
              )}
              <span>{tab.label}</span>
            </button>
          )
        })}
      </div>

      {/* ── Filter Toolbar ── */}
      <div className="flex flex-wrap items-center gap-3 p-2 bg-card/60 shadow-sm rounded-2xl">
        {/* Search */}
        <div className="flex-1 min-w-[200px] relative">
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name, email, skill..."
            className="w-full pl-9 pr-3 py-2 bg-card rounded-xl text-xs font-medium border border-border/50 focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-muted-foreground/60"
          />
        </div>

        {/* City Filter */}
        <div className="w-36 relative">
          <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={cityFilter}
            onChange={(e) => setCityFilter(e.target.value)}
            placeholder="City"
            className="w-full pl-8 pr-3 py-2 bg-card rounded-xl text-xs font-medium border border-border/50 focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-muted-foreground/60"
          />
        </div>

        {/* Date Filters */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <input
              type="text"
              placeholder="dd-mm-yyyy"
              defaultValue="29-07-2026"
              className="w-32 px-3 py-2 bg-card rounded-xl text-xs font-medium border border-border/50 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Calendar size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          </div>
          <span className="text-muted-foreground text-xs font-bold">to</span>
          <div className="relative">
            <input
              type="text"
              placeholder="dd-mm-yyyy"
              defaultValue="29-07-2026"
              className="w-32 px-3 py-2 bg-card rounded-xl text-xs font-medium border border-border/50 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Calendar size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          </div>
        </div>

        {/* More Filter */}
        <button className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-card border border-border/50 hover:bg-muted text-muted-foreground">
          <SlidersHorizontal size={13} /> More
        </button>

        {/* Apply */}
        <button className="px-4 py-2 rounded-xl text-xs font-bold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 transition-all shadow-sm">
          Apply
        </button>
      </div>

      {/* ── Main Layout: Candidate List (Left 8) + Summary Snapshot (Right 4) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Candidate List Rows */}
        <div className="lg:col-span-8 space-y-6">
          {Object.keys(groupedCandidates).length === 0 ? (
            <div className="text-center py-12 bg-card shadow-md rounded-2xl p-6">
              <p className="text-sm font-semibold text-muted-foreground">
                No candidates found matching your filters.
              </p>
            </div>
          ) : (
            Object.entries(groupedCandidates).map(([groupDate, candidates]) => (
              <div key={groupDate} className="space-y-3">
                {/* Date Header */}
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground/80 pl-1">
                  {groupDate}
                </h4>

                {/* Candidate Cards */}
                <div className="space-y-3">
                  {candidates.map((candidate) => (
                    <div
                      key={candidate.id}
                      onClick={() => onSelectCandidate?.(candidate)}
                      className="candidate-row-card bg-card shadow-sm hover:shadow-md hover:shadow-indigo-500/10 rounded-2xl p-4 transition-all duration-200 cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-4"
                    >
                      <div className="flex items-start sm:items-center gap-3.5">
                        {/* Avatar */}
                        <div
                          className={`w-11 h-11 rounded-full flex items-center justify-center text-sm font-extrabold flex-shrink-0 ${candidate.avatarBg}`}
                        >
                          {candidate.initials}
                        </div>

                        {/* Info */}
                        <div className="space-y-1.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-bold text-foreground">
                              {candidate.name}
                            </span>
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${candidate.statusColor}`}
                            >
                              {candidate.status}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                            <span className="inline-flex items-center gap-1">
                              <Building size={12} /> {candidate.company}
                            </span>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1">
                              <Clock size={12} /> {candidate.experience}
                            </span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-extrabold bg-muted text-muted-foreground uppercase">
                              {candidate.source}
                            </span>
                          </div>

                          {/* Skill Tags */}
                          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            {candidate.skills.map((skill) => (
                              <span
                                key={skill}
                                className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-muted/60 text-foreground border border-border/40"
                              >
                                {skill}
                              </span>
                            ))}
                          </div>

                          {/* Contact & Follow-up */}
                          <div className="flex flex-wrap items-center gap-2.5 text-[11px] pt-1">
                            <span className="inline-flex items-center gap-1 text-muted-foreground">
                              <Mail size={11} /> {candidate.email}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${candidate.followUpColor}`}
                            >
                              {candidate.followUp}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right Timestamp */}
                      <div className="text-right sm:self-center flex-shrink-0">
                        <span className="text-xs font-semibold text-muted-foreground/80">
                          {candidate.date}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right Sidebar Snapshot Cards (Matching Reference Image 2) */}
        <div className="lg:col-span-4 space-y-4">
          {/* Total Candidates Dark Accent Card */}
          <div className="relative overflow-hidden rounded-2xl bg-slate-900 text-white p-5 shadow-lg">
            <div className="absolute -right-6 -bottom-6 w-32 h-32 rounded-full bg-slate-800/80 pointer-events-none" />
            <span className="text-[11px] font-bold tracking-wider uppercase text-slate-400">
              TOTAL CANDIDATES
            </span>
            <div className="text-3xl font-extrabold tracking-tight mt-1 text-white">
              1255
            </div>
          </div>

          {/* This Page Card */}
          <div className="rounded-2xl bg-card p-4.5 shadow-md">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
              THIS PAGE
            </span>
            <div className="text-lg font-extrabold text-foreground mt-0.5">
              {filteredCandidates.length} shown
            </div>
          </div>

          {/* Follow-ups Overdue Card (Soft Rose) */}
          <div className="rounded-2xl bg-rose-50/70 dark:bg-rose-950/30 p-4.5 shadow-md shadow-rose-500/5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">
              FOLLOW-UPS OVERDUE
            </span>
            <div className="text-2xl font-extrabold text-rose-600 dark:text-rose-300 mt-0.5">
              20
            </div>
          </div>

          {/* Pipeline Snapshot Card */}
          <div className="rounded-2xl bg-card p-5 shadow-md space-y-3.5">
            <h3 className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
              PIPELINE SNAPSHOT
            </h3>

            <div className="space-y-2.5 text-xs font-semibold">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  <span className="text-muted-foreground">New Leads</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full" style={{ width: '45%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">13</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-purple-500" />
                  <span className="text-muted-foreground">Screening</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-purple-500 rounded-full" style={{ width: '15%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">1</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-500" />
                  <span className="text-muted-foreground">In Interview</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-cyan-500 rounded-full" style={{ width: '30%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">4</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500" />
                  <span className="text-muted-foreground">Offer</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-amber-500 rounded-full" style={{ width: '20%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">2</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="text-muted-foreground">Selected</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: '55%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">10</span>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-rose-500" />
                  <span className="text-muted-foreground">Rejected</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-rose-500 rounded-full" style={{ width: '85%' }} />
                  </div>
                  <span className="font-bold text-foreground w-5 text-right">328</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CandidateDatabase
