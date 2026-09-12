'use client'

import React, { useState, useEffect } from 'react'
import { Plus, ShieldAlert, Users, Database, LogOut, Server } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

export default function SuperAdminPage() {
  const [token, setToken] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState<'partners' | 'tenants'>('partners')
  const [partners, setPartners] = useState<any[]>([])
  const [tenants, setTenants] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    password: '',
    slug: '',
    brand_name: '',
    plan: 'pilot',
    max_tenants: 3
  })

  useEffect(() => {
    const stored = localStorage.getItem('cira-superadmin-token')
    if (stored) {
      setToken(stored)
      loadData(stored)
    }
  }, [])

  const loadData = async (authToken: string) => {
    try {
      const [pRes, tRes] = await Promise.all([
        fetch(`${API_BASE}/superadmin/partners`, {
          headers: { Authorization: `Bearer ${authToken}` }
        }),
        fetch(`${API_BASE}/superadmin/tenants`, {
          headers: { Authorization: `Bearer ${authToken}` }
        })
      ])

      if (pRes.status === 401 || pRes.status === 403 || tRes.status === 401 || tRes.status === 403) {
        setToken(null)
        localStorage.removeItem('cira-superadmin-token')
        setError('Session expired. Please sign in again.')
        return
      }

      if (pRes.ok) {
        const pData = await pRes.json()
        setPartners(Array.isArray(pData) ? pData : [])
      }
      if (tRes.ok) {
        const tData = await tRes.json()
        setTenants(Array.isArray(tData) ? tData : [])
      }
    } catch (err) {
      setError('Unable to load platform data. Please check server connectivity.')
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await fetch(`${API_BASE}/superadmin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || 'Invalid superadmin credentials')
      }
      const data = await res.json()
      setToken(data.token)
      localStorage.setItem('cira-superadmin-token', data.token)
      loadData(data.token)
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch(`${API_BASE}/superadmin/partners`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify(formData)
      })
      if (!res.ok) {
        const d = await res.json()
        const msg = typeof d.detail === 'string' ? d.detail : d.detail?.map((x: any) => x.msg).join(', ')
        throw new Error(msg || 'Failed to add partner')
      }
      setShowAdd(false)
      loadData(token!)
      setFormData({
        name: '',
        email: '',
        password: '',
        slug: '',
        brand_name: '',
        plan: 'pilot',
        max_tenants: 3
      })
    } catch (err: any) {
      alert(err.message)
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen bg-slate-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-slate-800 py-8 px-4 shadow-2xl sm:rounded-2xl sm:px-10 border border-slate-700">
            <div className="mb-6 flex justify-center">
              <div className="w-12 h-12 bg-rose-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-rose-900/50">
                <ShieldAlert size={24} />
              </div>
            </div>
            <h2 className="mt-2 mb-6 text-center text-2xl font-bold text-white">Super Admin Console</h2>
            {error && <div className="mb-4 text-sm text-rose-400 text-center bg-rose-950/50 p-2 rounded-lg border border-rose-900">{error}</div>}
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-slate-300">Super Admin Email</label>
                <input required type="text" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 block w-full rounded-xl border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300">Master Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 block w-full rounded-xl border border-slate-600 bg-slate-700/50 px-3 py-2 text-sm text-white focus:border-rose-500 focus:outline-none focus:ring-1 focus:ring-rose-500" />
              </div>
              <button type="submit" className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-xl shadow-sm text-sm font-bold text-white bg-rose-600 hover:bg-rose-700 transition-colors cursor-pointer">ACCESS SYSTEM</button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900 p-8 text-slate-300">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6 bg-slate-800 p-4 rounded-2xl shadow-lg border border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-rose-900/50 text-rose-500 flex items-center justify-center rounded-xl">
              <ShieldAlert size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">Super Admin Control Center</h1>
              <p className="text-xs text-slate-400">Global tenant & reseller partner management</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-rose-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-rose-700 shadow-sm transition-colors cursor-pointer">
              <Plus size={16} /> Provision Partner
            </button>
            <button onClick={() => { setToken(null); localStorage.removeItem('cira-superadmin-token') }} className="flex items-center gap-2 text-slate-400 hover:text-white bg-slate-700 px-3 py-2 rounded-xl text-sm font-semibold cursor-pointer transition-colors">
              <LogOut size={16} /> System Exit
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex gap-3 mb-6">
          <button
            onClick={() => setActiveTab('partners')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-colors cursor-pointer ${
              activeTab === 'partners'
                ? 'bg-rose-600 text-white shadow-md'
                : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
            }`}
          >
            <Users size={16} /> Reseller Partners ({partners.length})
          </button>
          <button
            onClick={() => setActiveTab('tenants')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-colors cursor-pointer ${
              activeTab === 'tenants'
                ? 'bg-rose-600 text-white shadow-md'
                : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
            }`}
          >
            <Database size={16} /> Global Tenants Overview ({tenants.length})
          </button>
        </div>

        {showAdd && (
          <div className="mb-8 bg-slate-800 p-6 rounded-2xl shadow-xl border border-rose-900/50">
            <h3 className="text-lg font-bold mb-4 text-white">Provision New Partner</h3>
            <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Partner Organization Name</label>
                <input required type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" placeholder="e.g. Uneecops Solutions" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Subdomain Slug</label>
                <input required type="text" value={formData.slug} onChange={e => setFormData({...formData, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '')})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" placeholder="e.g. uneecops" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Admin Email (Login ID)</label>
                <input required type="email" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Admin Password</label>
                <input required type="password" value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">White-Label Brand Name (Optional)</label>
                <input type="text" value={formData.brand_name} onChange={e => setFormData({...formData, brand_name: e.target.value})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" placeholder="e.g. Uneecops AI" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Plan</label>
                <select value={formData.plan} onChange={e => setFormData({...formData, plan: e.target.value})} className="w-full rounded-lg border border-slate-600 bg-slate-700 p-2 text-sm text-white">
                  <option value="pilot">Pilot (3 tenants)</option>
                  <option value="read">Read Only</option>
                  <option value="read_write">Read / Write Full</option>
                  <option value="migration">Data Migration</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Max Tenants (Quota)</label>
                <input required type="number" min="1" max="100" value={formData.max_tenants} onChange={e => setFormData({...formData, max_tenants: parseInt(e.target.value, 10) || 1})} className="w-full rounded-lg border border-slate-600 bg-slate-700/50 p-2 text-sm text-white" />
              </div>
              <div className="col-span-1 md:col-span-2 flex justify-end gap-3 mt-4 pt-4 border-t border-slate-700">
                <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700 rounded-lg cursor-pointer transition-colors">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-bold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm cursor-pointer transition-colors">Provision Partner</button>
              </div>
            </form>
          </div>
        )}

        {activeTab === 'partners' ? (
          <div className="bg-slate-800 rounded-2xl shadow-xl border border-slate-700 overflow-hidden">
            <table className="min-w-full divide-y divide-slate-700">
              <thead className="bg-slate-900/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Partner</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Admin Email</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Slug</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Plan</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Cap</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {partners.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-700/50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-bold text-white">{p.name}</div>
                      {p.brand_name && <div className="text-xs text-slate-500">DBA: {p.brand_name}</div>}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300">
                      {p.email}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-slate-400">
                      {p.slug}.cira.app
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-slate-700 text-slate-300 uppercase">
                        {p.plan}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400">
                      {p.max_tenants} max
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {p.is_active ? (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">ACTIVE</span>
                      ) : (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-bold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">SUSPENDED</span>
                      )}
                    </td>
                  </tr>
                ))}
                {partners.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-slate-500 text-sm">
                      No partners provisioned yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="bg-slate-800 rounded-2xl shadow-xl border border-slate-700 overflow-hidden">
            <table className="min-w-full divide-y divide-slate-700">
              <thead className="bg-slate-900/50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Company</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Company DB</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Host & Ports</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Backend</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Writes</th>
                  <th className="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {tenants.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-700/50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-white">
                      {t.company_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-900/50 text-blue-300 border border-blue-700/50">
                        {t.company_db}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300 font-mono">
                      <Server size={14} className="inline mr-1 text-slate-500" />
                      {t.sap_host}:{t.sap_hana_port}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-xs font-semibold text-slate-400 uppercase">
                      {t.backend_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {t.write_enabled ? (
                        <span className="text-emerald-400 font-semibold text-xs">Enabled</span>
                      ) : (
                        <span className="text-slate-500 text-xs">Disabled</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {t.is_active ? (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">ACTIVE</span>
                      ) : (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-bold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">INACTIVE</span>
                      )}
                    </td>
                  </tr>
                ))}
                {tenants.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-slate-500 text-sm">
                      No tenants configured across any partner.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
