'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, BarChart3, Check, ChevronLeft, ChevronRight, Clipboard, Download, FileJson, FileSpreadsheet, LogOut, Menu, MessageSquare, MoreHorizontal, Moon, Paperclip, Pencil, Plus, Search, ShieldCheck, Sparkles, Sun, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const fallbackDataPayload = { 
  report: 'Q3 Procurement Variance', 
  period: 'July 01 – September 30, 2024', 
  rows: [
    { plant: 'DE-1000', spend: '$2,481,920', variance: '+8.4%' }, 
    { plant: 'US-2200', spend: '$1,923,410', variance: '-2.1%' }, 
    { plant: 'SG-3100', spend: '$884,204', variance: '+4.8%' }
  ] 
}

type Message = { role: 'user' | 'assistant'; content: string; data?: any }
type Session = { id: number; title: string; date: string }

const initialMessages: Message[] = [
  { role: 'user', content: 'Show me the Q3 procurement variance by plant.' }, 
  { role: 'assistant', content: 'I found the procurement variance for Q3 across 18 plants. The largest positive variance is in DE-1000, driven primarily by raw materials and expedited freight.', data: fallbackDataPayload }
]
const initialSessions: Session[] = [
  { id: 1, title: 'Q3 procurement variance', date: 'Today' }, 
  { id: 2, title: 'Open purchase orders by vendor', date: 'Today' }, 
  { id: 3, title: 'Inventory aging analysis', date: 'Today' }, 
  { id: 4, title: 'Cost center allocations', date: 'Previous 7 days' }, 
  { id: 5, title: 'Materials forecast 2025', date: 'Previous 7 days' }, 
  { id: 6, title: 'Supplier performance review', date: 'Previous 7 days' }
]

function BrandMark() { return <div className="brand-mark"><span /><span /><span /></div> }

