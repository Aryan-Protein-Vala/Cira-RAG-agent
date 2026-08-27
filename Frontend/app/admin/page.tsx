'use client'

/**
 * Admin panel — company DB (tenant) registry.
 *
 * Differences from the first cut of this page:
 *  * it no longer posts to a hard-coded `/admin/login` backdoor (that endpoint
 *    compared the password against a literal in source and minted the admin role
 *    for anyone who had read the repo). Admins sign in with the normal
 *    /auth/login and the API enforces the `admin` role on every /admin route.
 *  * passwords are write-only: the list shows *how* a secret is stored
 *    (env reference / encrypted / plaintext), never the value.
 *  * every row can be tested against the real HANA/Service Layer before and
 *    after saving, and enabled/disabled without deleting it.
 */

import React, { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { Building2, Check, Eye, Loader2, Plug, Plus, ShieldAlert, Trash2, X } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

type Connection = {
  id: number
  company_db: string
  display_name: string
  enabled: boolean
  hana_address: string
  hana_port: number
  hana_user: string
  service_layer_port: number
  sl_user: string
  hana_secret_source: string
  sl_secret_source: string
  updated_at?: string | null
}

type TestResult = {
  ok?: boolean
  tables_visible?: number
  checks?: { target: string; ok: boolean; detail: string }[]
}

const EMPTY_FORM = {
  company_db: '',
  display_name: '',
  hana_address: '',
  hana_port: 30013,
  hana_user: '',
  hana_password: '',
  service_layer_port: 50000,
  sl_user: '',
  sl_password: '',
  notes: '',
}

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null)
  const [who, setWho] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rows, setRows] = useState<Connection[]>([])
  const [envTenants, setEnvTenants] = useState<string[]>([])
  const [storage, setStorage] = useState<{ encrypted_available: boolean; plaintext_allowed: boolean }>({
    encrypted_available: true,
    plaintext_allowed: false,
  })
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [testing, setTesting] = useState<number | 'new' | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  const api = useCallback(
    async (path: string, init: RequestInit = {}) => {
      const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(init.headers || {}),
        },
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`)
      return body
    },
    [token],
  )

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? window.localStorage.getItem('cira-token') : null
    if (saved) setToken(saved)
  }, [])

  const load = useCallback(async () => {
    try {
      const data = await api('/admin/connections')
      setRows(data.connections || [])
      setEnvTenants(data.from_environment || [])
      setStorage(data.secret_storage || storage)
    } catch (err: any) {
      if (/401|403/.test(String(err?.message))) {
        window.localStorage.removeItem('cira-token')
        setToken(null)
      }
      setError(err?.message || 'Could not load the registry')
    }
  }, [api, storage])

  useEffect(() => {
    if (token) {
      api('/auth/me')
        .then((me) => setWho(me.name || me.employee_id))
        .catch(() => setWho(''))
      load()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const signIn = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employee_id: username, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || 'Sign-in failed')
      const roles: string[] = data?.user?.roles || []
      if (!roles.includes('admin')) throw new Error('This account is not an administrator.')
      window.localStorage.setItem('cira-token', data.token)
      window.localStorage.setItem('cira-emp-id', data.user.employee_id)
      setToken(data.token)
      setWho(data.user.name || data.user.employee_id)
      setPassword('')
    } catch (err: any) {
      setError(err?.message || 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  const signOut = () => {
    window.localStorage.removeItem('cira-token')
    setToken(null)
    setRows([])
    setError('')
  }

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    setTestResult(null)
    try {
      await api('/admin/connections', { method: 'POST', body: JSON.stringify({ ...form, test_first: false }) })
      setNotice(`${form.company_db.toUpperCase()} registered. Its credentials are stored, never displayed.`)
      setForm({ ...EMPTY_FORM })
      await load()
    } catch (err: any) {
      setError(err?.message || 'Could not save the connection')
    } finally {
      setBusy(false)
    }
  }

  const testNew = async () => {
    setTesting('new')
    setError('')
    setTestResult(null)
    try {
      const result = await api('/admin/connections/test', {
        method: 'POST',
        body: JSON.stringify({
          company_db: form.company_db,
          hana_address: form.hana_address,
          hana_port: Number(form.hana_port),
          hana_user: form.hana_user,
          hana_password: form.hana_password,
          service_layer_port: Number(form.service_layer_port),
          sl_user: form.sl_user,
          sl_password: form.sl_password,
        }),
      })
      setTestResult(result)
    } catch (err: any) {
      setError(err?.message || 'Test failed')
    } finally {
      setTesting(null)
    }
  }

  const testSaved = async (row: Connection) => {
    setTesting(row.id)
    setError('')
    try {
      setTestResult(await api(`/admin/connections/${row.id}/test`, { method: 'POST' }))
    } catch (err: any) {
      setError(err?.message || 'Test failed')
    } finally {
      setTesting(null)
    }
  }

  const toggle = async (row: Connection) => {
    try {
      await api(`/admin/connections/${row.id}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: !row.enabled }),
      })
      await load()
    } catch (err: any) {
      setError(err?.message || 'Could not update')
    }
  }

  const remove = async (row: Connection) => {
    if (!window.confirm(`Remove ${row.company_db} from this server? Employees will no longer be able to sign in to it.`)) return
    try {
      await api(`/admin/connections/${row.id}`, { method: 'DELETE' })
      await load()
    } catch (err: any) {
      setError(err?.message || 'Could not delete')
    }
  }

  const field = (label: string, key: keyof typeof EMPTY_FORM, opts: { type?: string; hint?: string; required?: boolean } = {}) => (
    <label className="block">
      <span className="text-[11px] font-bold uppercase tracking-wide text-gray-500">
        {label}
        {opts.required ? ' *' : ''}
      </span>
      <input
        className="mt-1 w-full rounded-lg border border-gray-300 px-2.5 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        type={opts.type || 'text'}
        value={(form as any)[key]}
        required={!!opts.required}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
      {opts.hint ? <span className="mt-0.5 block text-[11px] text-gray-400">{opts.hint}</span> : null}
    </label>
  )

  if (!token) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <form onSubmit={signIn} className="w-full max-w-sm bg-white rounded-2xl shadow-xl p-7 space-y-4">
          <div className="flex items-center gap-2 text-indigo-600">
            <ShieldAlert size={20} />
            <h1 className="text-lg font-extrabold text-gray-900">CIRA administration</h1>
          </div>
          <p className="text-xs text-gray-500 -mt-2">
            Company DB registry. Sign in with the bootstrap admin account (CIRA_ADMIN_ID /
            CIRA_ADMIN_PASSWORD) or your IdP identity carrying the admin role.
          </p>
          <input
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Employee ID / admin ID"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <input
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
          <button
            disabled={busy}
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Sign in'}
          </button>
          <Link href="/" className="block text-center text-xs text-gray-400 hover:text-indigo-600">
            Back to CIRA
          </Link>
        </form>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-extrabold text-gray-900">
              <Building2 size={20} className="text-indigo-600" /> Company databases
            </h1>
            <p className="text-xs text-gray-500">
              Signed in as {who || 'admin'} · credentials are write-only here ·{' '}
              {storage.encrypted_available ? 'encryption at rest available' : 'install `cryptography` to encrypt at rest'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/" className="rounded-lg bg-gray-100 px-3 py-2 text-xs font-bold text-gray-600 hover:bg-gray-200">
              Open CIRA
            </Link>
            <button onClick={signOut} className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-100">
              Sign out
            </button>
          </div>
        </header>

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
            <X size={15} className="mt-0.5" /> {error}
          </div>
        )}
        {notice && (
          <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
            <Check size={15} className="mt-0.5" /> {notice}
          </div>
        )}

        <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-bold text-gray-900">Registered company DBs</h2>
          {rows.length === 0 && (
            <p className="mt-1 text-xs text-gray-500">
              None yet. Employees can currently sign in to the environment-registered DBs:
              {envTenants.length ? ` ${envTenants.join(', ')}.` : ' the deployment default.'}
            </p>
          )}
          {rows.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wide text-gray-400">
                  <tr>
                    <th className="py-2 pr-3">Company DB</th>
                    <th className="py-2 pr-3">HANA target</th>
                    <th className="py-2 pr-3">User</th>
                    <th className="py-2 pr-3">Secret</th>
                    <th className="py-2 pr-3">Service Layer</th>
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.map((row) => (
                    <tr key={row.id} className={row.enabled ? '' : 'opacity-50'}>
                      <td className="py-2 pr-3 font-bold text-gray-900">{row.company_db}</td>
                      <td className="py-2 pr-3 font-mono">{row.hana_address}:{row.hana_port}</td>
                      <td className="py-2 pr-3">{row.hana_user}</td>
                      <td className="py-2 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            row.hana_secret_source === 'env'
                              ? 'bg-emerald-100 text-emerald-700'
                              : row.hana_secret_source === 'encrypted'
                                ? 'bg-indigo-100 text-indigo-700'
                                : 'bg-amber-100 text-amber-700'
                          }`}
                        >
                          {row.hana_secret_source}
                        </span>
                      </td>
                      <td className="py-2 pr-3 font-mono">{row.sl_user ? `:${row.service_layer_port} as ${row.sl_user}` : '—'}</td>
                      <td className="py-2 pr-3">{row.enabled ? 'enabled' : 'paused'}</td>
                      <td className="py-2 whitespace-nowrap text-right">
                        <button
                          onClick={() => testSaved(row)}
                          className="mr-1 inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2 py-1 font-bold text-gray-600 hover:bg-gray-200"
                        >
                          {testing === row.id ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />} Test
                        </button>
                        <button
                          onClick={() => toggle(row)}
                          className="mr-1 inline-flex items-center gap-1 rounded-lg bg-gray-100 px-2 py-1 font-bold text-gray-600 hover:bg-gray-200"
                        >
                          {row.enabled ? 'Pause' : 'Enable'}
                        </button>
                        <button
                          onClick={() => remove(row)}
                          className="inline-flex items-center gap-1 rounded-lg bg-rose-50 px-2 py-1 font-bold text-rose-600 hover:bg-rose-100"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {testResult?.checks && (
            <div className="mt-3 rounded-xl border border-gray-200 bg-gray-50 p-3">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-gray-500">
                <Eye size={13} /> Last test
              </p>
              <ul className="space-y-0.5 text-xs">
                {testResult.checks.map((check, i) => (
                  <li key={i} className={check.ok ? 'text-emerald-700' : 'text-rose-600'}>
                    {check.ok ? '✓' : '✗'} {check.target}: {check.detail}
                  </li>
                ))}
                {typeof testResult.tables_visible === 'number' ? (
                  <li className="text-gray-600">tables visible: {testResult.tables_visible}</li>
                ) : null}
              </ul>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-bold text-gray-900">Add a company DB</h2>
          <p className="mt-1 text-[11px] text-gray-500">
            Paste the password as-is: it is encrypted at rest with CIRA_SECRET_KEY. To keep nothing on
            disk, type <code className="rounded bg-gray-100 px-1">env:VAR_NAME</code> instead and set that
            variable in Backend/.env on the server.
          </p>
          <form onSubmit={create} className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            {field('Company DB / schema', 'company_db', { required: true, hint: 'e.g. ACME_PROD (identifier-shaped)' })}
            {field('Display name', 'display_name')}
            {field('HANA host', 'hana_address', { required: true, hint: 'hostname or IP reachable from this server' })}
            {field('HANA SQL port', 'hana_port', { type: 'number', hint: '3<instance>13 system · 3<instance>15 tenant' })}
            {field('HANA read-only user', 'hana_user', { required: true })}
            {field('HANA password', 'hana_password', { type: 'password', required: true })}
            {field('Service Layer port', 'service_layer_port', { type: 'number', hint: 'needed only for data entry / writes' })}
            {field('Service Layer user', 'sl_user', { hint: 'a B1 user (e.g. manager) — not the HANA user' })}
            {field('Service Layer password', 'sl_password', { type: 'password' })}
            {field('Notes', 'notes')}
            <div className="md:col-span-2 flex flex-wrap items-center gap-2">
              <button
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Save connection
              </button>
              <button
                type="button"
                onClick={testNew}
                disabled={busy || testing === 'new'}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gray-100 px-3 py-2 text-xs font-bold text-gray-700 hover:bg-gray-200"
              >
                {testing === 'new' ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />} Test before saving
              </button>
            </div>
          </form>
        </section>
      </div>
    </main>
  )
}
