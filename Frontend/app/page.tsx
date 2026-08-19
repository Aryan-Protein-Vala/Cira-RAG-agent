'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, BarChart3, Check, ChevronLeft, ChevronRight, Clipboard, Database, FileJson, FileSpreadsheet, LogOut, Menu, MessageSquare, Moon, MoreHorizontal, Paperclip, Pencil, Plus, Search, ShieldCheck, Sparkles, Sun, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { exportToExcel } from '@/lib/export'
import { ChartCard, ChartPayload } from './ChartCard'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const fallbackDataPayload = { 
  report: 'Q3 Procurement Variance', 
  period: 'July 01 – September 30, 2024', 
  rows: [
    { plant: 'DE-1000', spend: '$2,481,920', variance: '+8.4%' }, 
    { plant: 'US-2200', spend: '$1,923,410', variance: '-2.1%' }, 
    { plant: 'SG-3100', spend: '$884,204', variance: '+4.8%' }
  ] 
}

type Message = { role: 'user' | 'assistant'; content: string; data?: any; entity?: string; chart?: ChartPayload; timestamp?: string; sources?: string[] }
type Session = { id: string; title: string; date: string }

const initialMessages: Message[] = []
const initialSessions: Session[] = []

function BrandMark() { return <div className="brand-mark"><span /><span /><span /></div> }

