'use client'

import React, { useState, useEffect } from 'react'
import { Database, Plus, Trash2, Server, Lock, LogOut, Activity, CheckCircle2, XCircle } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [tenants, setTenants] = useState<any[]>([])
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<any | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [formData, setFormData] = useState({
    company_name: '',
    company_db: '',
    sap_host: '',
    sap_hana_port: 30013,
    sap_sl_port: 50000,
    sap_db_user: '',
    sap_db_password: '',
    sap_sl_user: 'manager',
    sap_sl_password: '',
    backend_type: 'hana',
    currency: 'INR'
  })

  useEffect(() => {
    const stored = localStorage.getItem('cira-partner-admin-token')
    if (stored) {
      setToken(stored)
      loadTenants(stored)
    }
  }, [])

  const loadTenants = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/admin/tenants`, {
        headers: { Authorization: `Bearer ${authToken}` }
      })
      if (res.status === 401 || res.status === 403) {
        setError('Session expired. Please sign in again.')
        setToken(null)
        localStorage.removeItem('cira-partner-admin-token')
        return
      }
      if (!res.ok) throw new Error('Failed to load tenants')
      const data = await res.json()
      setTenants(Array.isArray(data) ? data : [])
    } catch (err) {
      setError('Unable to load tenants. Please check backend connection.')
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const res = await fetch(`${API_BASE}/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || 'Invalid partner credentials')
      }
      const data = await res.json()
      setToken(data.token)
      localStorage.setItem('cira-partner-admin-token', data.token)
      loadTenants(data.token)
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch(`${API_BASE}/admin/tenants`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify(formData)
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        const msg = typeof d.detail === 'string' ? d.detail : d.detail?.map((x: any) => x.msg).join(', ')
        throw new Error(msg || 'Failed to add tenant')
      }
      setShowAdd(false)
      loadTenants(token!)
      setFormData({
        company_name: '',
        company_db: '',
        sap_host: '',
        sap_hana_port: 30013,
        sap_sl_port: 50000,
        sap_db_user: '',
        sap_db_password: '',
        sap_sl_user: 'manager',
        sap_sl_password: '',
        backend_type: 'hana',
        currency: 'INR'
      })
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this tenant?')) return
    try {
      const res = await fetch(`${API_BASE}/admin/tenants/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to delete tenant')
      loadTenants(token!)
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleTestConnection = async (id: string) => {
    setTestingId(id)
    setTestResult(null)
    try {
      const res = await fetch(`${API_BASE}/admin/tenants/${id}/test`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setTestResult({ id, success: false, error: data.detail || 'Connection test failed' })
      } else {
        setTestResult({ id, ...data })
      }
    } catch (err: any) {
      setTestResult({ id, success: false, error: err.message })
    } finally {
      setTestingId(null)
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen bg-[#FDFCF8] flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-4 shadow-sm sm:rounded-2xl sm:px-10 border border-[#E8E6DB]">
            <div className="mb-6 flex justify-center">
              <div className="w-12 h-12 bg-[#F3F2EA] rounded-xl flex items-center justify-center text-[#1E1E1E] border border-[#E8E6DB]">
                <Lock size={24} />
              </div>
            </div>
            <h2 className="mt-2 mb-6 text-center text-2xl font-medium text-[#1E1E1E]">B1 Copilot Partner</h2>
            {error && <div className="mb-4 text-sm text-red-600 text-center bg-red-50 p-2 rounded-lg border border-red-100">{error}</div>}
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-[#5D5D5D]">Partner Email</label>
                <input required type="email" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 block w-full rounded-xl border border-[#E8E6DB] bg-[#FDFCF8] px-3 py-2 text-sm text-[#1E1E1E] focus:border-[#1E1E1E] focus:outline-none transition-colors" />
              </div>
              <div>
                <label className="block text-sm font-medium text-[#5D5D5D]">Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 block w-full rounded-xl border border-[#E8E6DB] bg-[#FDFCF8] px-3 py-2 text-sm text-[#1E1E1E] focus:border-[#1E1E1E] focus:outline-none transition-colors" />
              </div>
              <button type="submit" className="w-full flex justify-center py-2.5 px-4 rounded-xl text-sm font-medium text-white bg-[#1E1E1E] hover:bg-black transition-colors cursor-pointer">Sign in</button>
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
            <div className="w-10 h-10 bg-[#F3F2EA] text-[#1E1E1E] flex items-center justify-center rounded-xl border border-[#E8E6DB]">
              <Database size={20} />
            </div>
            <div>
              <h1 className="text-xl font-medium text-[#1E1E1E]">B1 Copilot Tenants</h1>
              <p className="text-xs text-[#5D5D5D]">Manage your customers' SAP connections</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <a href="/admin/migration" className="flex items-center gap-2 bg-[#F3F2EA] text-gray-700 px-4 py-2 rounded-xl text-sm font-medium hover:bg-[#E8E6DB] transition-colors cursor-pointer border border-[#E8E6DB]">
              Data Migration
            </a>
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-[#1E1E1E] text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-black shadow-sm transition-colors cursor-pointer">
              <Plus size={16} /> Add Tenant
            </button>
            <button onClick={() => { setToken(null); localStorage.removeItem('cira-partner-admin-token') }} className="flex items-center gap-2 text-[#5D5D5D] hover:text-[#1E1E1E] bg-[#F3F2EA] px-3 py-2 rounded-xl text-sm font-medium cursor-pointer border border-[#E8E6DB] transition-colors">
              <LogOut size={16} /> Logout
            </button>
          </div>
        </div>

        {testResult && (
          <div className={`mb-6 p-4 rounded-2xl border ${testResult.success ? 'bg-green-50 border-green-200 text-green-900' : 'bg-red-50 border-red-200 text-red-900'}`}>
            <div className="flex items-center gap-2 font-medium text-sm">
              {testResult.success ? <CheckCircle2 className="text-green-600" size={18} /> : <XCircle className="text-red-600" size={18} />}
              {testResult.host ? `Connection Test Result for ${testResult.host}:` : 'Connection Test Result:'}
            </div>
            {testResult.error || testResult.detail ? (
              <div className="text-xs mt-1 font-mono text-red-700">{testResult.error || testResult.detail}</div>
            ) : (
              <div className="text-xs mt-1 space-y-1">
                <div>DB Port ({testResult.hana_port}): {testResult.db_port_reachable ? 'Reachable' : `Unreachable (${testResult.db_port_error || 'timeout'})`}</div>
                <div>Service Layer Port ({testResult.sl_port}): {testResult.service_layer_port_reachable ? 'Reachable' : `Unreachable (${testResult.sl_port_error || 'timeout'})`}</div>
              </div>
            )}
          </div>
        )}

        {showAdd && (
          <div className="mb-8 bg-white p-6 rounded-2xl shadow-sm border border-[#E8E6DB]">
            <h3 className="text-lg font-medium mb-4 text-[#1E1E1E]">New Tenant Connection</h3>
            <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Company Name</label>
                <input required type="text" value={formData.company_name} onChange={e => setFormData({...formData, company_name: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. Sterling Motors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Company DB Name (Unique Identifier)</label>
                <input required type="text" value={formData.company_db} onChange={e => setFormData({...formData, company_db: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. STERLING_LIVE" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">SAP Host / IP</label>
                <input required type="text" value={formData.sap_host} onChange={e => setFormData({...formData, sap_host: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. 192.168.1.50 or 127.0.0.1" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Backend Type</label>
                <select value={formData.backend_type} onChange={e => setFormData({...formData, backend_type: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-white p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors">
                  <option value="hana">HANA SQL</option>
                  <option value="mssql">MS SQL</option>
                  <option value="service_layer">Service Layer Only</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">DB Port (HANA: 30013 / MSSQL: 1433)</label>
                <input required type="number" value={formData.sap_hana_port} onChange={e => setFormData({...formData, sap_hana_port: parseInt(e.target.value, 10) || 0})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Service Layer Port</label>
                <input required type="number" value={formData.sap_sl_port} onChange={e => setFormData({...formData, sap_sl_port: parseInt(e.target.value, 10) || 0})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Database Username</label>
                <input required type="text" value={formData.sap_db_user} onChange={e => setFormData({...formData, sap_db_user: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. SYSTEM" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Database Password</label>
                <input required type="password" value={formData.sap_db_password} onChange={e => setFormData({...formData, sap_db_password: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Service Layer User</label>
                <input required type="text" value={formData.sap_sl_user} onChange={e => setFormData({...formData, sap_sl_user: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" placeholder="e.g. manager" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#5D5D5D] mb-1">Service Layer Password</label>
                <input required type="password" value={formData.sap_sl_password} onChange={e => setFormData({...formData, sap_sl_password: e.target.value})} className="w-full rounded-lg border border-[#E8E6DB] bg-[#FDFCF8] p-2 text-sm text-[#1E1E1E] focus:outline-none focus:border-[#1E1E1E] transition-colors" />
              </div>
              <div className="col-span-1 md:col-span-2 flex justify-end gap-3 mt-4 pt-4 border-t border-[#E8E6DB]">
                <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm font-medium text-[#5D5D5D] hover:bg-[#F3F2EA] rounded-lg cursor-pointer transition-colors border border-transparent">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-medium text-white bg-[#1E1E1E] hover:bg-black rounded-lg shadow-sm cursor-pointer transition-colors">Save Tenant</button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-[#E8E6DB] overflow-hidden">
          <table className="min-w-full divide-y divide-[#E8E6DB]">
            <thead className="bg-[#F3F2EA]">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Company</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">DB Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">SAP Host</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Backend</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-[#5D5D5D] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-[#E8E6DB]">
              {tenants.map((t) => (
                <tr key={t.id} className="hover:bg-[#FDFCF8] transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-[#1E1E1E]">{t.company_name}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded text-[#1E1E1E] bg-[#F3F2EA] border border-[#E8E6DB]">
                      {t.company_db}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-[#1E1E1E] font-mono">
                    <Server size={14} className="inline mr-1 text-[#5D5D5D]" />
                    {t.sap_host}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-xs font-medium text-[#5D5D5D] uppercase">
                    {t.backend_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    {t.is_active ? (
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-green-50 text-green-700 border border-green-200">Active</span>
                    ) : (
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-medium rounded bg-red-50 text-red-700 border border-red-200">Inactive</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium flex items-center justify-end gap-2">
                    <button
                      onClick={() => handleTestConnection(t.id)}
                      disabled={testingId === t.id}
                      title="Test Connection"
                      className="text-[#1E1E1E] hover:bg-[#F3F2EA] border border-[#E8E6DB] p-2 rounded-lg transition-colors cursor-pointer"
                    >
                      <Activity size={16} className={testingId === t.id ? "animate-pulse" : ""} />
                    </button>
                    <button
                      onClick={() => handleDelete(t.id)}
                      title="Delete Tenant"
                      className="text-red-600 hover:bg-red-50 border border-red-100 p-2 rounded-lg transition-colors cursor-pointer"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-[#5D5D5D] text-sm">
                    No tenants found. Add your first client to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