function ThemeToggle({ theme, onToggle }: { theme: 'light' | 'dark'; onToggle: () => void }) { 
  return (
    <button className="theme-toggle" onClick={onToggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
      {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  )
}

function Login({ onLogin, theme, onToggle }: { onLogin: (id: string) => void; theme: 'light' | 'dark'; onToggle: () => void }) { 
  const [employee, setEmployee] = useState(''); 
  const [password, setPassword] = useState(''); 
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
        <form onSubmit={(event) => { event.preventDefault(); onLogin(employee || 'EMP-20481') }}>
          <label>Employee ID
            <input value={employee} onChange={(event) => setEmployee(event.target.value)} placeholder="e.g. EMP-20481" />
          </label>
          <label>Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" />
          </label>
          <button className="primary-button login-button" type="submit">Sign in securely <ArrowUp size={16} /></button>
        </form>
        <p className="secure-note"><ShieldCheck size={13} /> SSO protected · Your queries are private</p>
      </section>
    </main>
  )
}

function DataCard({ payload }: { payload?: any }) { 
  const dataPayload = payload && Array.isArray(payload) && payload.length > 0 
    ? {
        report: 'Dynamic SAP Data',
        period: 'Current query results',
        rows: payload.map((row: any) => ({
          plant: row.id || row.plant || 'N/A',
          spend: row.product || row.spend || 'N/A',
          variance: row.status || row.variance || 'N/A'
        }))
      }
    : fallbackDataPayload;

  const [copied, setCopied] = useState(false); 
  
  const copy = async () => { 
    await navigator.clipboard?.writeText(JSON.stringify(dataPayload, null, 2)); 
    setCopied(true); 
    window.setTimeout(() => setCopied(false), 1600) 
  }; 
  
  const download = (type: 'json' | 'csv') => { 
    const body = type === 'json' ? JSON.stringify(dataPayload, null, 2) : `Col1,Col2,Col3\n${dataPayload.rows.map((row: any) => `${row.plant},${row.spend},${row.variance}`).join('\n')}`; 
    const url = URL.createObjectURL(new Blob([body], { type: 'text/plain' })); 
    const link = document.createElement('a'); 
    link.href = url; 
    link.download = `sap-export.${type}`; 
    link.click(); 
    URL.revokeObjectURL(url) 
  }; 
  
  return (
    <div className="data-card">
      <div className="data-card-head">
        <div>
          <span className="data-label"><BarChart3 size={13} /> STRUCTURED RESULT</span>
          <strong>{dataPayload.report}</strong>
        </div>
        <span className="row-count">{dataPayload.rows.length} rows</span>
      </div>
      <p className="data-period">{dataPayload.period}</p>
      <div className="mini-table">
        <div className="mini-row mini-head">
          <span>Col 1</span>
          <span>Col 2</span>
          <span>Col 3</span>
        </div>
        {dataPayload.rows.map((row: any, i: number) => (
          <div className="mini-row" key={i}>
            <span>{row.plant}</span>
            <span>{row.spend}</span>
            <span className={String(row.variance).startsWith('+') ? 'positive' : (String(row.variance).startsWith('-') ? 'negative' : '')}>{row.variance}</span>
          </div>
        ))}
      </div>
      <div className="data-actions">
        <button onClick={() => download('csv')}><FileSpreadsheet size={14} /> Download Excel</button>
        <button onClick={() => download('json')}><FileJson size={14} /> Download JSON</button>
        <button onClick={copy}>{copied ? <Check size={14} /> : <Clipboard size={14} />} {copied ? 'Copied' : 'Copy Data'}</button>
      </div>
    </div>
  ) 
}

function Sidebar({ collapsed, onToggle, onLogout, active, onSelect, sessions, setSessions, theme, onTheme }: { collapsed: boolean; onToggle: () => void; onLogout: () => void; active: string; onSelect: (title: string) => void; sessions: Session[]; setSessions: (sessions: Session[]) => void; theme: 'light' | 'dark'; onTheme: () => void }) { 
  const [query, setQuery] = useState(''); 
  const [menu, setMenu] = useState<number | null>(null); 
  const [editing, setEditing] = useState<number | null>(null); 
  const [editValue, setEditValue] = useState(''); 
  const filtered = useMemo(() => sessions.filter((s) => s.title.toLowerCase().includes(query.toLowerCase())), [query, sessions]); 
  
  const rename = (session: Session) => { setEditing(session.id); setEditValue(session.title); setMenu(null) }; 
  const saveRename = (id: number) => { const title = editValue.trim(); if (title) setSessions(sessions.map((s) => s.id === id ? { ...s, title } : s)); setEditing(null) }; 
  const remove = (session: Session) => { setSessions(sessions.filter((s) => s.id !== session.id)); setMenu(null); if (active === session.title) onSelect('New conversation') }; 
  
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
            <button className="theme-toggle" onClick={onTheme} aria-label="Toggle theme">
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
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
                        <input autoFocus value={editValue} onChange={(event) => setEditValue(event.target.value)} onBlur={() => saveRename(session.id)} onKeyDown={(event) => { if (event.key === 'Enter') saveRename(session.id); if (event.key === 'Escape') setEditing(null) }} />
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
  const [collapsed, setCollapsed] = useState(false); 
  const [active, setActive] = useState('Q3 procurement variance'); 
  const [messages, setMessages] = useState<Message[]>(initialMessages); 
  const [input, setInput] = useState(''); 
  const [sessions, setSessions] = useState(initialSessions); 
  const [theme, setTheme] = useState<'light' | 'dark'>('dark'); 
  const [isThinking, setIsThinking] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null); 
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { 
    const saved = window.localStorage.getItem('cira-theme') as 'light' | 'dark' | null; 
    if (saved) setTheme(saved) 
  }, []); 

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

    const streamingId = Date.now();
    setMessages((current) => [...current, { role: 'assistant', content: '', _streamingId: streamingId }]);

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: value, session_id: sessionId })
      });

      if (!res.body) throw new Error('No stream');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value: chunk } = await reader.read();
        if (done) break;
        buffer += decoder.decode(chunk, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

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
                  ? { ...m, data: parsed.data }
                  : m
              ));
            }
          } catch {}
        }
      }
    } catch (err) {
      setMessages((current) => current.map((m: any) =>
        m._streamingId === streamingId
          ? { ...m, content: 'Sorry, I encountered an error connecting to the FastAPI backend.' }
          : m
      ));
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
    if (title === 'Q3 procurement variance') {
      setMessages(initialMessages);
      return;
    }
    const sessionId = `${employeeId}__${title}`;
    try {
      const res = await fetch(`http://localhost:8000/history/${encodeURIComponent(sessionId)}`);
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
  
  if (!loggedIn) return <Login onLogin={(id) => { setEmployeeId(id); setLoggedIn(true); }} theme={theme} onToggle={toggleTheme} />; 
  
  return (
    <main className="app-shell">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} onLogout={() => setLoggedIn(false)} active={active} onSelect={selectChat} sessions={sessions} setSessions={setSessions} theme={theme} onTheme={toggleTheme} />
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
                  {message.data && <DataCard payload={message.data} />}
                </div>
              </div>
            </div>
          ))}
          {isThinking && (
             <div className="message-row assistant">
              <div className="message-avatar"><BrandMark /></div>
              <div className="message-content">
                <span className="message-author">CIRA AI <small>· thinking...</small></span>
                <div className="bubble">...</div>
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