function ThemeToggle({ theme, onToggle }: { theme: 'light' | 'dark'; onToggle: () => void }) { 
  return (
    <button className="theme-toggle" onClick={onToggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
      {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  )
}

/** 
 * Fix 1.3: UTF-8 safe base64 token — btoa() crashes on non-Latin1 chars.
 * Uses TextEncoder + Uint8Array → safe for any Unicode employee ID.
 */
function mintSessionToken(employeeId: string): string {
  const payload = JSON.stringify({ employee_id: employeeId, iat: Math.floor(Date.now() / 1000) });
  const bytes = new TextEncoder().encode(payload);
  const binString = Array.from(bytes, (b) => String.fromCodePoint(b)).join('');
  return btoa(binString);
}

function Login({ onLogin, theme, onToggle }: { onLogin: (id: string, token: string) => void; theme: 'light' | 'dark'; onToggle: () => void }) { 
  const [employee, setEmployee] = useState(''); 
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const ADMIN_ID = 'admin';
  const ADMIN_PASSWORD = 'asdfghjkl;';

  return (
    <>
      <div className="chat-blur-film" style={{ position: 'fixed', inset: 0, zIndex: -1, background: 'rgba(255, 255, 255, 0.4)', backdropFilter: 'blur(12px)' }} />
      <main className="login-shell">
        <div className="login-top">
        <div className="sidebar-brand"><BrandMark /><span>CIRA</span></div>
        <ThemeToggle theme={theme} onToggle={onToggle} />
      </div>
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand"><BrandMark /><span>CIRA</span></div>
        <div className="eyebrow"><ShieldCheck size={14} /> INTERNAL DATA ACCESS</div>
        <h1 id="login-title">Ask your enterprise<br /><em>anything.</em></h1>
        <p className="login-copy">Securely query SAP data with natural language. Built for clarity, speed, and control.</p>
        <form onSubmit={(event) => {
          event.preventDefault();
          setError('');
          const id = employee.trim();
          const pass = password;

          // Admin bypass — always grants access for demo/testing
          if (id.toLowerCase() === ADMIN_ID && pass === ADMIN_PASSWORD) {
            onLogin('ADMIN-001', mintSessionToken('ADMIN-001'));
            return;
          }

          // For all other users: require at least an Employee ID
          if (!id) {
            setError('Please enter your Employee ID.');
            return;
          }

          // In production replace this with a real SSO call.
          // For now, any non-empty Employee ID with any non-empty password grants access.
          if (!pass) {
            setError('Please enter your password.');
            return;
          }

          onLogin(id, mintSessionToken(id));
        }}>
          <label>Employee ID
            <input value={employee} onChange={(event) => setEmployee(event.target.value)} placeholder="e.g. EMP-20481" />
          </label>
          <label>Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" />
          </label>
          {error && <p style={{ color: 'var(--destructive)', fontSize: '11px', margin: '0' }}>{error}</p>}
          <button className="primary-button login-button" type="submit">Sign in securely <ArrowUp size={16} /></button>
        </form>
        <p className="secure-note"><ShieldCheck size={13} /> SSO protected · Your queries are private</p>
      </section>
      </main>
    </>
  )
}

function DataCard({ payload, entity }: { payload?: any; entity?: string }) { 
  if (Array.isArray(payload) && payload.length === 0) {
    return (
      <div className="data-card">
        <div className="data-card-head">
          <div>
            <span className="data-label"><BarChart3 size={13} /> STRUCTURED SAP RESULT</span>
            <strong>{entity ?? 'SAP Data'}</strong>
          </div>
          <span className="row-count">0 records</span>
        </div>
        <p className="data-period" style={{ marginTop: '12px', marginBottom: 0 }}>No records found matching query criteria.</p>
      </div>
    );
  }

  const rawData: any[] = Array.isArray(payload) ? payload : (payload ? [payload] : fallbackDataPayload.rows);
  const headers = rawData.length > 0 && typeof rawData[0] === 'object' && rawData[0] !== null ? Object.keys(rawData[0]) : [];
  const [copied, setCopied] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const filteredData = useMemo(() => {
    let list = rawData;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(row => Object.values(row).some(v => String(v).toLowerCase().includes(q)));
    }
    if (sortKey) {
      list = [...list].sort((a, b) => {
        const valA = a[sortKey];
        const valB = b[sortKey];
        if (typeof valA === 'number' && typeof valB === 'number') {
          return sortAsc ? valA - valB : valB - valA;
        }
        return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
      });
    }
    return list;
  }, [rawData, search, sortKey, sortAsc]);

  const displayRows = showAll ? filteredData : filteredData.slice(0, 4);

  const copy = async () => {
    await navigator.clipboard?.writeText(JSON.stringify(filteredData, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const downloadJSON = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(filteredData, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${entity ?? 'sap'}_export.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const toggleSort = (h: string) => {
    if (sortKey === h) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(h);
      setSortAsc(true);
    }
  };

  return (
    <div className="data-card">
      <div className="data-card-head">
        <div>
          <span className="data-label"><BarChart3 size={13} /> STRUCTURED SAP RESULT</span>
          <strong>{entity ?? 'SAP Data'}</strong>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="row-count">{filteredData.length} records</span>
          {rawData.length > 4 && (
            <button 
              onClick={() => setShowAll(!showAll)}
              style={{
                background: 'rgba(255, 255, 255, 0.08)',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                color: '#38bdf8',
                borderRadius: '8px',
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'var(--cursor-pointer)'
              }}
            >
              {showAll ? 'Show Less' : `View All (${rawData.length})`}
            </button>
          )}
        </div>
      </div>

      {showAll && (
        <div style={{ margin: '10px 0 12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(0, 0, 0, 0.25)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '10px',
            padding: '6px 10px',
            flex: 1
          }}>
            <Search size={13} style={{ color: 'rgba(255, 255, 255, 0.5)' }} />
            <input 
              value={search} 
              onChange={(e) => setSearch(e.target.value)} 
              placeholder="Filter records..." 
              style={{
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: '#fff',
                fontSize: '12px',
                width: '100%'
              }}
            />
          </div>
        </div>
      )}

      <p className="data-period" style={{ marginTop: '4px', marginBottom: '12px' }}>
        Showing {displayRows.length} of {filteredData.length} entries {sortKey ? `· Sorted by ${sortKey} (${sortAsc ? 'ASC' : 'DESC'})` : ''}
      </p>

      <div className="mini-table" style={{ maxHeight: showAll ? '320px' : 'none', overflowY: showAll ? 'auto' : 'visible' }}>
        <div className="mini-row mini-head" style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 5)}, 1fr)` }}>
          {headers.slice(0, 5).map((h) => (
            <span 
              key={h} 
              onClick={() => toggleSort(h)} 
              style={{ cursor: 'var(--cursor-pointer)', display: 'flex', alignItems: 'center', gap: '4px' }}
              title="Click to sort"
            >
              {h} {sortKey === h ? (sortAsc ? '▲' : '▼') : ''}
            </span>
          ))}
        </div>
        {displayRows.map((row, i) => (
          <div className="mini-row" key={i} style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 5)}, 1fr)` }}>
            {headers.slice(0, 5).map((h) => (
              <span key={h} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {String(row[h] ?? '')}
              </span>
            ))}
          </div>
        ))}
      </div>

      <div className="data-actions">
        <button onClick={() => exportToExcel(rawData, `${entity ?? 'sap'}_export.xlsx`)}>
          <FileSpreadsheet size={14} /> Download Excel
        </button>
        <button onClick={downloadJSON}><FileJson size={14} /> Download JSON</button>
        <button onClick={copy}>{copied ? <Check size={14} /> : <Clipboard size={14} />} {copied ? 'Copied' : 'Copy Data'}</button>
      </div>
    </div>
  )
}

