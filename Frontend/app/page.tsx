'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowUp,
  BarChart3,
  Check,
  ChevronLeft,
  Clipboard,
  Columns3,
  Database,
  FileJson,
  FileSpreadsheet,
  FileText,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Paperclip,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { exportToCsv, exportToExcel, exportToJson } from '@/lib/export'
import { ChartCard, ChartPayload } from './ChartCard'

/**
 * All backend calls go through the Next server (`/api/*` -> FastAPI rewrite in
 * next.config.mjs). Hard-coding http://localhost:8000 broke every deployment
 * where the browser is not running on the same machine as the backend
 * (RDP access by hostname, remote preview, nginx, mobile).
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

type MessageMeta = {
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

type Message = {
  role: 'user' | 'assistant'
  content: string
  data?: any
  entity?: string
  meta?: MessageMeta
  chart?: ChartPayload
  timestamp?: string
  sources?: string[]
  status?: string
  error?: string
  _streamingId?: number
}

type Session = { id: string; title: string; date: string }
type ToastType = { id: number; message: string; type: 'success' | 'error' }

/** crypto.randomUUID() only exists in secure contexts — an RDP box served
 *  over plain http://<ip>:3000 would otherwise throw on the first message. */
function newSessionId(): string {
  const c: any = typeof crypto !== 'undefined' ? crypto : undefined
  if (c?.randomUUID) return c.randomUUID()
  if (c?.getRandomValues) {
    const bytes = c.getRandomValues(new Uint8Array(16))
    return Array.from(bytes, (b: number) => b.toString(16).padStart(2, '0')).join('')
  }
  return `sid-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function BrandMark() {
  return (
    <div className="brand-mark">
      <span />
      <span />
      <span />
    </div>
  )
}

function ThemeToggle({ theme, onToggle }: { theme: 'light' | 'dark'; onToggle: () => void }) {
  return (
    <button className="theme-toggle" onClick={onToggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
      {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Login                                                                      */
/* ────────────────────────────────────────────────────────────────────────── */
function Login({
  onLogin,
  theme,
  onToggle,
}: {
  onLogin: (user: { employee_id: string; name: string }, token: string) => void
  theme: 'light' | 'dark'
  onToggle: () => void
}) {
  const [employee, setEmployee] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    const id = employee.trim()
    if (!id) return setError('Please enter your Employee ID.')
    if (!password) return setError('Please enter your password.')

    setBusy(true)
    try {
      // Tokens are minted and signed by the backend — the browser can no
      // longer forge a session for an arbitrary employee id.
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employee_id: id, password }),
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        setError(detail?.detail || 'Sign-in failed. Check your credentials.')
        return
      }
      const data = await res.json()
      onLogin(data.user, data.token)
    } catch {
      setError('Cannot reach the CIRA backend. Is the API running on port 8000?')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="chat-blur-film" />
      <main className="login-shell">
        <div className="login-top">
          <div className="sidebar-brand">
            <BrandMark />
            <span>CIRA</span>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggle} />
        </div>
        <section className="login-card" aria-labelledby="login-title">
          <div className="login-brand">
            <BrandMark />
            <span>CIRA</span>
          </div>
          <div className="eyebrow">
            <ShieldCheck size={14} /> INTERNAL DATA ACCESS
          </div>
          <h1 id="login-title">
            Ask your enterprise
            <br />
            <em>anything.</em>
          </h1>
          <p className="login-copy">Securely query SAP Business One with natural language. Built for clarity, speed and control.</p>
          <form onSubmit={submit}>
            <label>
              Employee ID
              <input value={employee} onChange={(e) => setEmployee(e.target.value)} placeholder="e.g. EMP-20481" autoComplete="username" />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
            </label>
            {error && <p className="login-error">{error}</p>}
            <button className="primary-button login-button" type="submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in securely'} <ArrowUp size={16} />
            </button>
          </form>
          <p className="secure-note">
            <ShieldCheck size={13} /> Session tokens are signed server-side · Your queries are private
          </p>
        </section>
      </main>
    </>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Data card                                                                  */
/* ────────────────────────────────────────────────────────────────────────── */
const PAGE_SIZES = [25, 50, 100, 500]
const DEFAULT_VISIBLE_COLUMNS = 6

function formatCell(value: any): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function DataCard({ payload, entity, meta }: { payload?: any; entity?: string; meta?: MessageMeta }) {
  const rawData: any[] = useMemo(
    () => (Array.isArray(payload) ? payload : payload ? [payload] : []),
    [payload],
  )

  const headers = useMemo(() => {
    const seen: string[] = []
    for (const row of rawData.slice(0, 100)) {
      if (row && typeof row === 'object') {
        for (const key of Object.keys(row)) if (!seen.includes(key)) seen.push(key)
      }
    }
    return meta?.columns?.length ? meta.columns.filter((c) => seen.includes(c)).concat(seen.filter((c) => !meta.columns!.includes(c))) : seen
  }, [rawData, meta?.columns])

  // Every hook runs unconditionally — the previous version declared hooks
  // *after* an early return for empty results, which crashed React.
  const [copied, setCopied] = useState(false)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const [showColumnPicker, setShowColumnPicker] = useState(false)
  const [hidden, setHidden] = useState<string[]>([])
  const [showSql, setShowSql] = useState(false)

  useEffect(() => {
    setHidden(headers.slice(DEFAULT_VISIBLE_COLUMNS))
    setPage(0)
  }, [headers.join('|')])

  const visibleHeaders = useMemo(() => headers.filter((h) => !hidden.includes(h)), [headers, hidden])

  const filteredData = useMemo(() => {
    let list = rawData
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter((row) => Object.values(row ?? {}).some((v) => String(v ?? '').toLowerCase().includes(q)))
    }
    if (sortKey) {
      list = [...list].sort((a, b) => {
        const valA = a?.[sortKey]
        const valB = b?.[sortKey]
        if (valA === valB) return 0
        if (valA === null || valA === undefined) return 1
        if (valB === null || valB === undefined) return -1
        if (typeof valA === 'number' && typeof valB === 'number') return sortAsc ? valA - valB : valB - valA
        return sortAsc
          ? String(valA).localeCompare(String(valB), undefined, { numeric: true })
          : String(valB).localeCompare(String(valA), undefined, { numeric: true })
      })
    }
    return list
  }, [rawData, search, sortKey, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filteredData.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const displayRows = filteredData.slice(safePage * pageSize, safePage * pageSize + pageSize)

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(JSON.stringify(filteredData, null, 2))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard blocked (http origin) — ignore */
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
      <div className="data-card">
        <div className="data-card-head">
          <div>
            <span className="data-label">
              <BarChart3 size={13} /> STRUCTURED SAP RESULT
            </span>
            <strong>{entity ?? 'SAP Data'}</strong>
          </div>
          <span className="row-count">0 records</span>
        </div>
        <p className="data-period" style={{ marginTop: 12, marginBottom: 0 }}>
          No records matched that query. Try widening the period or removing a filter.
        </p>
      </div>
    )
  }

  const gridStyle = { gridTemplateColumns: `repeat(${Math.max(visibleHeaders.length, 1)}, minmax(0, 1fr))` }
  const fileBase = (entity ?? 'sap').toString().replace(/[^\w.-]+/g, '_')

  return (
    <div className="data-card">
      <div className="data-card-head">
        <div>
          <span className="data-label">
            <BarChart3 size={13} /> STRUCTURED SAP RESULT
          </span>
          <strong>{entity ?? 'SAP Data'}</strong>
        </div>
        <div className="data-card-badges">
          {meta?.simulated && (
            <span className="badge badge-warn" title="The live SAP HANA server was not reachable, so this is sandbox data.">
              <AlertTriangle size={11} /> SIMULATED
            </span>
          )}
          {meta?.truncated && meta?.totalAvailable ? (
            <span className="badge" title={`${meta.totalAvailable.toLocaleString()} rows match; the first ${rawData.length.toLocaleString()} were fetched.`}>
              of {meta.totalAvailable.toLocaleString()}
            </span>
          ) : null}
          {typeof meta?.elapsedMs === 'number' && <span className="badge">{meta.elapsedMs} ms</span>}
          <span className="row-count">{filteredData.length.toLocaleString()} records</span>
        </div>
      </div>

      <div className="data-toolbar">
        <div className="data-search">
          <Search size={13} />
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(0)
            }}
            placeholder="Filter records…"
          />
        </div>

        <div className="data-toolbar-right">
          <div className="column-picker">
            <button onClick={() => setShowColumnPicker((v) => !v)} className="mini-button" aria-expanded={showColumnPicker}>
              <Columns3 size={13} /> Columns ({visibleHeaders.length}/{headers.length})
            </button>
            {showColumnPicker && (
              <div className="column-panel" onMouseLeave={() => setShowColumnPicker(false)}>
                <div className="column-panel-actions">
                  <button onClick={() => setHidden([])}>Show all</button>
                  <button onClick={() => setHidden(headers.slice(DEFAULT_VISIBLE_COLUMNS))}>Reset</button>
                </div>
                <div className="column-panel-list">
                  {headers.map((h) => (
                    <label key={h}>
                      <input
                        type="checkbox"
                        checked={!hidden.includes(h)}
                        onChange={() =>
                          setHidden((current) =>
                            current.includes(h) ? current.filter((c) => c !== h) : [...current, h],
                          )
                        }
                      />
                      <span>{h}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <select
            className="mini-select"
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value))
              setPage(0)
            }}
            aria-label="Rows per page"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="data-period">
        Showing {displayRows.length.toLocaleString()} of {filteredData.length.toLocaleString()} entries
        {sortKey ? ` · sorted by ${sortKey} (${sortAsc ? 'ASC' : 'DESC'})` : ''}
        {meta?.source ? ` · ${meta.source}` : ''}
      </p>

      <div className="mini-table">
        <div className="mini-row mini-head" style={gridStyle}>
          {visibleHeaders.map((h) => (
            <span key={h} onClick={() => toggleSort(h)} title="Click to sort" className="sortable">
              {h} {sortKey === h ? (sortAsc ? '▲' : '▼') : ''}
            </span>
          ))}
        </div>
        {displayRows.map((row, i) => (
          <div className="mini-row" key={`${safePage}-${i}`} style={gridStyle}>
            {visibleHeaders.map((h) => (
              <span key={h} title={formatCell(row?.[h])} className={typeof row?.[h] === 'number' ? 'numeric' : ''}>
                {formatCell(row?.[h])}
              </span>
            ))}
          </div>
        ))}
      </div>

      {pageCount > 1 && (
        <div className="pagination">
          <button onClick={() => setPage(0)} disabled={safePage === 0}>
            « First
          </button>
          <button onClick={() => setPage(safePage - 1)} disabled={safePage === 0}>
            ‹ Prev
          </button>
          <span>
            Page {safePage + 1} of {pageCount}
          </span>
          <button onClick={() => setPage(safePage + 1)} disabled={safePage >= pageCount - 1}>
            Next ›
          </button>
          <button onClick={() => setPage(pageCount - 1)} disabled={safePage >= pageCount - 1}>
            Last »
          </button>
        </div>
      )}

      <div className="data-actions">
        <button onClick={() => exportToExcel(filteredData, `${fileBase}_export.xlsx`)}>
          <FileSpreadsheet size={14} /> Excel
        </button>
        <button onClick={() => exportToCsv(filteredData, `${fileBase}_export.csv`)}>
          <FileText size={14} /> CSV
        </button>
        <button onClick={() => exportToJson(filteredData, `${fileBase}_export.json`)}>
          <FileJson size={14} /> JSON
        </button>
        <button onClick={copy}>
          {copied ? <Check size={14} /> : <Clipboard size={14} />} {copied ? 'Copied' : 'Copy'}
        </button>
        {meta?.sql && (
          <button onClick={() => setShowSql((v) => !v)}>
            <Database size={14} /> {showSql ? 'Hide SQL' : 'Show SQL'}
          </button>
        )}
      </div>

      {showSql && meta?.sql && <pre className="sql-block">{meta.sql}</pre>}
      {meta?.warnings?.length ? (
        <p className="data-warning">
          <AlertTriangle size={12} /> {meta.warnings.join(' ')}
        </p>
      ) : null}
    </div>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Sidebar                                                                    */
/* ────────────────────────────────────────────────────────────────────────── */
function Sidebar({
  collapsed,
  onToggle,
  onLogout,
  activeId,
  onSelect,
  sessions,
  setSessions,
  sessionToken,
  employeeId,
  profileName,
  showToast,
  onRequestDelete,
  onOpenProfile,
}: {
  collapsed: boolean
  onToggle: () => void
  onLogout: () => void
  activeId: string
  onSelect: (id: string, title: string) => void
  sessions: Session[]
  setSessions: React.Dispatch<React.SetStateAction<Session[]>>
  sessionToken: string
  employeeId: string
  profileName: string
  showToast: (msg: string, type?: 'success' | 'error') => void
  onRequestDelete: (session: Session) => void
  onOpenProfile: () => void
}) {
  const [query, setQuery] = useState('')
  const [menu, setMenu] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const filtered = useMemo(
    () => sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase())),
    [query, sessions],
  )

  const rename = (session: Session) => {
    setEditing(session.id)
    setEditValue(session.title)
    setMenu(null)
  }

  const saveRename = async (id: string, oldTitle: string) => {
    const title = editValue.trim()
    setEditing(null)
    if (!title || title === oldTitle) return
    setSessions((current) => current.map((s) => (s.id === id ? { ...s, title } : s)))
    try {
      const res = await fetch(`${API_BASE}/session/${encodeURIComponent(id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}` },
        body: JSON.stringify({ title }),
      })
      showToast(res.ok ? 'Chat renamed' : 'Rename failed', res.ok ? 'success' : 'error')
    } catch {
      showToast('Rename failed', 'error')
    }
  }

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-top">
        <button className="sidebar-brand-btn" onClick={collapsed ? onToggle : undefined}>
          <BrandMark />
          <span className="brand-text">CIRA</span>
        </button>
        <button className="icon-button toggle-btn" onClick={onToggle} aria-label="Toggle sidebar">
          <ChevronLeft size={18} />
        </button>
      </div>
      <div className="sidebar-actions">
        <button className="new-chat" onClick={() => onSelect('new', 'New conversation')}>
          <Plus size={16} />
          <span>New chat</span>
        </button>
      </div>
      <div className="history-search">
        <BrandMark />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search history" />
      </div>
      <div className="history">
        <div className="history-group">
          {filtered.length === 0 && <p className="history-empty">No conversations yet.</p>}
          {filtered.map((session) => (
            <div
              className={`history-item ${activeId === session.id ? 'active' : ''}`}
              key={session.id}
              onClick={() => editing !== session.id && onSelect(session.id, session.title)}
            >
              <MessageSquare size={15} />
              <div className="history-title">
                {editing === session.id ? (
                  <input
                    autoFocus
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={() => saveRename(session.id, session.title)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveRename(session.id, session.title)
                      if (e.key === 'Escape') setEditing(null)
                    }}
                  />
                ) : (
                  <span>{session.title}</span>
                )}
              </div>
              <button
                className="history-menu-button"
                onClick={(e) => {
                  e.stopPropagation()
                  setMenu(menu === session.id ? null : session.id)
                }}
                aria-label={`Options for ${session.title}`}
              >
                <MoreHorizontal size={16} />
              </button>
              {menu === session.id && (
                <div className="history-menu" onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => rename(session)}>
                    <Pencil size={14} /> Rename
                  </button>
                  <button
                    className="delete-action"
                    onClick={() => {
                      setMenu(null)
                      onRequestDelete(session)
                    }}
                  >
                    <Trash2 size={14} /> Delete
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="profile">
        <button className="avatar" onClick={onOpenProfile} aria-label="Open user profile" type="button">
          {(employeeId || 'AD').slice(0, 2).toUpperCase()}
        </button>
        <div className="profile-info">
          <strong>{profileName || employeeId}</strong>
          <span>{employeeId}</span>
        </div>
        <button
          className="icon-button logout-btn"
          onClick={(e) => {
            e.stopPropagation()
            onLogout()
          }}
          aria-label="Log out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Page                                                                       */
/* ────────────────────────────────────────────────────────────────────────── */
export default function Page() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [isAuthLoaded, setIsAuthLoaded] = useState(false)
  const [employeeId, setEmployeeId] = useState('')
  const [sessionToken, setSessionToken] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [activeId, setActiveId] = useState<string>('new')
  const [active, setActive] = useState('New conversation')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [theme, setTheme] = useState<'light' | 'dark'>('dark')
  const [isThinking, setIsThinking] = useState(false)
  const [toasts, setToasts] = useState<ToastType[]>([])
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null)
  const [showProfile, setShowProfile] = useState(false)
  const [profileName, setProfileName] = useState('')
  const [profileDept, setProfileDept] = useState('Enterprise Operations')
  const [profileRole, setProfileRole] = useState('Senior Manager')
  const [backendInfo, setBackendInfo] = useState<{ name: string; schema: string; simulated: boolean } | null>(null)
  const [attachment, setAttachment] = useState<{ name: string; text: string } | null>(null)

  const autoScrollRef = useRef(true)
  const fileRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const showToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, message, type }])
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 3200)
  }, [])

  const handleLogout = useCallback(() => {
    abortControllerRef.current?.abort()
    localStorage.removeItem('cira-emp-id')
    localStorage.removeItem('cira-token')
    setLoggedIn(false)
    setSessionToken('')
    setSessions([])
    setMessages([])
    setActiveId('new')
    setActive('New conversation')
    setBackendInfo(null)
  }, [])

  /** fetch wrapper that adds auth and force-signs-out on an expired token */
  const api = useCallback(
    async (path: string, options: RequestInit = {}) => {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
          ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
          ...(options.headers || {}),
          Authorization: `Bearer ${sessionToken}`,
        },
      })
      if (res.status === 401) {
        showToast('Session expired — please sign in again.', 'error')
        handleLogout()
        throw new Error('unauthorised')
      }
      return res
    },
    [sessionToken, handleLogout, showToast],
  )

  /* ── boot ─────────────────────────────────────────────────────────────── */
  useEffect(() => {
    const savedToken = localStorage.getItem('cira-token')
    const savedEmpId = localStorage.getItem('cira-emp-id')
    if (savedToken && savedEmpId) {
      setEmployeeId(savedEmpId)
      setSessionToken(savedToken)
      setLoggedIn(true)
    }
    setProfileName(localStorage.getItem('cira-profile-name') || savedEmpId || '')
    setProfileDept(localStorage.getItem('cira-profile-dept') || 'Enterprise Operations')
    setProfileRole(localStorage.getItem('cira-profile-role') || 'Senior Manager')
    const savedTheme = localStorage.getItem('cira-theme') as 'light' | 'dark' | null
    if (savedTheme) setTheme(savedTheme)
    setIsAuthLoaded(true)
  }, [])

  useEffect(() => {
    if (!loggedIn || !sessionToken) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await api('/sessions')
        const data = await res.json()
        if (!cancelled && data.sessions) {
          setSessions(data.sessions.map((s: any) => ({ id: s.id, title: s.title, date: 'Today' })))
        }
      } catch {
        /* handled by api() */
      }
      try {
        const res = await api('/sap/health')
        const data = await res.json()
        if (!cancelled) {
          setBackendInfo({ name: data.active_backend, schema: data.schema, simulated: data.simulated })
        }
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loggedIn, sessionToken, api])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    window.localStorage.setItem('cira-theme', theme)
  }, [theme])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 60
  }

  useEffect(() => {
    if (autoScrollRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, isThinking])

  const toggleTheme = () => setTheme((value) => (value === 'dark' ? 'light' : 'dark'))

  const removeSession = async (session: Session) => {
    setSessions((current) => current.filter((s) => s.id !== session.id))
    setSessionToDelete(null)
    if (activeId === session.id) {
      setActiveId('new')
      setActive('New conversation')
      setMessages([])
    }
    try {
      const res = await api(`/session/${encodeURIComponent(session.id)}`, { method: 'DELETE' })
      showToast(res.ok || res.status === 404 ? 'Chat deleted' : 'Failed to delete chat', res.ok ? 'success' : 'error')
    } catch {
      /* handled */
    }
  }

  /* ── chat ─────────────────────────────────────────────────────────────── */
  const submit = async () => {
    const value = input.trim()
    if (!value || isThinking) return

    autoScrollRef.current = true
    let currentSessionId = activeId
    let chatTitle = active

    if (activeId === 'new') {
      currentSessionId = newSessionId()
      setActiveId(currentSessionId)
      chatTitle = value.slice(0, 30) + (value.length > 30 ? '…' : '')
      setActive(chatTitle)
      setSessions((current) => [{ id: currentSessionId, title: chatTitle, date: 'Today' }, ...current])

      const capturedSessionId = currentSessionId
      api('/generate_title', { method: 'POST', body: JSON.stringify({ prompt: value }) })
        .then((res) => res.json())
        .then((data) => {
          if (!data?.title) return
          api(`/session/${encodeURIComponent(capturedSessionId)}`, {
            method: 'PUT',
            body: JSON.stringify({ title: data.title }),
          }).then(() => {
            setActiveId((curr) => {
              if (curr === capturedSessionId) setActive(data.title)
              return curr
            })
            setSessions((curr) => curr.map((s) => (s.id === capturedSessionId ? { ...s, title: data.title } : s)))
          })
        })
        .catch(() => {})
    }

    const sessionId = currentSessionId
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    let outgoing = value
    if (attachment?.text) {
      outgoing = `${value}\n\n--- Attached file: ${attachment.name} ---\n${attachment.text.slice(0, 4000)}`
    }

    setMessages((current) => [...current, { role: 'user', content: value, timestamp }])
    setInput('')
    setAttachment(null)
    setIsThinking(true)

    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    const streamingId = Date.now()
    setMessages((current) => [...current, { role: 'assistant', content: '', timestamp, _streamingId: streamingId }])

    const patch = (updater: (m: Message) => Message) =>
      setMessages((current) => current.map((m) => (m._streamingId === streamingId ? updater(m) : m)))

    const processEvent = (raw: string) => {
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue
        let parsed: any
        try {
          parsed = JSON.parse(line.slice(5).trim())
        } catch {
          continue
        }
        switch (parsed.type) {
          case 'chunk':
            patch((m) => ({ ...m, content: m.content + parsed.text, status: undefined }))
            break
          case 'status':
            patch((m) => ({ ...m, status: parsed.text }))
            break
          case 'backend':
            setBackendInfo({ name: parsed.name, schema: parsed.schema, simulated: parsed.simulated })
            break
          case 'tabular':
            patch((m) => ({ ...m, data: parsed.data, entity: parsed.entity, meta: parsed.meta, status: undefined }))
            break
          case 'chart':
            patch((m) => ({ ...m, chart: parsed }))
            break
          case 'source':
            patch((m) => ({ ...m, sources: Array.from(new Set([...(m.sources || []), String(parsed.name)])) }))
            break
          case 'error':
            patch((m) => ({ ...m, error: parsed.text, status: undefined }))
            break
          case 'done':
            patch((m) => ({ ...m, status: undefined }))
            break
          default:
            break
        }
      }
    }

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}` },
        body: JSON.stringify({ query: outgoing, session_id: sessionId }),
        signal: abortController.signal,
      })

      if (res.status === 401) {
        showToast('Session expired — please sign in again.', 'error')
        handleLogout()
        return
      }
      if (!res.ok || !res.body) throw new Error(`Backend returned ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value: chunk } = await reader.read()
        if (done) {
          if (buffer.trim()) processEvent(buffer)
          break
        }
        buffer += decoder.decode(chunk, { stream: true })
        const events = buffer.split('\n\n') // SSE event boundary
        buffer = events.pop() ?? ''
        events.forEach(processEvent)
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        patch((m) => ({
          ...m,
          content: m.content || '',
          error: `Could not reach the CIRA backend (${err?.message ?? 'network error'}). Check that the API is running.`,
        }))
      }
    } finally {
      setIsThinking(false)
      abortControllerRef.current = null
    }
  }

  const stopGeneration = () => {
    abortControllerRef.current?.abort()
    setIsThinking(false)
  }

  const selectChat = async (id: string, title: string) => {
    if (activeId === id) return
    abortControllerRef.current?.abort()
    setActiveId(id)
    setActive(title)
    if (window.innerWidth < 720) setCollapsed(true)

    if (id === 'new') {
      setMessages([])
      return
    }

    try {
      const res = await api(`/history/${encodeURIComponent(id)}`)
      const data = await res.json()
      setMessages(
        (data.messages || []).map((m: any) => ({
          role: m.role,
          content: m.content,
          data: m.data,
          entity: m.entity,
          meta: m.meta,
          chart: m.chart,
        })),
      )
    } catch {
      setMessages([])
    }
  }

  const handleLogin = (user: { employee_id: string; name: string }, token: string) => {
    localStorage.setItem('cira-emp-id', user.employee_id)
    localStorage.setItem('cira-token', token)
    setEmployeeId(user.employee_id)
    setProfileName(localStorage.getItem('cira-profile-name') || user.name || user.employee_id)
    setSessionToken(token)
    setLoggedIn(true)
  }

  const onPickFile = async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await api('/upload', { method: 'POST', body: form })
      const data = await res.json()
      if (data.usable_as_context) {
        setAttachment({ name: data.name, text: data.text_preview })
        showToast(`${data.name} attached — it will be sent with your next message`)
      } else {
        showToast(`${data.name} uploaded (${Math.round(data.size / 1024)} KB). Text extraction is only supported for txt/csv/md/json.`)
      }
    } catch {
      showToast('Upload failed', 'error')
    }
  }

  const greeting = useMemo(() => {
    const hour = new Date().getHours()
    const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
    const who = (profileName || employeeId || '').split(' ')[0]
    return who ? `${part}, ${who}.` : `${part}.`
  }, [profileName, employeeId])

  if (!isAuthLoaded) return null
  if (!loggedIn) return <Login onLogin={handleLogin} theme={theme} onToggle={toggleTheme} />

  return (
    <>
      <div className="chat-blur-film" />
      {!collapsed && <div className="mobile-sidebar-backdrop" onClick={() => setCollapsed(true)} />}
      <main className="app-shell">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed(!collapsed)}
          onLogout={handleLogout}
          activeId={activeId}
          onSelect={selectChat}
          sessions={sessions}
          setSessions={setSessions}
          sessionToken={sessionToken}
          employeeId={employeeId}
          profileName={profileName}
          showToast={showToast}
          onRequestDelete={(s) => setSessionToDelete(s)}
          onOpenProfile={() => setShowProfile(true)}
        />
        <section className="chat-shell">
          <header className="chat-header">
            <div className="mobile-title">
              <button className="icon-button mobile-menu" onClick={() => setCollapsed(!collapsed)} aria-label="Open menu">
                <Menu size={20} />
              </button>
              <div>
                <span className="eyebrow">RAG WORKSPACE</span>
                <h2>{active}</h2>
              </div>
            </div>
            <div className="header-actions">
              {backendInfo && (
                <span className={`backend-pill ${backendInfo.simulated ? 'warn' : ''}`} title={`${backendInfo.name} · schema ${backendInfo.schema}`}>
                  <Database size={12} /> {backendInfo.simulated ? 'Sandbox data' : 'Live SAP'} · {backendInfo.schema}
                </span>
              )}
              <ThemeToggle theme={theme} onToggle={toggleTheme} />
              <button className="secondary-button" onClick={() => selectChat('new', 'New conversation')}>
                <Plus size={16} /> New chat
              </button>
            </div>
          </header>

          <div className="chat-scroll" ref={scrollRef} onScroll={handleScroll}>
            <div className="chat-container">
              {messages.length === 0 && (
                <div className="chat-intro">
                  <div className="intro-icon">
                    <Sparkles size={20} />
                  </div>
                  <div>
                    <h1>{greeting}</h1>
                    <p>Ask anything about your SAP Business One data — invoices, orders, stock, vendors, the general ledger.</p>
                    <div className="suggestions">
                      {[
                        'Show me all open invoices from last quarter',
                        'Which vendors have the highest purchase order value?',
                        'Give me a pie chart of stock value by warehouse',
                        'Top 10 customers by revenue this year',
                      ].map((s) => (
                        <button key={s} onClick={() => setInput(s)}>
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <div className={`message-row ${message.role}`} key={message._streamingId ?? `${message.role}-${index}`}>
                  <div className="message-avatar">{message.role === 'assistant' ? <BrandMark /> : employeeId.slice(0, 2).toUpperCase()}</div>
                  <div className="message-content">
                    <span className="message-author">
                      {message.role === 'assistant' ? 'CIRA AI' : 'You'} <small>· {message.timestamp || 'just now'}</small>
                    </span>

                    {message.role === 'assistant' && !message.content && !message.data && !message.error && isThinking && index === messages.length - 1 ? (
                      <div className="bubble typing-bubble">
                        <div className="typing-indicator">
                          <span />
                          <span />
                          <span />
                        </div>
                        {message.status && <p className="status-line">{message.status}</p>}
                      </div>
                    ) : (
                      <div className="bubble">
                        {message.role === 'assistant' ? (
                          <>
                            {message.status && <p className="status-line">{message.status}</p>}
                            {message.content && (
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                            )}
                            {message.error && (
                              <p className="error-line">
                                <AlertTriangle size={14} /> {message.error}
                              </p>
                            )}
                          </>
                        ) : (
                          message.content
                        )}
                        {message.chart && <ChartCard payload={message.chart} />}
                        {message.data !== undefined && message.data !== null && (
                          <DataCard payload={message.data} entity={message.entity} meta={message.meta} />
                        )}
                        {message.sources && message.sources.length > 0 && (
                          <div className="source-capsules">
                            {message.sources.map((src, idx) => (
                              <div key={`${src}-${idx}`} className="source-capsule">
                                <Database size={12} /> {src}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <footer className="composer-wrap">
            {attachment && (
              <div className="attachment-chip">
                <Paperclip size={12} /> {attachment.name}
                <button onClick={() => setAttachment(null)} aria-label="Remove attachment">
                  ×
                </button>
              </div>
            )}
            <div className="composer">
              <button className="icon-button" onClick={() => fileRef.current?.click()} aria-label="Attach file">
                <Paperclip size={18} />
              </button>
              <input
                ref={fileRef}
                type="file"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) onPickFile(file)
                  e.target.value = ''
                }}
              />
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={(e) => {
                  const el = e.currentTarget
                  el.style.height = 'auto'
                  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    submit()
                  }
                }}
                placeholder="Ask anything about your SAP data…"
                rows={1}
                style={{ resize: 'none', overflowY: 'auto' }}
              />
              {isThinking ? (
                <button className="send-button stop" onClick={stopGeneration} aria-label="Stop generating">
                  <Square size={14} />
                </button>
              ) : (
                <button className="send-button" onClick={submit} aria-label="Send message" disabled={!input.trim()}>
                  <BrandMark />
                </button>
              )}
            </div>
            <p className="composer-note">CIRA reads your ERP read-only. Verify important figures before acting.</p>
          </footer>
        </section>
      </main>

      {sessionToDelete && (
        <div className="modal-overlay" onClick={() => setSessionToDelete(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete chat</h3>
            <p>Delete “{sessionToDelete.title}”? This cannot be undone.</p>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setSessionToDelete(null)}>
                Cancel
              </button>
              <button className="btn-confirm" onClick={() => removeSession(sessionToDelete)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {showProfile && (
        <div className="modal-overlay" onClick={() => setShowProfile(false)}>
          <div className="modal-content profile-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>User profile</h3>
            <div className="profile-form">
              <label>
                Name <input value={profileName} onChange={(e) => setProfileName(e.target.value)} />
              </label>
              <label>
                Employee ID <input defaultValue={employeeId} disabled />
              </label>
              <label>
                Department <input value={profileDept} onChange={(e) => setProfileDept(e.target.value)} />
              </label>
              <label>
                Role <input value={profileRole} onChange={(e) => setProfileRole(e.target.value)} />
              </label>
            </div>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setShowProfile(false)}>
                Close
              </button>
              <button
                className="btn-confirm btn-primary"
                onClick={() => {
                  localStorage.setItem('cira-profile-name', profileName)
                  localStorage.setItem('cira-profile-dept', profileDept)
                  localStorage.setItem('cira-profile-role', profileRole)
                  showToast('Profile updated')
                  setShowProfile(false)
                }}
              >
                Save changes
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === 'success' ? <Check size={16} /> : <AlertTriangle size={16} />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </>
  )
}
