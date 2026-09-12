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
      <div className="min-h-screen bg-[#FDFCF8] flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-4 shadow-sm sm:rounded-2xl sm:px-10 border border-[#E8E6DB]">
            <div className="mb-6 flex justify-center">
              <div className="w-12 h-12 bg-[#1E1E1E] rounded-xl flex items-center justify-center text-white border border-[#E8E6DB]">
                <ShieldAlert size={24} />
              </div>
            </div>
            <h2 className="mt-2 mb-6 text-center text-2xl font-medium text-[#1E1E1E]">B1 Copilot Core</h2>
            {error && <div className="mb-4 text-sm text-red-600 text-center bg-red-50 p-2 rounded-lg border border-red-100">{error}</div>}
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-[#5D5D5D]">Super Admin Email</label>
                <input required type="text" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 block w-full rounded-xl border border-[#E8E6DB] bg-[#FDFCF8] px-3 py-2 text-sm text-[#1E1E1E] focus:border-[#1E1E1E] focus:outline-none transition-colors" />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#5D5D5D]">Master Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 block w-full rounded-xl border border-[#E8E6DB] bg-[#FDFCF8] px-3 py-2 text-sm text-[#1E1E1E] focus:border-[#1E1E1E] focus:outline-none transition-colors" />
              </div>
              <button type="submit" className="w-full flex justify-center py-2.5 px-4 rounded-xl text-sm font-medium text-white bg-[#1E1E1E] hover:bg-black transition-colors cursor-pointer">ACCESS SYSTEM</button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#FDFCF8] p-8 font-sans text-[#1E1E1E] selection:bg-[#E8E6DB]">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8 bg-white p-4 rounded-2xl shadow-sm border border-[#E8E6DB]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#1E1E1E] text-white flex items-center justify-center rounded-xl border border-[#E8E6DB]">
              <ShieldAlert size={20} />
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#1E1E1E]">B1 Copilot Master Console</h1>
              <p className="text-xs text-[#5D5D5D]">Global tenant & reseller partner management</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-[#1E1E1E] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-black shadow-sm transition-colors cursor-pointer">
              <Plus size={16} /> Provision Partner
            </button>
            <button onClick={() => { setToken(null); localStorage.removeItem('cira-superadmin-token') }} className="flex items-center gap-2 text-[#5D5D5D] hover:text-[#1E1E1E] bg-[#F3F2EA] px-3 py-2 rounded-xl text-sm font-medium cursor-pointer border border-[#E8E6DB] transition-colors">
              <LogOut size={16} /> System Exit
            </button>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="flex gap-3 mb-6">
          <button
            onClick={() => setActiveTab('partners')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors cursor-pointer ${
              activeTab === 'partners'
                ? 'bg-[#1E1E1E] text-white border border-[#1E1E1E]'
                : 'bg-white text-[#5D5D5D] hover:text-[#1E1E1E] border border-[#E8E6DB]'
            }`}
          >
            <Users size={16} /> Reseller Partners ({partners.length})
          </button>
          <button
            onClick={() => setActiveTab('tenants')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors cursor-pointer ${
              activeTab === 'tenants'
                ? 'bg-[#1E1E1E] text-white border border-[#1E1E1E]'
                : 'bg-white text-[#5D5D5D] hover:text-[#1E1E1E] border border-[#E8E6DB]'
            }`}
          >
            <Database size={16} /> Global Tenants Overview ({tenants.length})
          </button>
        </div>

        {showAdd && (
          <div className="mb-8 bg-white p-6 rounded-2xl shadow-sm border border-[#E8E6DB]">
            <h3 className="text-lg font-medium mb-4 text-[#1E1E1E]">Provision New Partner</h3>
            <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Partner Organization Name</label>
                <input required type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. Uneecops Solutions" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Subdomain Slug</label>
                <input required type="text" value={formData.slug} onChange={e => setFormData({...formData, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '')})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. uneecops" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Admin Email (Login ID)</label>
                <input required type="email" value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Admin Password</label>
                <input required type="password" value={formData.password} onChange={e => setFormData({...formData, password: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">White-Label Brand Name (Optional)</label>
                <input type="text" value={formData.brand_name} onChange={e => setFormData({...formData, brand_name: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. Uneecops AI" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Plan</label>
                <select value={formData.plan} onChange={e => setFormData({...formData, plan: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-white p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors">
                  <option value="pilot">Pilot (3 tenants)</option>
                  <option value="read">Read Only</option>
                  <option value="read_write">Read / Write Full</option>
                  <option value="migration">Data Migration</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Max Tenants (Quota)</label>
                <input required type="number" min="1" max="100" value={formData.max_tenants} onChange={e => setFormData({...formData, max_tenants: parseInt(e.target.value, 10) || 1})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div className="col-span-1 md:col-span-2 flex justify-end gap-3 mt-4 pt-4 border-t border-[#E8E6DB]">
                <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm font-medium text-[#5D5D5D] hover:bg-[#F3F2EA] rounded-lg cursor-pointer transition-colors border border-transparent">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-[#1E1E1E] hover:bg-black rounded-lg shadow-sm cursor-pointer transition-colors">Provision Partner</button>
              </div>
            </form>
          </div>
        )}

        {activeTab === 'partners' ? (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E8E6DB] overflow-hidden">
            <table className="min-w-full divide-y divide-[#E8E6DB]">
              <thead className="bg-[#F3F2EA]">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Partner</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Admin Email</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Slug</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Plan</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Cap</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-[#E8E6DB]">
                {partners.map((p) => (
                  <tr key={p.id} className="hover:bg-[#FDFCF8] transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-[#1E1E1E]">{p.name}</div>
                      {p.brand_name && <div className="text-xs text-[#5D5D5D]">DBA: {p.brand_name}</div>}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-[#1E1E1E]">
                      {p.email}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-[#5D5D5D]">
                      {p.slug}.copilot.b1
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded text-[#1E1E1E] bg-[#F3F2EA] border border-[#E8E6DB] uppercase">
                        {p.plan}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-[#5D5D5D]">
                      {p.max_tenants} max
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {p.is_active ? (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-green-50 text-green-700 border border-green-200">ACTIVE</span>
                      ) : (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-red-50 text-red-700 border border-red-200">SUSPENDED</span>
                      )}
                    </td>
                  </tr>
                ))}
                {partners.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-[#5D5D5D] text-sm">
                      No partners provisioned yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="bg-white rounded-2xl shadow-sm border border-[#E8E6DB] overflow-hidden">
            <table className="min-w-full divide-y divide-[#E8E6DB]">
              <thead className="bg-[#F3F2EA]">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Company</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Company DB</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Host & Ports</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Backend</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Writes</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-[#E8E6DB]">
                {tenants.map((t) => (
                  <tr key={t.id} className="hover:bg-[#FDFCF8] transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-[#1E1E1E]">
                      {t.company_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded text-[#1E1E1E] bg-[#F3F2EA] border border-[#E8E6DB]">
                        {t.company_db}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-[#1E1E1E] font-mono">
                      <Server size={14} className="inline mr-1 text-[#5D5D5D]" />
                      {t.sap_host}:{t.sap_hana_port}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-xs font-medium text-[#5D5D5D] uppercase">
                      {t.backend_type}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {t.write_enabled ? (
                        <span className="text-green-600 font-medium text-xs">Enabled</span>
                      ) : (
                        <span className="text-[#5D5D5D] text-xs">Disabled</span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {t.is_active ? (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-green-50 text-green-700 border border-green-200">ACTIVE</span>
                      ) : (
                        <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-red-50 text-red-700 border border-red-200">INACTIVE</span>
                      )}
                    </td>
                  </tr>
                ))}
                {tenants.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-[#5D5D5D] text-sm">
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