type ToastType = { id: number; message: string; type: 'success' | 'error' };

function Sidebar({ 
  collapsed, 
  onToggle, 
  onLogout, 
  activeId, 
  onSelect, 
  sessions, 
  setSessions, 
  theme, 
  onTheme, 
  sessionToken, 
  employeeId, 
  showToast,
  onRequestDelete,
  onOpenProfile
}: { 
  collapsed: boolean; 
  onToggle: () => void; 
  onLogout: () => void; 
  activeId: string; 
  onSelect: (id: string, title: string) => void; 
  sessions: Session[]; 
  setSessions: (sessions: Session[]) => void; 
  theme: 'light' | 'dark'; 
  onTheme: () => void; 
  sessionToken: string; 
  employeeId: string; 
  showToast: (msg: string, type?: 'success' | 'error') => void;
  onRequestDelete: (session: Session) => void;
  onOpenProfile: () => void;
}) { 
  const [query, setQuery] = useState(''); 
  const [menu, setMenu] = useState<string | null>(null); 
  const [editing, setEditing] = useState<string | null>(null); 
  const [editValue, setEditValue] = useState(''); 
  const filtered = useMemo(() => sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase())), [query, sessions]); 
  
  const rename = (session: Session) => { setEditing(session.id); setEditValue(session.title); setMenu(null) }; 
  const saveRename = async (id: string, oldTitle: string) => { 
    const title = editValue.trim(); 
    if (title && title !== oldTitle) {
      setSessions(sessions.map((s) => s.id === id ? { ...s, title } : s));
      try {
        const res = await fetch(`${API_BASE}/session/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionToken}` },
          body: JSON.stringify({ title })
        });
        if (res.ok) showToast('Chat renamed', 'success');
      } catch (err) { 
        console.error('Rename failed', err);
        showToast('Rename failed', 'error');
      }
    }
    setEditing(null);
  }; 
  
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
      <div className="history-search"><BrandMark /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search history" /></div>
      <div className="history">
            <div className="history-group">
              {filtered.map((session) => (
                <div className={`history-item ${activeId === session.id ? 'active' : ''}`} key={session.id} onClick={() => editing !== session.id && onSelect(session.id, session.title)}>
                  <MessageSquare size={15} />
                  <div className="history-title">
                    {editing === session.id ? (
                      <input autoFocus value={editValue} onChange={(event) => setEditValue(event.target.value)} onBlur={() => saveRename(session.id, session.title)} onKeyDown={(event) => { if (event.key === 'Enter') saveRename(session.id, session.title); if (event.key === 'Escape') setEditing(null) }} />
                    ) : (
                      <span>{session.title}</span>
                    )}
                  </div>
                  <button className="history-menu-button" onClick={(event) => { event.stopPropagation(); setMenu(menu === session.id ? null : session.id) }} aria-label={`Options for ${session.title}`}><MoreHorizontal size={16} /></button>
                  {menu === session.id && (
                    <div className="history-menu" onClick={(event) => event.stopPropagation()}>
                          <button onClick={() => rename(session)}><Pencil size={14} /> Rename</button>
                          <button className="delete-action" onClick={() => { setMenu(null); onRequestDelete(session); }}><Trash2 size={14} /> Delete</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
      <div className="profile">
        <button 
          className="avatar" 
          onClick={onOpenProfile} 
          aria-label="Open user profile" 
          type="button"
        >
          {(employeeId || 'AD').slice(0, 2).toUpperCase()}
        </button>
        <div className="profile-info"><strong>{employeeId.toUpperCase().startsWith('ADMIN') ? 'System Admin' : employeeId}</strong><span>{employeeId || 'EMP-20481'}</span></div>
        <button className="icon-button logout-btn" onClick={(e) => { e.stopPropagation(); onLogout(); }} aria-label="Log out"><LogOut size={16} /></button>
      </div>
    </aside>
  ) 
}

export default function Page() { 
  const [loggedIn, setLoggedIn] = useState(false); 
  const [isAuthLoaded, setIsAuthLoaded] = useState(false);
  const [employeeId, setEmployeeId] = useState('');
  const [sessionToken, setSessionToken] = useState('');  // Bearer token passed on every API call
  const [collapsed, setCollapsed] = useState(false); 
  const [activeId, setActiveId] = useState<string>('new'); 
  const [active, setActive] = useState('New conversation'); 
  const [messages, setMessages] = useState<Message[]>(initialMessages); 
  const [input, setInput] = useState(''); 
  const [sessions, setSessions] = useState<Session[]>(initialSessions); 
  const [theme, setTheme] = useState<'light' | 'dark'>('light'); 
  const [isThinking, setIsThinking] = useState(false);
  const [toasts, setToasts] = useState<ToastType[]>([]);
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null);
  const [showProfile, setShowProfile] = useState(false);
  const [profileName, setProfileName] = useState('System Admin');
  const [profileDept, setProfileDept] = useState('Enterprise Operations');
  const [profileRole, setProfileRole] = useState('Senior Manager');
  const autoScrollRef = useRef(true);
  const fileRef = useRef<HTMLInputElement>(null); 
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);  // Fix 6.2: cancel in-flight streams on session switch

  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    const id = Date.now();
    setToasts(current => [...current, { id, message, type }]);
    setTimeout(() => {
      setToasts(current => current.filter(t => t.id !== id));
    }, 3000);
  };

  const removeSession = async (session: Session) => { 
    setSessions(current => current.filter((s) => s.id !== session.id)); 
    setSessionToDelete(null);
    if (activeId === session.id) selectChat('new', 'New conversation');
    try {
      const res = await fetch(`${API_BASE}/session/${session.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${sessionToken}` }
      });
      if (res.ok || res.status === 404) {
        showToast('Chat deleted', 'success');
      } else {
        showToast('Failed to delete chat', 'error');
      }
    } catch (err) { 
      console.error('Delete failed', err);
      showToast('Error connecting to server', 'error');
    }
  };

  useEffect(() => {
    const savedToken = localStorage.getItem('cira-token');
    const savedEmpId = localStorage.getItem('cira-emp-id');
    if (savedToken && savedEmpId) {
      setEmployeeId(savedEmpId);
      setProfileName(savedEmpId.toUpperCase().startsWith('ADMIN') ? 'System Admin' : savedEmpId);
      setSessionToken(savedToken);
      setLoggedIn(true);
    }
    const savedTheme = localStorage.getItem('cira-theme') as 'light' | 'dark' | null;
    if (savedTheme) setTheme(savedTheme);
    setIsAuthLoaded(true);
  }, []);

  useEffect(() => { 
    if (loggedIn && sessionToken) {
      fetch(`${API_BASE}/sessions`, {
        headers: { 'Authorization': `Bearer ${sessionToken}` }
      })
        .then(res => res.json())
        .then(data => {
          if (data.sessions) {
            setSessions(data.sessions.map((s: any) => ({
              id: s.id,
              title: s.title,
              date: 'Today'
            })));
          }
        })
        .catch(console.error);
    }
  }, [loggedIn, sessionToken]);

  useEffect(() => { 
    document.documentElement.classList.toggle('dark', theme === 'dark'); 
    window.localStorage.setItem('cira-theme', theme) 
  }, [theme]); 

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 50;
    autoScrollRef.current = isNearBottom;
  };

  useEffect(() => {
    if (autoScrollRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  const toggleTheme = () => setTheme((value) => value === 'dark' ? 'light' : 'dark'); 
  
  const submit = async () => { 
    const value = input.trim(); 
    if (!value || isThinking) return; 

    autoScrollRef.current = true;
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }

    let currentSessionId = activeId;
    let chatTitle = active;
    const isNew = activeId === 'new';
    
    if (isNew) {
      currentSessionId = crypto.randomUUID();
      setActiveId(currentSessionId);
      chatTitle = value.slice(0, 30) + (value.length > 30 ? '...' : '');
      setActive(chatTitle);
      setSessions(current => [{ id: currentSessionId, title: chatTitle, date: 'Today' }, ...current]);
      
      // Fire background title generation
      fetch(`${API_BASE}/generate_title`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionToken}` },
        body: JSON.stringify({ prompt: value })
      })
      .then(res => res.json())
      .then(data => {
        if (data.title) {
          fetch(`${API_BASE}/session/${currentSessionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionToken}` },
            body: JSON.stringify({ title: data.title })
          }).then(() => {
            setActive(curr => curr === chatTitle ? data.title : curr);
            setSessions(curr => curr.map(s => s.id === currentSessionId ? { ...s, title: data.title } : s));
          });
        }
      })
      .catch(console.error);
    }
    
    const sessionId = currentSessionId;
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((current) => [...current, { role: 'user', content: value, timestamp }]); 
    setInput(''); 
    setIsThinking(true);

    // Fix 6.2: Cancel any previous in-flight stream before starting a new one
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const streamingId = Date.now();
    setMessages((current) => [...current, { role: 'assistant', content: '', timestamp, _streamingId: streamingId } as any]);

    const jsonTryParse = (str: string) => {
      try { return JSON.parse(str) } catch { return null }
    };

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${sessionToken}`,
        },
        body: JSON.stringify({ query: value, session_id: sessionId }),
        signal: abortController.signal,  // Fix 6.2: fetch is cancellable
      });

      if (!res.body) throw new Error('No stream');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const processLines = (lines: string[]) => {
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const parsed = jsonTryParse(line.slice(6));
            if (!parsed) continue;
            if (parsed.type === 'chunk') {
              setMessages((current) => current.map((m: any) =>
                m._streamingId === streamingId
                  ? { ...m, content: m.content + parsed.text }
                  : m
              ));
            } else if (parsed.type === 'tabular') {
              setMessages((current) => current.map((m: any) =>
                m._streamingId === streamingId
                  ? { ...m, data: parsed.data, entity: parsed.entity }
                  : m
              ));
            } else if (parsed.type === 'chart') {
              setMessages((current) => current.map((m: any) =>
                m._streamingId === streamingId
                  ? { ...m, chart: parsed }
                  : m
              ));
            } else if (parsed.type === 'source' && parsed.name) {
              setMessages((current) => current.map((m: any) =>
                m._streamingId === streamingId
                  ? { ...m, sources: Array.from(new Set([...(m.sources || []), String(parsed.name)])) }
                  : m
              ));
            }
          } catch {}
        }
      };

      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) {
          // Fix 6.1: Drain remaining buffer after stream ends (handles streams without trailing \n)
          if (buffer.trim()) processLines([buffer]);
          break;
        }
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        processLines(lines);
      }
    } catch (err: any) {
      // AbortError is expected when user switches chat — not a real error
      if (err?.name !== 'AbortError') {
        setMessages((current) => current.map((m: any) =>
          m._streamingId === streamingId
            ? { ...m, content: 'Sorry, I encountered an error connecting to the FastAPI backend.' }
            : m
        ));
      }
    } finally {
      setIsThinking(false);
    }
  }; 
  
  const selectChat = async (id: string, title: string) => { 
    if (activeId === id) return;
    
    abortControllerRef.current?.abort();

    setActiveId(id);
    setActive(title);
    setCollapsed(true);

    if (id === 'new') {
      setMessages([]);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/history/${encodeURIComponent(id)}`, {
        headers: { 'Authorization': `Bearer ${sessionToken}` },
      });
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {
        setMessages(data.messages.map((m: any) => ({
          role: m.role,
          content: m.content,
          data: m.data,
          entity: m.entity,
          chart: m.chart
        })));
      } else {
        setMessages([{ role: 'assistant', content: `I'm ready to continue with "${title}". What would you like to know?` }]);
      }
    } catch {
      setMessages([{ role: 'assistant', content: `I'm ready to continue with "${title}". What would you like to know?` }]);
    }
  }; 
  
  const handleLogin = (id: string, token: string) => {
    localStorage.setItem('cira-emp-id', id);
    localStorage.setItem('cira-token', token);
    setEmployeeId(id);
    setProfileName(id.toUpperCase().startsWith('ADMIN') ? 'System Admin' : id);
    setSessionToken(token);
    setLoggedIn(true);
  };

  const handleLogout = () => {
    localStorage.removeItem('cira-emp-id');
    localStorage.removeItem('cira-token');
    setLoggedIn(false);
    setSessionToken('');
    setSessions([]);
    setMessages([]);
    setActiveId('new');
    setActive('New conversation');
  };

  if (!isAuthLoaded) return null;
  if (!loggedIn) return <Login onLogin={handleLogin} theme={theme} onToggle={toggleTheme} />; 
  
  return (
    <>
      <div className="chat-blur-film" style={{ position: 'fixed', inset: 0, zIndex: -1, background: 'rgba(255, 255, 255, 0.4)', backdropFilter: 'blur(12px)' }} />
      <main className="app-shell">
        <Sidebar 
          collapsed={collapsed} 
          onToggle={() => setCollapsed(!collapsed)} 
          onLogout={handleLogout} 
          activeId={activeId} 
          onSelect={selectChat} 
          sessions={sessions} 
          setSessions={setSessions} 
          theme={theme} 
          onTheme={toggleTheme} 
          sessionToken={sessionToken} 
          employeeId={employeeId} 
          showToast={showToast}
          onRequestDelete={(s) => setSessionToDelete(s)}
          onOpenProfile={() => setShowProfile(true)}
        />
        <section className="chat-shell">
        <header className="chat-header">
          <div className="mobile-title">
            <button className="icon-button mobile-menu" onClick={() => setCollapsed(!collapsed)} aria-label="Open menu"><Menu size={20} /></button>
            <div><span className="eyebrow">RAG WORKSPACE</span><h2>{active}</h2></div>
          </div>
          <div className="header-actions">
            <button className="secondary-button" onClick={() => selectChat('new', 'New conversation')}><Plus size={16} /> New chat</button>
          </div>
        </header>
        <div className="chat-scroll" ref={scrollRef} onScroll={handleScroll}>
          <div className="chat-container">
            <div className="chat-intro">
              <div className="intro-icon"><Sparkles size={20} /></div>
              <div><h1>Good morning, Alex.</h1><p>Ask questions about your SAP data in plain language.</p></div>
            </div>
            {messages.map((message, index) => (
              <div className={`message-row ${message.role}`} key={index}>
                <div className="message-avatar">{message.role === 'assistant' ? <BrandMark /> : employeeId.slice(0, 2).toUpperCase()}</div>
                <div className="message-content">
                  <span className="message-author">{message.role === 'assistant' ? 'CIRA AI' : 'You'} <small>· {message.timestamp || 'just now'}</small></span>
                  <div className="bubble">
                    {message.role === 'assistant' ? (
                      message.content === '' && isThinking && index === messages.length - 1 ? (
                        <div className="typing-indicator"><span /><span /><span /></div>
                      ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                      )
                    ) : (
                      message.content
                    )}
                    {message.chart && <ChartCard payload={message.chart} />}
                    {message.data && <DataCard payload={message.data} entity={message.entity} />}
                    {message.sources && message.sources.length > 0 && (
                      <div className="source-capsules">
                        {message.sources.map((src: string, idx: number) => (
                          <div key={idx} className="source-capsule"><Database size={12} /> {src}</div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <footer className="composer-wrap">
          <div className="composer">
            <button className="icon-button" onClick={() => fileRef.current?.click()} aria-label="Attach file"><Paperclip size={18} /></button>
            <input ref={fileRef} type="file" hidden />
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); submit() } }} placeholder="Ask anything about your SAP data..." rows={1} />
            <button className="send-button" disabled={isThinking} onClick={submit} aria-label="Send message"><BrandMark /></button>
          </div>
          <p className="composer-note">CIRA can make mistakes. Verify important data.</p>
        </footer>
      </section>
      </main>

      {/* Full-screen Centered Modals */}
      {sessionToDelete && (
        <div className="modal-overlay" onClick={() => setSessionToDelete(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Delete Chat</h3>
            <p>Are you sure you want to delete "{sessionToDelete.title}"? This cannot be undone.</p>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setSessionToDelete(null)}>Cancel</button>
              <button className="btn-confirm" onClick={() => removeSession(sessionToDelete)}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {showProfile && (
        <div className="modal-overlay" onClick={() => setShowProfile(false)}>
          <div className="modal-content profile-modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>User Profile</h3>
            <div className="profile-form">
              <label>Name <input value={profileName} onChange={(e) => setProfileName(e.target.value)} /></label>
              <label>Employee ID <input defaultValue={employeeId} disabled /></label>
              <label>Department <input value={profileDept} onChange={(e) => setProfileDept(e.target.value)} /></label>
              <label>Role <input value={profileRole} onChange={(e) => setProfileRole(e.target.value)} /></label>
            </div>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setShowProfile(false)}>Close</button>
              <button className="btn-confirm" style={{background: 'var(--primary)', color: '#000'}} onClick={() => { showToast('Profile updated'); setShowProfile(false); }}>Save Changes</button>
            </div>
          </div>
        </div>
      )}

      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            {t.type === 'success' ? <Check size={16} /> : <Trash2 size={16} />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </>
  ) 
}
