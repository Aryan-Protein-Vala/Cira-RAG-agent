'use client'

import React, { useState, useMemo, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  Search,
  Columns3,
  Download,
  Copy,
  Check,
  Maximize2,
  X,
  AlertTriangle,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileSpreadsheet,
  FileText,
  FileJson,
  Database,
} from 'lucide-react'
import { exportToCsv, exportToExcel, exportToJson } from '@/lib/export'

export interface MessageMeta {
  source?: string
  simulated?: boolean
  table?: string
  columns?: string[]
  rowCount?: number
  totalAvailable?: number | null
  truncated?: boolean
  elapsedMs?: number
  sql?: string
  warnings?: string[]
}

const PAGE_SIZES = [10, 25, 50, 100]
const DEFAULT_VISIBLE_COLUMNS = 6

function formatCell(value: any): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function DataCard({
  payload,
  entity,
  meta,
}: {
  payload?: any
  entity?: string
  meta?: MessageMeta
}) {
  const rawData: any[] = useMemo(
    () => (Array.isArray(payload) ? payload : payload ? [payload] : []),
    [payload]
  )

  const headers = useMemo(() => {
    const seen: string[] = []
    for (const row of rawData.slice(0, 100)) {
      if (row && typeof row === 'object') {
        for (const key of Object.keys(row)) if (!seen.includes(key)) seen.push(key)
      }
    }
    return meta?.columns?.length
      ? meta.columns.filter((c) => seen.includes(c)).concat(seen.filter((c) => !meta.columns!.includes(c)))
      : seen
  }, [rawData, meta?.columns])

  const [copied, setCopied] = useState(false)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(10)
  const [showColumnPicker, setShowColumnPicker] = useState(false)
  const [hidden, setHidden] = useState<string[]>([])
  const [showSql, setShowSql] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)

  useEffect(() => {
    setHidden(headers.slice(DEFAULT_VISIBLE_COLUMNS))
    setPage(0)
  }, [headers])

  const visibleHeaders = useMemo(
    () => headers.filter((h) => !hidden.includes(h)),
    [headers, hidden]
  )

  const filteredData = useMemo(() => {
    let list = rawData
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((row) =>
        Object.values(row ?? {}).some((v) =>
          String(v ?? '').toLowerCase().includes(q)
        )
      )
    }
    if (sortKey) {
      list = [...list].sort((a, b) => {
        const valA = a?.[sortKey]
        const valB = b?.[sortKey]
        if (valA === valB) return 0
        if (valA === null || valA === undefined) return 1
        if (valB === null || valB === undefined) return -1
        if (typeof valA === 'number' && typeof valB === 'number')
          return sortAsc ? valA - valB : valB - valA
        return sortAsc
          ? String(valA).localeCompare(String(valB), undefined, { numeric: true })
          : String(valB).localeCompare(String(valA), undefined, { numeric: true })
      })
    }
    return list
  }, [rawData, search, sortKey, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filteredData.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const displayRows = filteredData.slice(
    safePage * pageSize,
    safePage * pageSize + pageSize
  )

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(JSON.stringify(filteredData, null, 2))
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      // ignore
    }
  }

  const toggleSort = (h: string) => {
    if (sortKey === h) setSortAsc(!sortAsc)
    else {
      setSortKey(h)
      setSortAsc(true)
    }
  }

  if (rawData.length === 0) {
    return (
      <div 
        className="data-card-wrapper bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden transform hover:rotate-1 hover:-translate-y-2 hover:shadow-xl transition-all duration-300 animate-fade-in text-gray-900 w-full"
        style={{ animationFillMode: 'both', animationDelay: '300ms' }}
      >
        <div className="bg-gradient-to-r from-purple-300 to-purple-400 px-4 py-3 flex items-center justify-between text-purple-950">
          <div className="flex items-center gap-2">
            <Database size={15} className="text-purple-800" />
            <strong className="text-sm font-black text-purple-950">
              {entity ?? 'Structured Result'}
            </strong>
          </div>
          <span className="text-xs font-bold bg-purple-900/10 px-2 py-1 rounded-md">0 records</span>
        </div>
        <div className="p-5">
          <p className="text-xs text-gray-500 font-semibold mt-1">
            No records matched that query. Try widening filters or adjusting search terms.
          </p>
        </div>
      </div>
    )
  }

  const renderTable = (expanded: boolean) => (
    <div className={`w-full ${expanded ? 'h-full flex flex-col gap-3' : 'space-y-3'}`}>
      {/* Head */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-1 border-b border-indigo-400/30">
        <div>
          <span className="text-[10px] font-extrabold tracking-wider uppercase text-blue-200 flex items-center gap-1.5">
            <Database size={12} className="text-white" /> STRUCTURED RESULT
          </span>
          <h4 className="text-sm md:text-base font-bold text-white">
            {entity ?? 'Data Table'}
          </h4>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {meta?.simulated && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/15 text-amber-600 dark:text-amber-300">
              <AlertTriangle size={11} /> SIMULATED
            </span>
          )}
          {typeof meta?.elapsedMs === 'number' && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-muted text-muted-foreground">
              {meta.elapsedMs} ms
            </span>
          )}
          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/10 text-indigo-500">
            {filteredData.length.toLocaleString()} rows
          </span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="relative flex-1 min-w-[160px]">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
            placeholder="Filter records..."
            className="w-full pl-8 pr-3 py-1.5 bg-muted/40 rounded-xl text-xs border border-border/40 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        <div className="flex items-center gap-2">
          {/* Column Picker */}
          <div className="relative">
            <button
              onClick={() => setShowColumnPicker(!showColumnPicker)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-all active:scale-95"
            >
              <Columns3 size={13} /> ({visibleHeaders.length}/{headers.length})
            </button>
            {showColumnPicker && (
              <div
                className="absolute right-0 mt-1.5 w-48 bg-white border border-gray-100 rounded-xl shadow-xl p-2 z-30 space-y-1.5"
                onMouseLeave={() => setShowColumnPicker(false)}
              >
                <div className="flex items-center justify-between pb-1 border-b border-gray-100 text-[11px] font-bold">
                  <button onClick={() => setHidden([])} className="text-indigo-500 hover:underline">
                    Show all
                  </button>
                  <button onClick={() => setHidden(headers.slice(DEFAULT_VISIBLE_COLUMNS))} className="text-gray-500 hover:underline">
                    Reset
                  </button>
                </div>
                <div className="max-h-48 overflow-y-auto space-y-1 text-xs">
                  {headers.map((h) => (
                    <label key={h} className="flex items-center gap-2 px-1 py-0.5 cursor-pointer hover:bg-gray-100 rounded">
                      <input
                        type="checkbox"
                        checked={!hidden.includes(h)}
                        onChange={() =>
                          setHidden((cur) =>
                            cur.includes(h) ? cur.filter((c) => c !== h) : [...cur, h]
                          )
                        }
                        className="rounded text-indigo-500"
                      />
                      <span className="truncate text-gray-900">{h}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-indigo-500 hover:bg-indigo-600 text-white shadow-sm transition-all active:scale-95"
            >
              <Download size={13} /> Export
            </button>
            {showExportMenu && (
              <div
                className="absolute right-0 mt-1.5 w-36 bg-white border border-gray-100 rounded-xl shadow-xl py-1 z-30"
                onMouseLeave={() => setShowExportMenu(false)}
              >
                <button
                  onClick={() => {
                    exportToExcel(filteredData, `${entity || 'data'}.xlsx`)
                    setShowExportMenu(false)
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-gray-900 hover:bg-gray-100 flex items-center gap-2 transition-colors"
                >
                  <FileSpreadsheet size={13} /> Excel (.xlsx)
                </button>
                <button
                  onClick={() => {
                    exportToCsv(filteredData, `${entity || 'data'}.csv`)
                    setShowExportMenu(false)
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-gray-900 hover:bg-gray-100 flex items-center gap-2 transition-colors"
                >
                  <FileText size={13} /> CSV (.csv)
                </button>
                <button
                  onClick={() => {
                    exportToJson(filteredData, `${entity || 'data'}.json`)
                    setShowExportMenu(false)
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs font-semibold text-gray-900 hover:bg-gray-100 flex items-center gap-2 transition-colors"
                >
                  <FileJson size={13} /> JSON (.json)
                </button>
              </div>
            )}
          </div>

          {/* Copy JSON */}
          <button
            onClick={copy}
            className="p-1.5 rounded-xl text-xs font-semibold bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Copy as JSON"
          >
            {copied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
          </button>
        </div>
      </div>

      {/* Table Data View */}
      <div className={`rounded-xl border border-border/40 bg-white ${expanded ? 'flex-1 overflow-auto min-h-0 relative' : 'overflow-auto max-h-[350px] relative'}`}>
        <table className="w-full text-left border-collapse text-xs">
          <thead className="sticky top-0 z-10 bg-white shadow-sm">
            <tr className="bg-muted/60 text-muted-foreground border-b border-border/40 font-bold">
              {visibleHeaders.map((header) => {
                const isSorted = sortKey === header
                return (
                  <th
                    key={header}
                    onClick={() => toggleSort(header)}
                    className="p-2.5 cursor-pointer select-none hover:text-foreground transition-colors whitespace-nowrap"
                  >
                    <div className="flex items-center gap-1.5">
                      <span>{header}</span>
                      {isSorted ? (
                        sortAsc ? <ArrowUp size={12} className="text-indigo-500" /> : <ArrowDown size={12} className="text-indigo-500" />
                      ) : (
                        <ArrowUpDown size={11} className="opacity-40" />
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {displayRows.map((row, rIdx) => (
              <tr
                key={rIdx}
                className="hover:bg-muted/30 transition-colors odd:bg-card even:bg-muted/10"
              >
                {visibleHeaders.map((header) => (
                  <td key={header} className="p-2.5 text-foreground whitespace-nowrap font-medium">
                    {formatCell(row?.[header])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPage(0)
            }}
            className="bg-muted/40 rounded-lg px-2 py-0.5 border border-border/40 text-foreground"
          >
            {PAGE_SIZES.map((sz) => (
              <option key={sz} value={sz}>
                {sz}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span>
            Page {safePage + 1} of {pageCount}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="p-1.5 rounded-xl hover:bg-muted/50 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent transition-all active:scale-95"
            >
              ‹
            </button>
            <button
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              disabled={safePage >= pageCount - 1}
              className="p-1.5 rounded-xl hover:bg-muted/50 text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent transition-all active:scale-95"
            >
              ›
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <>
      <div 
        className="data-card-wrapper bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden transform hover:rotate-1 hover:-translate-y-2 hover:shadow-xl transition-all duration-300 animate-fade-in text-gray-900 w-full flex flex-col"
        style={{ animationFillMode: 'both', animationDelay: '300ms' }}
      >
        <div className="bg-gradient-to-r from-purple-300 to-purple-400 px-4 py-3 flex items-center justify-between text-purple-950">
          <div>
            <span className="text-[10px] font-extrabold tracking-wider uppercase text-purple-800 flex items-center gap-1.5">
              <Database size={12} className="text-purple-700" /> STRUCTURED RESULT
            </span>
            <h4 className="text-sm md:text-base font-black text-purple-950">
              {entity ?? 'Data Table'}
            </h4>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {meta?.simulated && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/15 text-amber-600">
                <AlertTriangle size={11} /> SIMULATED
              </span>
            )}
            {typeof meta?.elapsedMs === 'number' && (
              <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-purple-900/10 text-purple-950">
                {meta.elapsedMs} ms
              </span>
            )}
            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-white/40 text-purple-950">
              {filteredData.length.toLocaleString()} rows
            </span>
            {!isExpanded && (
              <button
                onClick={() => setIsExpanded(true)}
                className="p-1.5 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all active:scale-95"
                title="Expand view"
              >
                <Maximize2 size={14} />
              </button>
            )}
          </div>
        </div>

        <div className="p-4">
          {renderTable(false)}
        </div>
      </div>

      {/* Fullscreen Expand Modal */}
      {isExpanded && typeof document !== 'undefined' && createPortal(
        <div
          className="fixed inset-0 z-[100] bg-white animate-in fade-in flex flex-col p-6 md:p-10"
        >
          <div className="w-full max-w-7xl mx-auto flex flex-col h-full space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <h3 className="text-xl md:text-2xl font-black text-gray-900">
                {entity ?? 'Structured Result'}
              </h3>
              <button
                onClick={() => setIsExpanded(false)}
                className="p-2 rounded-xl hover:bg-gray-100 text-gray-400 hover:text-gray-900 transition-all active:scale-95"
                title="Close fullscreen"
              >
                <X size={24} />
              </button>
            </div>
            <div className="flex-1 overflow-hidden flex flex-col pb-4">
              {renderTable(true)}
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

export default DataCard
