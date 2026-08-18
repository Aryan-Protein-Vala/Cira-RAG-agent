'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, BarChart3, Check, ChevronLeft, ChevronRight, Clipboard, FileJson, FileSpreadsheet, LogOut, Menu, MessageSquare, Moon, MoreHorizontal, Paperclip, Pencil, Plus, Search, ShieldCheck, Sparkles, Sun, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { exportToExcel } from '@/lib/export'

const fallbackDataPayload = { 
  report: 'Q3 Procurement Variance', 
  period: 'July 01 – September 30, 2024', 
  rows: [
    { plant: 'DE-1000', spend: '$2,481,920', variance: '+8.4%' }, 
    { plant: 'US-2200', spend: '$1,923,410', variance: '-2.1%' }, 
    { plant: 'SG-3100', spend: '$884,204', variance: '+4.8%' }
  ] 
}

type Message = { role: 'user' | 'assistant'; content: string; data?: any; entity?: string }
type Session = { id: number; title: string; date: string }

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
  )
}

function DataCard({ payload, entity }: { payload?: any; entity?: string }) { 
  const rawData: any[] = Array.isArray(payload) && payload.length > 0 ? payload : fallbackDataPayload.rows;
  const headers = Object.keys(rawData[0]);
  const previewRows = rawData.slice(0, 3);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard?.writeText(JSON.stringify(rawData, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const downloadJSON = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(rawData, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${entity ?? 'sap'}_export.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="data-card">
      <div className="data-card-head">
        <div>
          <span className="data-label"><BarChart3 size={13} /> STRUCTURED RESULT</span>
          <strong>{entity ?? 'SAP Data'}</strong>
        </div>
        <span className="row-count">{rawData.length} rows</span>
      </div>
      <p className="data-period">Previewing {previewRows.length} of {rawData.length} records</p>
      <div className="mini-table">
        <div className="mini-row mini-head" style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 3)}, 1fr)` }}>
          {headers.slice(0, 3).map((h) => <span key={h}>{h}</span>)}
        </div>
        {previewRows.map((row, i) => (
          <div className="mini-row" key={i} style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 3)}, 1fr)` }}>
            {headers.slice(0, 3).map((h) => (
              <span key={h}>{String(row[h] ?? '')}</span>
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

function Sidebar({ collapsed, onToggle, onLogout, active, onSelect, sessions, setSessions, theme, onTheme, sessionToken, employeeId }: { collapsed: boolean; onToggle: () => void; onLogout: () => void; active: string; onSelect: (title: string) => void; sessions: Session[]; setSessions: (sessions: Session[]) => void; theme: 'light' | 'dark'; onTheme: () => void; sessionToken: string; employeeId: string; }) { 
  const [query, setQuery] = useState(''); 
  const [menu, setMenu] = useState<number | null>(null); 
  const [editing, setEditing] = useState<number | null>(null); 
  const [editValue, setEditValue] = useState(''); 
  const filtered = useMemo(() => sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase())), [query, sessions]); 
  
  const rename = (session: Session) => { setEditing(session.id); setEditValue(session.title); setMenu(null) }; 
  const saveRename = async (id: number, oldTitle: string) => { 
    const title = editValue.trim(); 
    if (title && title !== oldTitle) {
      setSessions(sessions.map((s) => s.id === id ? { ...s, title } : s));
      try {
        await fetch(`http://localhost:8000/session/${employeeId}__${oldTitle}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${sessionToken}` },
          body: JSON.stringify({ title: `${employeeId}__${title}` })
        });
      } catch (err) { console.error('Rename failed', err) }
    }
    setEditing(null);
  }; 
  const remove = async (session: Session) => { 
    setSessions(sessions.filter((s) => s.id !== session.id)); 
    setMenu(null); 
    if (active === session.title) onSelect('New conversation');
    try {
      await fetch(`http://localhost:8000/session/${employeeId}__${session.title}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${sessionToken}` }
      });
    } catch (err) { console.error('Delete failed', err) }
  };
  
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-top">
        <div className="sidebar-brand"><BrandMark /><span>CIRA</span></div>
        <button className="icon-button" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
      {!collapsed && (
        <>
          <div className="sidebar-actions">
            <button className="new-chat" onClick={() => onSelect('New conversation')}>
              <Plus size={16} /> 
              <span>New chat</span>
            </button>
            {/* <button className="theme-toggle" onClick={onTheme} aria-label="Toggle theme">
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button> */}
          </div>
          <div className="history-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search history" /></div>
          <div className="history">
            {['Today', 'Previous 7 days'].map((date) => (
              <div className="history-group" key={date}>
                <span className="group-label">{date}</span>
                {filtered.filter((s) => s.date === date).map((session) => (
                  <div className={`history-item ${active === session.title ? 'active' : ''}`} key={session.id} onClick={() => editing !== session.id && onSelect(session.title)}>
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
                        <button className="delete-action" onClick={() => remove(session)}><Trash2 size={14} /> Delete</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div className="profile">
            <div className="avatar">AM</div>
            <div className="profile-info"><strong>Alex Morgan</strong><span>EMP-20481</span></div>
            <button className="icon-button" onClick={onLogout} aria-label="Log out"><LogOut size={16} /></button>
          </div>
        </>
      )}
    </aside>
  ) 
}

export default function Page() { 
  const [loggedIn, setLoggedIn] = useState(false); 
  const [employeeId, setEmployeeId] = useState('EMP-20481');
  const [sessionToken, setSessionToken] = useState('');  // Bearer token passed on every API call
  const [collapsed, setCollapsed] = useState(false); 
  const [active, setActive] = useState('New conversation'); 
  const [messages, setMessages] = useState<Message[]>(initialMessages); 
  const [input, setInput] = useState(''); 
  const [sessions, setSessions] = useState(initialSessions); 
  const [theme, setTheme] = useState<'light' | 'dark'>('light'); 
  const [isThinking, setIsThinking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null); 
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);  // Fix 6.2: cancel in-flight streams on session switch

  useEffect(() => { 
    if (loggedIn && sessionToken) {
      fetch('http://localhost:8000/sessions', {
        headers: { 'Authorization': `Bearer ${sessionToken}` }
      })
        .then(res => res.json())
        .then(data => {
          if (data.sessions) {
            setSessions(data.sessions.map((s: any, idx: number) => ({
              id: idx,
              title: s.title.replace(`${employeeId}__`, ''), // Strip prefix
              date: 'Today' // Mocking date for simplicity
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

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isThinking]);

  const toggleTheme = () => setTheme((value) => value === 'dark' ? 'light' : 'dark'); 
  
  const submit = async () => { 
    const value = input.trim(); 
    if (!value || isThinking) return; 
    
    const sessionId = `${employeeId}__${active}`;
    setMessages((current) => [...current, { role: 'user', content: value }]); 
    setInput(''); 
    setIsThinking(true);

    // Fix 6.2: Cancel any previous in-flight stream before starting a new one
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const streamingId = Date.now();
    setMessages((current) => [...current, { role: 'assistant', content: '', _streamingId: streamingId } as any]);

    try {
      const res = await fetch('http://localhost:8000/chat', {
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
            const parsed = JSON.parse(line.slice(6));
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
  
  const selectChat = async (title: string) => { 
    setActive(title);
    if (title === 'New conversation') {
      setMessages([]);
      return;
    }
    const sessionId = `${employeeId}__${title}`;
    try {
      const res = await fetch(`http://localhost:8000/history/${encodeURIComponent(sessionId)}`, {
        headers: { 'Authorization': `Bearer ${sessionToken}` },
      });
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {
        setMessages(data.messages.map((m: any) => ({ role: m.role, content: m.content, data: m.data })));
      } else {
        setMessages([{ role: 'assistant', content: `I'm ready to continue with "${title}". What would you like to know?` }]);
      }
    } catch {
      setMessages([{ role: 'assistant', content: `I'm ready to continue with "${title}". What would you like to know?` }]);
    }
  }; 
  
  if (!loggedIn) return <Login onLogin={(id, token) => { setEmployeeId(id); setSessionToken(token); setLoggedIn(true); }} theme={theme} onToggle={toggleTheme} />; 
  
  return (
    <main className="app-shell">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} onLogout={() => setLoggedIn(false)} active={active} onSelect={selectChat} sessions={sessions} setSessions={setSessions} theme={theme} onTheme={toggleTheme} sessionToken={sessionToken} employeeId={employeeId} />
      <section className="chat-shell">
        <header className="chat-header">
          <div className="mobile-title">
            <button className="icon-button mobile-menu" onClick={() => setCollapsed(!collapsed)} aria-label="Open menu"><Menu size={20} /></button>
            <div><span className="eyebrow">RAG WORKSPACE</span><h2>{active}</h2></div>
          </div>
          <div className="header-actions">
            <button className="secondary-button" onClick={() => selectChat('New conversation')}><Plus size={16} /> New chat</button>
          </div>
        </header>
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-intro">
            <div className="intro-icon"><Sparkles size={20} /></div>
            <div><h1>Good morning, Alex.</h1><p>Ask questions about your SAP data in plain language.</p></div>
          </div>
          {messages.map((message, index) => (
            <div className={`message-row ${message.role}`} key={index}>
              <div className="message-avatar">{message.role === 'assistant' ? <BrandMark /> : employeeId.slice(0, 2).toUpperCase()}</div>
              <div className="message-content">
                <span className="message-author">{message.role === 'assistant' ? 'CIRA AI' : 'You'} <small>{message.role === 'assistant' ? '· just now' : ''}</small></span>
                <div className="bubble">
                  {message.role === 'assistant' ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                  ) : (
                    message.content
                  )}
                  {message.data && <DataCard payload={message.data} entity={message.entity} />}
                </div>
              </div>
            </div>
          ))}
          {isThinking && (
             <div className="message-row assistant">
              <div className="message-avatar"><BrandMark /></div>
              <div className="message-content">
                <span className="message-author">CIRA AI <small>· thinking...</small></span>
                <div className="typing-indicator"><span /><span /><span /></div>
              </div>
            </div>
          )}
        </div>
        <footer className="composer-wrap">
          <div className="composer">
            <button className="icon-button" onClick={() => fileRef.current?.click()} aria-label="Attach file"><Paperclip size={18} /></button>
            <input ref={fileRef} type="file" hidden />
            <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); submit() } }} placeholder="Ask anything about your SAP data..." rows={1} />
            <button className="send-button" disabled={isThinking} onClick={submit} aria-label="Send message"><ArrowUp size={18} /></button>
          </div>
          <p className="composer-note">CIRA can make mistakes. Verify important data.</p>
        </footer>
      </section>
    </main>
  ) 
}
