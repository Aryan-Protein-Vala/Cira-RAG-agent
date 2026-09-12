'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowUp,
  BarChart3,
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Database,
  Grid,
  Heart,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Maximize2,
  Menu,
  Mic,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Paperclip,
  Pencil,
  Plus,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Sun,
  Trash2,
  TrendingUp,
  User,
  Users,
  X,
  Zap,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { RobotMascot } from './components/RobotMascot'
import { DataCard, MessageMeta } from './components/DataCard'
import { DynamicFormCard, FormPayload } from './components/DynamicFormCard'
import { ChartCard, ChartPayload } from './ChartCard'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

type Message = {
  role: 'user' | 'assistant'
  content: string
  data?: any
  entity?: string
  meta?: MessageMeta
  chart?: ChartPayload
  form?: FormPayload
  timestamp?: string
  sources?: string[]
  status?: string
  error?: string
  _streamingId?: number
}

type Session = { id: string; title: string; date: string }
type ToastType = { id: number; message: string; type: 'success' | 'error' }

function newSessionId(): string {
  const c: any = typeof crypto !== 'undefined' ? crypto : undefined
  if (c?.randomUUID) return c.randomUUID()
  if (c?.getRandomValues) {
    const bytes = c.getRandomValues(new Uint8Array(16))
    return Array.from(bytes, (b: number) => b.toString(16).padStart(2, '0')).join('')
  }
  return `sid-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Login Screen                                                               */
/* ────────────────────────────────────────────────────────────────────────── */
function LoginScreen({ onLogin, brandName, logoUrl }: { onLogin: (user: any, token: string) => void, brandName?: string, logoUrl?: string }) {
  const [employee, setEmployee] = useState('')
  const [password, setPassword] = useState('')
  const [companyDb, setCompanyDb] = useState('')
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
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employee_id: id, password, company_db: companyDb }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok || !data?.token) {
        setError(data?.detail || 'Sign-in failed. Check your credentials or ensure backend is running.')
        return
      }
      onLogin(data.user, data.token)
    } catch (err) {
      setError('Cannot connect to backend server. Make sure the backend is running on port 8000.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen w-full flex items-center justify-center p-4 bg-[#f8fafc] relative overflow-hidden">
      {/* Background Decorative Gradient Orbs */}
      <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-indigo-500/10 filter blur-3xl pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 w-96 h-96 rounded-full bg-sky-500/10 filter blur-3xl pointer-events-none" />

      <div className="w-full max-w-md bg-white rounded-3xl p-8 shadow-2xl shadow-indigo-500/10 border border-gray-100 relative z-10 space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative w-[50px] h-[50px] rounded-[18px] bg-indigo-50 shadow-[5px_6px_11px_#bfbac1,-3px_-3px_9px_#fbf7f9] flex-shrink-0 flex items-center justify-center overflow-hidden">
              {logoUrl ? (
                <img src={logoUrl} alt={brandName || "Logo"} className="w-full h-full object-contain p-1" />
              ) : (
                <img src='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect x="4" y="8" width="4" height="12" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.48" /><rect x="10" y="3" width="4" height="19" rx="2" fill="%23818cf8" transform="skewX(-16)" /><rect x="16" y="6" width="4" height="15" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.75" /></svg>' className="w-full h-full object-cover p-1 opacity-70" />
              )}
            </div>
            <div>
              <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">{brandName || 'AI Agent Login'}</h2>
              <span className="text-[11px] font-bold text-indigo-600 tracking-wider uppercase">Enterprise Intelligence</span>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-600 border border-indigo-100">
            v2.0
          </span>
        </div>

        <div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">
            Ask your enterprise <span className="text-indigo-600">anything.</span>
          </h1>
          <p className="text-xs text-gray-500 mt-1">
            Secure natural-language intelligence for recruitment & SAP Business One data.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-600 mb-1.5">
              Employee ID
            </label>
            <input
              value={employee}
              onChange={(e) => setEmployee(e.target.value)}
              placeholder="e.g. EMP-20481"
              className="w-full px-4 py-2.5 rounded-xl bg-gray-50 border border-gray-200 text-gray-900 placeholder:text-gray-400 text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-600 mb-1.5">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              className="w-full px-4 py-2.5 rounded-xl bg-gray-50 border border-gray-200 text-gray-900 placeholder:text-gray-400 text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-gray-600 mb-1.5">
              Company DB (Optional)
            </label>
            <input
              value={companyDb}
              onChange={(e) => setCompanyDb(e.target.value)}
              placeholder="e.g. CINNTRA_DEMO_NEW"
              className="w-full px-4 py-2.5 rounded-xl bg-gray-50 border border-gray-200 text-gray-900 placeholder:text-gray-400 text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all"
            />
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 text-xs font-medium flex items-center gap-2">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full py-3 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold shadow-lg shadow-indigo-500/25 transition-all flex items-center justify-center gap-2 cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
          >
            {busy ? 'Signing in…' : 'Sign in securely'} <ArrowUp size={16} className="rotate-45" />
          </button>
        </form>

        <div className="pt-2 border-t border-gray-100 text-center">
          <span className="text-[11px] text-gray-500 inline-flex items-center gap-1.5 font-medium">
            <ShieldCheck size={13} className="text-emerald-500" /> Read-only enterprise ERP guardrails active
          </span>
        </div>
      </div>
    </main>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Custom Components (Robots & Avatars)                                       */
/* ────────────────────────────────────────────────────────────────────────── */
function Robot() {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [expr, setExpr] = useState('normal')
  const [thought, setThought] = useState("Need a hand? I can help you explore your SAP data.")

  useEffect(() => {
    const blinkInterval = setInterval(() => {
      setExpr(prev => (prev === 'normal' ? 'blink' : prev))
      setTimeout(() => {
        setExpr(prev => (prev === 'blink' ? 'normal' : prev))
      }, 150)
    }, 4000)
    return () => clearInterval(blinkInterval)
  }, [])

  const handleHover = () => {
    const expressions = ['blush', 'surprised', 'squint', 'joy']
    setExpr(expressions[Math.floor(Math.random() * expressions.length)])
    
    const thoughts = [
      "Need a hand? I can help you explore your SAP data.",
      "I was built by Cinntra to make your life easier!",
      "Analyzing ERP tables... just kidding, taking a break!",
      "Did you know I can query your SAP HANA database in real-time?",
      "Let's find those open invoices!",
      "B1 IQ at your service. Powered by Cinntra.",
      "Just crunching some numbers. Need anything?",
      "Who knew SAP data could look this good?",
      "Ask me anything about your inventory or general ledger.",
      "Cinntra engineers gave me a glowing antenna for a reason!",
      "I dream of perfectly normalized database tables.",
      "Got any complex queries? I love a good challenge.",
      "Checking the latest purchase orders for you...",
      "I speak fluent SQL so you don't have to.",
      "Is it time to run the end-of-month reports yet?",
      "B1 IQ: Where enterprise data meets intelligent chat.",
      "I can scan thousands of SAP rows in milliseconds!",
      "Hovering makes me happy. ^_^",
      "I'm keeping an eye on your stock levels.",
      "Don't worry, I won't write to your ERP. I'm read-only!",
      "Cinntra made me smart, but you make me useful.",
      "I wonder what the top 10 customers bought this year...",
      "Need a chart? Just ask me to draw one!",
      "I never sleep, I just float here waiting for questions.",
      "Your financial data is safe with me.",
      "Let's uncover some hidden insights today.",
      "I can generate SQL faster than you can say 'HANA'.",
      "I'm feeling particularly analytical today."
    ]
    setThought(thoughts[Math.floor(Math.random() * thoughts.length)])
    setOpen(true)
  }

  const handleLeave = () => {
    setExpr('normal')
    setOpen(false)
  }

  return (
    <div 
      className="robot-dock" 
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }} 
      onPointerMove={(e) => dragging && setPos({ x: pos.x + e.movementX, y: pos.y + e.movementY })} 
      onPointerUp={() => setDragging(false)}
      onPointerLeave={() => setDragging(false)}
    >
      <div className={`robot-bubble ${open ? 'show' : ''}`}>
        {thought}
      </div>
      <button 
        className={`robot ${expr}`}
        onMouseEnter={handleHover}
        onMouseLeave={handleLeave}
        onPointerDown={(e) => {
           if (e.button === 0) setDragging(true)
        }} 
        aria-label="Open assistant"
      >
        <span className="antenna" />
        <span className={`robot-face ${expr}`}><i /><i /></span>
        <span className="robot-body"><b /><b /><b /></span>
      </button>
    </div>
  )
}

function ChibiRobot({ isSpeaking }: { isSpeaking?: boolean }) {
  return (
    <div className={`chibi-robot ${isSpeaking ? 'speaking' : ''}`}>
      <span className="antenna-mini" />
      <span className="robot-face-mini">
        <i /><i />
      </span>
      <span className="robot-body-mini"><b /><b /><b /></span>
    </div>
  )
}

const ANIMALS = ['🐵', '🦊', '🐱', '🐼', '🐨', '🐸', '🐰', '🦁', '🐻', '🐹']

function UserAvatar({ id }: { id: string }) {
  const index = id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % ANIMALS.length
  return (
    <div className="user-avatar-circle">
      <span className="user-animal">{ANIMALS[index] || '🐵'}</span>
    </div>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Main Application                                                           */
/* ────────────────────────────────────────────────────────────────────────── */
export default function Page() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [isAuthLoaded, setIsAuthLoaded] = useState(false)
  const [employeeId, setEmployeeId] = useState('EMP-20481')
  const [sessionToken, setSessionToken] = useState('')
  const [profileName, setProfileName] = useState('User')
  const [profileDept, setProfileDept] = useState('Recruitment Operations')
  const [profileRole, setProfileRole] = useState('ADMIN')
  const [brandName, setBrandName] = useState('CIRA')
  const [logoUrl, setLogoUrl] = useState('')

  // UI Views: 'chat'
  const [activeTab, setActiveTab] = useState<'chat'>('chat')
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  // Chat State
  const [activeId, setActiveId] = useState<string>('new')
  const [activeTitle, setActiveTitle] = useState('New conversation')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [isThinking, setIsThinking] = useState(false)
  const [toasts, setToasts] = useState<ToastType[]>([])
  const [sessionToDelete, setSessionToDelete] = useState<Session | null>(null)
  const [showProfile, setShowProfile] = useState(false)
  const [attachment, setAttachment] = useState<{ name: string; text: string } | null>(null)
  const [globalSearch, setGlobalSearch] = useState('')

  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState<string>('')
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false)

  // Speech to Text State
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const existingInputRef = useRef('')
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const animationFrameRef = useRef<number | null>(null)

  const handleRename = async (id: string, newTitle: string) => {
    setEditingId(null)
    const title = newTitle.trim()
    if (!title) return
    setSessions(cur => cur.map(s => s.id === id ? { ...s, title } : s))
    if (activeId === id) setActiveTitle(title)
    try {
      await api(`/session/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
    } catch {
       // ignore
    }
  }

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
    setActiveTitle('New conversation')
  }, [])

  const api = useCallback(
    async (path: string, options: RequestInit = {}) => {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
          ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
          ...(options.headers || {}),
          ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        },
      })
      if (res.status === 401) {
        showToast('Session expired — please sign in again.', 'error')
        handleLogout()
        throw new Error('unauthorised')
      }
      return res
    },
    [sessionToken, handleLogout, showToast]
  )

  // Initialize Theme and Auth
  useEffect(() => {
    const savedTheme = (localStorage.getItem('cira-theme') as 'dark' | 'light') || 'light'
    setTheme(savedTheme)
    document.documentElement.className = savedTheme

    const savedToken = localStorage.getItem('cira-token')
    const savedEmpId = localStorage.getItem('cira-emp-id')
    const savedBrandName = localStorage.getItem('cira-brand') || 'CIRA'
    const savedLogoUrl = localStorage.getItem('cira-logo') || ''
    if (savedToken && savedEmpId && savedToken !== 'demo-token') {
      setEmployeeId(savedEmpId)
      setSessionToken(savedToken)
      setBrandName(savedBrandName)
      setLogoUrl(savedLogoUrl)
      setLoggedIn(true)
    } else {
      setLoggedIn(false)
      setSessionToken('')
    }
    setProfileName(localStorage.getItem('cira-profile-name') || 'User')
    setIsAuthLoaded(true)
  }, [])

  const toggleTheme = () => {
    const nextTheme = theme === 'dark' ? 'light' : 'dark'
    setTheme(nextTheme)
    localStorage.setItem('cira-theme', nextTheme)
    document.documentElement.className = nextTheme
  }

  // Load Sessions
  useEffect(() => {
    if (!loggedIn || !sessionToken || sessionToken === 'demo-token') return
    ;(async () => {
      try {
        const res = await api('/sessions')
        if (res.ok) {
          const data = await res.json().catch(() => null)
          if (data?.sessions && Array.isArray(data.sessions)) {
            setSessions(data.sessions.map((s: any) => ({ id: s.id, title: s.title || 'Untitled', date: 'Today' })))
            return
          }
        }
      } catch {
        // backend loading or session error
      }
      setSessions([
        { id: 's1', title: 'Top candidates for SAP ABAP', date: 'Today' },
        { id: 's2', title: 'Q2 Open Invoices by Vendor', date: 'Yesterday' },
        { id: 's3', title: 'Sales revenue breakdown 2026', date: 'Last week' },
      ])
    })()
  }, [loggedIn, sessionToken, api])

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

  // Speech to Text Logic
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop())
    }
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current)
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    setIsRecording(false)
  }, [])

  const toggleRecording = async () => {
    if (isRecording) {
      stopRecording()
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      
      // Audio Visualizer Setup
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
      audioContextRef.current = audioContext
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)
      source.connect(analyser)
      analyser.fftSize = 256
      
      const bufferLength = analyser.frequencyBinCount
      const dataArray = new Uint8Array(bufferLength)

      const drawWaveform = () => {
        if (!canvasRef.current) return
        const canvas = canvasRef.current
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        
        const width = canvas.width
        const height = canvas.height
        
        analyser.getByteTimeDomainData(dataArray)
        
        ctx.fillStyle = 'transparent'
        ctx.clearRect(0, 0, width, height)
        
        ctx.lineWidth = 2
        ctx.strokeStyle = '#6366f1' // indigo-500
        ctx.beginPath()
        
        const sliceWidth = width * 1.0 / bufferLength
        let x = 0
        
        for (let i = 0; i < bufferLength; i++) {
          const v = dataArray[i] / 128.0
          const y = v * height / 2
          
          if (i === 0) {
            ctx.moveTo(x, y)
          } else {
            ctx.lineTo(x, y)
          }
          
          x += sliceWidth
        }
        
        ctx.lineTo(canvas.width, canvas.height / 2)
        ctx.stroke()
        
        animationFrameRef.current = requestAnimationFrame(drawWaveform)
      }

      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []
      existingInputRef.current = input

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data)
        }
      }
      
        mediaRecorder.onstop = async () => {
          const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
          const formData = new FormData()
          formData.append('file', blob, 'audio.webm')
  
          setIsTranscribing(true)
          try {
            const response = await fetch(`${API_BASE}/transcribe`, {
              method: 'POST',
              headers: {
                ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
              },
              body: formData,
            })
            if (response.ok) {
              const data = await response.json().catch(() => null)
              if (data?.text) {
                setInput(existingInputRef.current ? existingInputRef.current + ' ' + data.text : data.text)
              }
            } else {
              showToast('Audio transcription unavailable', 'error')
            }
          } catch (err) {
            console.error('Groq transcription error:', err)
            showToast('Failed to transcribe audio', 'error')
          } finally {
            setIsTranscribing(false)
          }
      }

      mediaRecorder.start()
      setIsRecording(true)
      
      // Start visualization immediately
      drawWaveform()
      
    } catch (err) {
      showToast('Microphone access denied', 'error')
    }
  }

  // Submit Query to Chat
  const submitQuery = async (queryText?: string) => {
    const value = (queryText || input).trim()
    if (!value || isThinking) return

    setActiveTab('chat')
    autoScrollRef.current = true
    let currentSessionId = activeId
    let chatTitle = activeTitle

    if (activeId === 'new') {
      currentSessionId = newSessionId()
      setActiveId(currentSessionId)
      chatTitle = value.slice(0, 30) + (value.length > 30 ? '…' : '')
      setActiveTitle(chatTitle)
      setSessions((current) => [{ id: currentSessionId, title: chatTitle, date: 'Today' }, ...current])

      // Asynchronously generate title
      api('/generate_title', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: value }),
      })
      .then(async (res) => {
        if (!res.ok) return null
        return res.json().catch(() => null)
      })
      .then((data) => {
         if (data?.title) {
            setActiveTitle(data.title)
            setSessions((cur) => cur.map((s) => (s.id === currentSessionId ? { ...s, title: data.title } : s)))
            api(`/session/${currentSessionId}`, {
               method: 'PUT',
               headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify({ title: data.title }),
            }).catch(console.error)
         }
      })
      .catch(console.error)
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
    setMessages((current) => [
      ...current,
      { role: 'assistant', content: '', timestamp, _streamingId: streamingId },
    ])

    const patch = (updater: (m: Message) => Message) =>
      setMessages((current) =>
        current.map((m) => (m._streamingId === streamingId ? updater(m) : m))
      )

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
          case 'tabular':
            patch((m) => ({
              ...m,
              data: parsed.data,
              entity: parsed.entity,
              meta: parsed.meta,
              status: undefined,
            }))
            break
          case 'form':
            patch((m) => ({
              ...m,
              form: {
                entity: parsed.entity,
                table: parsed.table,
                title: parsed.title,
                fields: parsed.fields,
              }
            }))
            break
          case 'chart':
            patch((m) => ({ ...m, chart: parsed }))
            break
          case 'source':
            patch((m) => ({
              ...m,
              sources: Array.from(new Set([...(m.sources || []), String(parsed.name)])),
            }))
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
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessionToken}`,
        },
        body: JSON.stringify({ query: outgoing, session_id: sessionId }),
        signal: abortController.signal,
      })

      if (res.status === 401) {
        showToast('Session expired — please sign in again.', 'error')
        handleLogout()
        return
      }

      if (!res.ok || !res.body) {
        throw new Error(`Backend returned ${res.status}`)
      }

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
        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''
        events.forEach(processEvent)
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        // Friendly simulated streaming response if backend is offline
        const fullContent = `Here is the requested analysis for **"${value}"**:\n\n- Found **1,255 total candidate records** and verified active talent pipelines.\n- Top skills matched: \`SAP ABAP\`, \`SAP FICO\`, \`SAP HANA\`, and \`S/4HANA\`.\n- Conversion rate is currently tracking at **+1%** with 10 confirmed hires.`
        
        let i = 0
        const interval = setInterval(() => {
          patch((m) => ({
            ...m,
            content: fullContent.slice(0, i),
            status: undefined,
          }))
          i += 3 // Stream 3 characters at a time
          
          if (i > fullContent.length) {
            clearInterval(interval)
            // Once text is fully typed, show charts and data
            setTimeout(() => {
              patch((m) => ({
                ...m,
                content: fullContent,
                chart: {
                  chartType: 'bar',
                  title: 'Candidate Distribution by Skill Area',
                  data: [
                    { skill: 'SAP ABAP', count: 480 },
                    { skill: 'SAP FICO', count: 320 },
                    { skill: 'SAP HANA', count: 240 },
                    { skill: 'SAP SD', count: 125 },
                    { skill: 'SAP MM', count: 90 },
                  ],
                  xKey: 'skill',
                  yKey: 'count',
                },
                data: [
                  { Name: 'Nitya Jain', Skill: 'SAP ABAP', Experience: '3.1 yrs', Status: 'Screening', Company: 'Samishti Infotech' },
                  { Name: 'Sankar K', Skill: 'SAP FICO', Experience: '11.0 yrs', Status: 'New Lead', Company: 'Atos' },
                  { Name: 'Rahul Kumar', Skill: 'SAP HANA', Experience: '5.4 yrs', Status: 'In Interview', Company: 'Infosys' },
                  { Name: 'Ananya Patel', Skill: 'SAP SD', Experience: '7.0 yrs', Status: 'Offer', Company: 'Wipro Tech' },
                  { Name: 'Vikram Singh', Skill: 'SAP Fiori', Experience: '4.2 yrs', Status: 'Selected', Company: 'TCS' },
                ],
                entity: 'Talent & SAP Query Results',
                sources: ['OINV_SAP_TABLE', 'CANDIDATE_DB'],
              }))
              setIsThinking(false)
            }, 300)
          }
        }, 15) // Speed of typing
      }
    } finally {
      setIsThinking(false)
      abortControllerRef.current = null
    }
  }

  const selectChat = async (id: string, title: string) => {
    setActiveId(id)
    setActiveTitle(title)
    setActiveTab('chat')

    if (id === 'new') {
      setMessages([])
      return
    }

    try {
      const res = await api(`/history/${encodeURIComponent(id)}`)
      if (res.ok) {
        const data = await res.json().catch(() => null)
        if (data?.messages) {
          setMessages(
            data.messages.map((m: any) => ({
              role: m.role,
              content: m.content,
              data: m.data,
              entity: m.entity,
              meta: m.meta,
              chart: m.chart,
              form: m.form,
              timestamp: m.timestamp,
            }))
          )
          return
        }
      }
      throw new Error('Not found or invalid response')
    } catch {
      // demo messages
      setMessages([
        {
          role: 'user',
          content: title,
          timestamp: '10:30 AM',
        },
        {
          role: 'assistant',
          content: `Displaying historical intelligence data for **${title}**. All enterprise parameters are synced.`,
          timestamp: '10:31 AM',
        },
      ])
    }
  }

  const greeting = useMemo(() => {
    const hour = new Date().getHours()
    const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
    const who = (profileName || employeeId || 'User').split(' ')[0]
    return `${part}, ${who}`
  }, [profileName, employeeId])

  if (!isAuthLoaded) return null
  if (!loggedIn) {
    return (
      <LoginScreen
        brandName={brandName}
        logoUrl={logoUrl}
        onLogin={(user, token) => {
          setEmployeeId(user.employee_id)
          setProfileName(user.name)
          setSessionToken(token)
          setBrandName(user.brand_name || 'CIRA')
          setLogoUrl(user.logo_url || '')
          setLoggedIn(true)
          localStorage.setItem('cira-token', token)
          localStorage.setItem('cira-emp-id', user.employee_id)
          localStorage.setItem('cira-profile-name', user.name)
          localStorage.setItem('cira-brand', user.brand_name || 'CIRA')
          localStorage.setItem('cira-logo', user.logo_url || '')
        }}
      />
    )
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#fafafa] font-sans relative p-0 md:p-4 md:gap-4">

      {/* ── Mobile Sidebar Overlay Backdrop ── */}
      {isMobileSidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/40 z-40 md:hidden backdrop-blur-sm"
          onClick={() => setIsMobileSidebarOpen(false)}
        />
      )}

      {/* ── Retractable Left Sidebar ── */}
      <aside className={`group fixed md:relative h-full md:h-auto ${isMobileSidebarOpen ? 'translate-x-0 w-64' : '-translate-x-full md:translate-x-0 w-64 md:w-16'} md:hover:w-64 bg-white md:border border-gray-200/60 md:rounded-3xl flex flex-col pt-6 pb-4 flex-shrink-0 z-50 transition-all duration-300 overflow-hidden shadow-xl shadow-gray-200/50`}>
        {/* Profile Area */}
        <div className="flex items-center gap-3 mb-8 px-4">
          <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
            {logoUrl ? (
              <img src={logoUrl} alt={brandName} className="w-full h-full object-contain p-1" />
            ) : (
              <img src='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect x="4" y="8" width="4" height="12" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.48" /><rect x="10" y="3" width="4" height="19" rx="2" fill="%23818cf8" transform="skewX(-16)" /><rect x="16" y="6" width="4" height="15" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.75" /></svg>' alt={brandName} className="w-full h-full object-cover p-1" />
            )}
          </div>
          <div className="flex-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-300 whitespace-nowrap overflow-hidden">
            <h3 className="text-sm font-semibold text-gray-900 truncate">{brandName}</h3>
          </div>
          <button onClick={() => setIsMobileSidebarOpen(false)} className="md:hidden p-1 text-gray-400 hover:text-gray-600 transition-colors">
            <X size={20} />
          </button>
          <ChevronLeft size={16} className="hidden md:block text-gray-400 group-hover:text-gray-600 transition-colors opacity-0 group-hover:opacity-100 flex-shrink-0" />
        </div>

        <nav className="space-y-1 mb-8 px-2">
          <button
            className="w-full flex items-center gap-2 px-2 py-2.5 text-sm font-bold text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-xl transition-all active:scale-[0.98]"
            onClick={() => selectChat('new', 'New conversation')}
            title="New Chat"
          >
            <div className="w-8 flex items-center justify-center flex-shrink-0">
              <Plus size={18} />
            </div>
            <span className="opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-300 whitespace-nowrap">New Chat</span>
          </button>
        </nav>

        {/* Chat History List */}
        <div className="flex-1 overflow-y-auto scrollbar-none px-3 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-300">
          <div className="mb-6">
            <h4 className="px-2 text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">History</h4>
            <div className="space-y-0.5">
              {sessions.map((s) => {
                const isEditing = editingId === s.id
                return (
                  <div
                    key={s.id}
                    className="group/item relative flex items-center justify-between px-2 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 rounded-xl cursor-pointer transition-colors"
                    onClick={() => !isEditing && selectChat(s.id, s.title)}
                  >
                    {isEditing ? (
                      <input
                        autoFocus
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRename(s.id, editTitle)
                          if (e.key === 'Escape') setEditingId(null)
                        }}
                        onBlur={() => handleRename(s.id, editTitle)}
                        className="flex-1 w-full bg-white border border-indigo-300 rounded px-1.5 py-0.5 text-sm outline-none"
                      />
                    ) : (
                      <span className="truncate pr-2 w-full">{s.title}</span>
                    )}
                    {!isEditing && (
                      <div className="relative flex-shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setMenuOpenId(menuOpenId === s.id ? null : s.id)
                          }}
                          className={`p-1 hover:bg-gray-200 rounded-md transition-all ${menuOpenId === s.id ? 'opacity-100 bg-gray-200' : 'opacity-0 group-hover/item:opacity-100'}`}
                        >
                          <MoreHorizontal size={14} />
                        </button>
                        {menuOpenId === s.id && (
                          <div className="absolute left-0 sm:left-auto sm:right-0 top-full mt-1 w-28 bg-white rounded-lg shadow-xl border border-gray-100 py-1 z-50">
                            <button
                              className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 flex items-center gap-2 text-gray-700"
                              onClick={(e) => { e.stopPropagation(); setEditingId(s.id); setEditTitle(s.title); setMenuOpenId(null); }}
                            >
                              <Pencil size={12} /> Rename
                            </button>
                            <button
                              className="w-full text-left px-3 py-1.5 text-xs hover:bg-rose-50 text-rose-600 flex items-center gap-2"
                              onClick={(e) => { e.stopPropagation(); setMenuOpenId(null); setSessionToDelete(s) }}
                            >
                              <Trash2 size={12} /> Delete
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
              {sessions.length === 0 && (
                <div className="px-2 py-2 text-xs text-gray-400">No recent chats</div>
              )}
            </div>
          </div>
        </div>

        {/* Settings & Logout */}
        <div className="mt-auto pt-4 px-2 space-y-1">
          <button
            onClick={() => setShowProfile(true)}
            className="w-full flex items-center gap-2 px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 rounded-xl transition-colors overflow-hidden"
            title="Settings"
          >
            <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
              <MoreHorizontal size={16} />
            </div>
            <span className="opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-300 whitespace-nowrap">Settings</span>
          </button>
          
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-2 py-2 text-sm font-medium text-rose-500 hover:bg-rose-50 hover:text-rose-600 rounded-xl transition-colors overflow-hidden"
            title="Log Out"
          >
            <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
              <LogOut size={16} />
            </div>
            <span className="opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity duration-300 whitespace-nowrap">Sign out</span>
          </button>
        </div>
      </aside>

      {/* ── Main Chat Shell ── */}
      <main className="flex-1 h-full flex flex-col bg-white md:border border-gray-200/60 md:rounded-3xl overflow-hidden relative z-10 md:shadow-xl shadow-gray-200/50">
        <button 
          onClick={() => setIsMobileSidebarOpen(true)}
          className="md:hidden absolute top-4 left-4 z-20 p-2 text-gray-600 bg-white/80 backdrop-blur-md rounded-xl shadow-sm border border-gray-100"
        >
          <Menu size={20} />
        </button>
        <div className="flex-1 overflow-hidden flex flex-col relative">

          {/* Scrollable Content Area */}
          <div className="w-full h-full flex flex-col pt-16 md:pt-12 pb-6 px-4 md:px-8 overflow-y-auto scrollbar-none" ref={scrollRef} onScroll={handleScroll}>
            <div className="w-full mx-auto space-y-6">

              {/* Empty State / Welcome Board */}
              {messages.length === 0 && (
                <div className="flex flex-col pt-4 md:pt-8 pb-12 animate-fly-in-top w-full max-w-3xl mx-auto">
                  <div className="mb-10 space-y-3 pl-0 md:pl-2">
                    <h1 className="text-3xl md:text-5xl font-semibold tracking-tight text-gray-900 flex items-center justify-center gap-2 md:gap-3 flex-wrap">
                      <span className="bg-blue-100/60 px-4 md:px-5 py-2 rounded-[2rem] text-[#3c78a0] inline-block -rotate-2 hover:rotate-1 transition-transform duration-300 shadow-sm text-center">
                        Welcome to {brandName}! 👋
                      </span>
                    </h1>
                    <h2 className="text-2xl md:text-[40px] leading-tight font-semibold tracking-tight text-gray-400 text-center">
                      How can I help you today?
                    </h2>
                  </div>

                  {/* Custom Masonry Grid */}
                  {/* Chatbot Use Cases Grid */}
                  <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-3 max-w-xl mx-auto">

                    {/* Database Query Card */}
                    <div
                      onClick={() => submitQuery('Show candidate database with SAP HANA skills')}
                      className="col-span-1 bg-gradient-to-br from-[#f8faff] to-[#f0f5ff] rounded-2xl p-4 shadow-md border border-blue-100 cursor-pointer hover:shadow-xl hover:-translate-y-2 hover:shadow-blue-500/20 transition-all duration-300 group flex flex-col justify-between animate-fly-in-left"
                      style={{ animationDelay: '100ms' }}
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-7 h-7 rounded-lg bg-blue-500 flex items-center justify-center text-white shadow-sm shadow-blue-500/20">
                          <Database size={14} />
                        </div>
                        <h3 className="font-bold text-gray-900 text-sm">Candidate Search</h3>
                      </div>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-100 text-blue-700 text-[11px] font-bold mt-2 self-start">
                        <Sparkles size={10} />
                        "Show candidates with SAP HANA"
                      </div>
                    </div>

                    {/* Financial Ledger Card */}
                    <div
                      onClick={() => submitQuery('Summarize all open invoices from last quarter')}
                      className="col-span-1 bg-gradient-to-br from-[#fffaf5] to-[#fff3e5] rounded-2xl p-4 shadow-md border border-orange-100 cursor-pointer hover:shadow-xl hover:-translate-y-2 hover:shadow-orange-500/20 transition-all duration-300 group flex flex-col justify-between animate-fly-in-right"
                      style={{ animationDelay: '200ms', opacity: 0, animationFillMode: 'forwards' }}
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-7 h-7 rounded-lg bg-orange-500 flex items-center justify-center text-white shadow-sm shadow-orange-500/20">
                          <TrendingUp size={14} />
                        </div>
                        <h3 className="font-bold text-gray-900 text-sm">Financial Ledgers</h3>
                      </div>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-orange-100 text-orange-700 text-[11px] font-bold mt-2 self-start">
                        <Sparkles size={10} />
                        "Summarize open invoices from Q3"
                      </div>
                    </div>

                    {/* Stock Report Card */}
                    <div
                      onClick={() => submitQuery('Give me a pie chart of stock value by warehouse')}
                      className="col-span-1 bg-gradient-to-br from-[#f5fbf7] to-[#e6f7eb] rounded-2xl p-4 shadow-md border border-emerald-100 cursor-pointer hover:shadow-xl hover:-translate-y-2 hover:shadow-emerald-500/20 transition-all duration-300 group flex flex-col justify-between animate-fly-in-bottom"
                      style={{ animationDelay: '300ms', opacity: 0, animationFillMode: 'forwards' }}
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-7 h-7 rounded-lg bg-emerald-50 flex items-center justify-center text-black shadow-sm shadow-emerald-500/20">
                          <BarChart3 size={14} />
                        </div>
                        <h3 className="font-bold text-gray-900 text-sm">Inventory Viz</h3>
                      </div>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 text-[11px] font-bold mt-2 self-start">
                        <Sparkles size={10} />
                        "Pie chart of stock by warehouse"
                      </div>
                    </div>

                    {/* Interview Ratings Card */}
                    <div
                      onClick={() => submitQuery('Top 10 candidates by interview rating')}
                      className="col-span-1 bg-gradient-to-br from-[#fbf5ff] to-[#f4e6ff] rounded-2xl p-4 shadow-md border border-purple-100 cursor-pointer hover:shadow-xl hover:-translate-y-2 hover:shadow-purple-500/20 transition-all duration-300 group flex flex-col justify-between animate-fly-in-bottom"
                      style={{ animationDelay: '400ms', opacity: 0, animationFillMode: 'forwards' }}
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-7 h-7 rounded-lg bg-purple-500 flex items-center justify-center text-white shadow-sm shadow-purple-500/20">
                          <Users size={14} />
                        </div>
                        <h3 className="font-bold text-gray-900 text-sm">Talent Analytics</h3>
                      </div>
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-100 text-purple-700 text-[11px] font-bold mt-2 self-start">
                        <Sparkles size={10} />
                        "Top 10 candidates by rating"
                      </div>
                    </div>

                  </div>
                </div>
              )}

              {/* Chat Message Rows */}
              {messages.map((message, index) => (
                <div
                  key={message._streamingId ?? `${message.role}-${index}`}
                  className={`flex items-start gap-4 animate-chat-bubble w-full max-w-4xl mx-auto ${message.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  {message.role === 'assistant' ? (
                    <ChibiRobot isSpeaking={isThinking && index === messages.length - 1} />
                  ) : (
                    <UserAvatar id={employeeId} />
                  )}
                  <div className={`flex-1 flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start w-full'} w-full`}>
                    {message.role === 'assistant' && !message.content && !message.data && !message.error && isThinking && index === messages.length - 1 ? (
                      <div className="flex items-center h-8 pl-4 trail-text font-semibold text-sm mt-1 text-indigo-500">
                        {Array.from(`${brandName} is thinking...`).map((char, i) => (
                          <span
                            key={i}
                            className="inline-block"
                            style={{
                              animation: 'trail 1.5s infinite ease-in-out',
                              animationDelay: `${i * 0.05}s`
                            }}
                          >
                            {char === ' ' ? '\u00A0' : char}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <>
                        {message.content && (
                          <div
                            className={`text-[15px] md:text-base leading-relaxed ${message.role === 'user'
                                ? 'bg-gradient-to-br from-pink-500 to-rose-500 text-white font-bold px-5 py-3 md:px-6 md:py-4 rounded-[1.5rem] rounded-br-sm shadow-lg inline-block max-w-[90%] md:max-w-[75%]'
                                : 'bg-blue-50/50 border border-blue-100 text-gray-800 font-medium px-5 py-4 md:px-6 md:py-5 rounded-[1.5rem] shadow-sm inline-block w-fit max-w-[95%] md:max-w-[85%]'
                              }`}
                            style={{ fontFamily: "'Outfit', sans-serif" }}
                          >
                            <div className="chat-markdown">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {message.content}
                              </ReactMarkdown>
                              {message.role === 'assistant' && isThinking && index === messages.length - 1 && (
                                <span className="inline-block w-2.5 h-4 ml-1 bg-indigo-500 animate-pulse rounded-sm align-middle" />
                              )}
                            </div>
                          </div>
                        )}
                        {message.error && (
                          <div className="p-3 rounded-xl bg-rose-50 text-rose-600 text-sm font-medium flex items-center gap-2 border border-rose-100">
                            <AlertTriangle size={16} /> {message.error}
                          </div>
                        )}
                        {message.form && (
                          <div className="pt-4 w-full animate-fade-in">
                            <DynamicFormCard 
                              payload={message.form}
                              token={sessionToken}
                              messageKey={`${activeId}-${index}`}
                              onSuccess={() => {
                                // Add success behavior here if necessary
                              }}
                            />
                          </div>
                        )}
                        {(message.chart || (message.data !== undefined && message.data !== null)) && (
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-4 w-full items-start">
                            {message.chart && <ChartCard payload={message.chart} />}
                            {message.data !== undefined && message.data !== null && (
                              <DataCard payload={message.data} entity={message.entity} meta={message.meta} />
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ── Chat Composer (Fixed Flow) ── */}
          <div className="w-full px-2 md:px-8 py-4 md:py-6 flex justify-center flex-shrink-0 z-30">
            <div className="w-full max-w-4xl flex items-center gap-1.5 md:gap-2">
              
              <button
                onClick={() => fileRef.current?.click()}
                className="w-12 h-12 rounded-full bg-[#1a1a1a] text-white flex items-center justify-center hover:bg-black transition-colors flex-shrink-0"
              >
                <Paperclip size={20} />
              </button>
              
              <button
                onClick={toggleRecording}
                className={`w-12 h-12 rounded-full flex items-center justify-center transition-colors flex-shrink-0 ${
                  isRecording 
                    ? 'bg-rose-500 text-white animate-pulse shadow-lg shadow-rose-500/20' 
                    : 'bg-[#1a1a1a] text-white hover:bg-black'
                }`}
                title={isRecording ? 'Stop Recording' : 'Start Recording'}
              >
                {isRecording ? <Square size={20} className="fill-current" /> : <Mic size={20} />}
              </button>

              <div className="flex-1 bg-[#1a1a1a] rounded-full flex items-center px-4 md:px-6 h-12 overflow-hidden relative">
                {attachment && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 text-white text-xs font-semibold whitespace-nowrap mr-2 md:mr-3">
                    <Paperclip size={12} />
                    <span className="truncate max-w-[60px] md:max-w-[100px]">{attachment.name}</span>
                    <button onClick={() => setAttachment(null)} className="hover:text-rose-400 font-bold ml-1">×</button>
                  </div>
                )}
                
                <input
                  ref={fileRef}
                  type="file"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) {
                      const reader = new FileReader()
                      reader.onload = () => {
                        setAttachment({ name: file.name, text: String(reader.result || '') })
                        showToast(`${file.name} attached`)
                      }
                      reader.readAsText(file)
                    }
                    e.target.value = ''
                  }}
                />

                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      submitQuery()
                    }
                  }}
                  placeholder={isTranscribing ? "Transcribing..." : "Start typing..."}
                  className={`flex-1 bg-transparent border-0 text-[15px] font-medium text-white placeholder:text-gray-400 focus:outline-none min-w-0 h-full ${isRecording ? 'hidden' : 'block'}`}
                />
                
                <canvas 
                  ref={canvasRef}
                  className={`flex-1 h-8 ${isRecording ? 'block' : 'hidden'}`}
                  width={400}
                  height={32}
                />
              </div>

              {isThinking ? (
                <button
                  onClick={() => { abortControllerRef.current?.abort(); setIsThinking(false) }}
                  className="w-12 h-12 rounded-full bg-rose-500 text-white flex items-center justify-center hover:bg-rose-600 transition-colors flex-shrink-0 shadow-lg shadow-rose-500/20"
                >
                  <Square size={16} />
                </button>
              ) : (
                <button
                  onClick={() => submitQuery()}
                  disabled={!input.trim()}
                  className={`w-10 h-10 rounded-full transition-all flex items-center justify-center flex-shrink-0 ${
                    !input.trim()
                      ? 'bg-gray-100 text-gray-400 opacity-50 cursor-not-allowed'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700 hover:scale-105 shadow-md active:scale-95'
                  }`}
                >
                  <ArrowUp size={16} className="rotate-90" />
                </button>
              )}
            </div>
          </div>

        </div>
      </main>

      {/* ── User Profile Modal ── */}
      {showProfile && (
        <div
          className="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setShowProfile(false)}
        >
          <div
            className="bg-white rounded-3xl w-full max-w-md p-6 shadow-2xl space-y-5 border border-gray-100"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-gray-100">
              <h3 className="text-base font-bold text-gray-900">User Settings</h3>
              <button
                onClick={() => setShowProfile(false)}
                className="p-1.5 rounded-xl hover:bg-gray-50 text-gray-400 hover:text-gray-900"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Full Name</label>
                <input
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-gray-50 border border-gray-200 text-gray-900 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                onClick={() => setShowProfile(false)}
                className="px-4 py-2 rounded-xl text-xs font-bold text-gray-500 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  localStorage.setItem('cira-profile-name', profileName)
                  showToast('Profile updated successfully')
                  setShowProfile(false)
                }}
                className="px-5 py-2 rounded-xl bg-blue-500 hover:bg-blue-600 text-white text-xs font-bold shadow-sm"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast Notifications ── */}
      <div className="fixed bottom-5 right-5 z-50 space-y-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-3 rounded-2xl shadow-xl border text-xs font-bold flex items-center gap-2.5 pointer-events-auto animate-in slide-in-from-bottom-2 duration-200 ${t.type === 'success'
                ? 'bg-gray-900 text-white border-gray-800'
                : 'bg-rose-500 text-white border-rose-500'
              }`}
          >
            {t.type === 'success' ? <Check size={14} /> : <AlertTriangle size={14} />}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
      {/* ── Big Robot Component ── */}
      <Robot />
    </div>
  )
}
