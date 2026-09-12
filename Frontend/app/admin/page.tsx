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
      <div className="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-4 shadow-xl sm:rounded-2xl sm:px-10 border border-gray-100">
            <div className="mb-6 flex justify-center">
              <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-indigo-200">
                <Lock size={24} />
              </div>
            </div>
            <h2 className="mt-2 mb-6 text-center text-2xl font-bold text-gray-900">Partner Admin Panel</h2>
            {error && <div className="mb-4 text-sm text-rose-500 text-center bg-rose-50 p-2 rounded-lg">{error}</div>}
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700">Partner Email</label>
                <input required type="email" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 block w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 block w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              </div>
              <button type="submit" className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-xl shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 cursor-pointer">Sign in</button>
            </form>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8 bg-white p-4 rounded-2xl shadow-sm border border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-100 text-indigo-600 flex items-center justify-center rounded-xl">
              <Database size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Client Tenants</h1>
              <p className="text-xs text-gray-500">Manage your customers' SAP connections</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-indigo-700 shadow-sm transition-colors cursor-pointer">
              <Plus size={16} /> Add Tenant
            </button>
            <button onClick={() => { setToken(null); localStorage.removeItem('cira-partner-admin-token') }} className="flex items-center gap-2 text-gray-500 hover:text-gray-700 bg-gray-100 px-3 py-2 rounded-xl text-sm font-semibold cursor-pointer">
              <LogOut size={16} /> Logout
            </button>
          </div>
        </div>

        {testResult && (
          <div className={`mb-6 p-4 rounded-2xl border ${testResult.success ? 'bg-emerald-50 border-emerald-200 text-emerald-900' : 'bg-rose-50 border-rose-200 text-rose-900'}`}>
            <div className="flex items-center gap-2 font-bold text-sm">
              {testResult.success ? <CheckCircle2 className="text-emerald-600" size={18} /> : <XCircle className="text-rose-600" size={18} />}
              {testResult.host ? `Connection Test Result for ${testResult.host}:` : 'Connection Test Result:'}
            </div>
            {testResult.error || testResult.detail ? (
              <div className="text-xs mt-1 font-mono text-rose-700">{testResult.error || testResult.detail}</div>
            ) : (
              <div className="text-xs mt-1 space-y-1">
                <div>DB Port ({testResult.hana_port}): {testResult.db_port_reachable ? 'Reachable' : `Unreachable (${testResult.db_port_error || 'timeout'})`}</div>
                <div>Service Layer Port ({testResult.sl_port}): {testResult.service_layer_port_reachable ? 'Reachable' : `Unreachable (${testResult.sl_port_error || 'timeout'})`}</div>
              </div>
            )}
          </div>
        )}

        {showAdd && (
          <div className="mb-8 bg-white p-6 rounded-2xl shadow-lg border border-indigo-100">
            <h3 className="text-lg font-bold mb-4 text-gray-900">New Tenant Connection</h3>
            <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Company Name</label>
                <input required type="text" value={formData.company_name} onChange={e => setFormData({...formData, company_name: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" placeholder="e.g. Sterling Motors" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Company DB Name (Unique Identifier)</label>
                <input required type="text" value={formData.company_db} onChange={e => setFormData({...formData, company_db: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" placeholder="e.g. STERLING_LIVE" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">SAP Host / IP</label>
                <input required type="text" value={formData.sap_host} onChange={e => setFormData({...formData, sap_host: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" placeholder="e.g. 192.168.1.50 or 127.0.0.1" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Backend Type</label>
                <select value={formData.backend_type} onChange={e => setFormData({...formData, backend_type: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900">
                  <option value="hana">HANA SQL</option>
                  <option value="mssql">MS SQL</option>
                  <option value="service_layer">Service Layer Only</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">DB Port (HANA: 30013 / MSSQL: 1433)</label>
                <input required type="number" value={formData.sap_hana_port} onChange={e => setFormData({...formData, sap_hana_port: parseInt(e.target.value, 10) || 0})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Service Layer Port</label>
                <input required type="number" value={formData.sap_sl_port} onChange={e => setFormData({...formData, sap_sl_port: parseInt(e.target.value, 10) || 0})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Database Username</label>
                <input required type="text" value={formData.sap_db_user} onChange={e => setFormData({...formData, sap_db_user: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" placeholder="e.g. SYSTEM" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Database Password</label>
                <input required type="password" value={formData.sap_db_password} onChange={e => setFormData({...formData, sap_db_password: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Service Layer User</label>
                <input required type="text" value={formData.sap_sl_user} onChange={e => setFormData({...formData, sap_sl_user: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" placeholder="e.g. manager" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Service Layer Password</label>
                <input required type="password" value={formData.sap_sl_password} onChange={e => setFormData({...formData, sap_sl_password: e.target.value})} className="w-full rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900" />
              </div>
              <div className="col-span-1 md:col-span-2 flex justify-end gap-3 mt-2">
                <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 rounded-lg cursor-pointer">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm cursor-pointer">Save Tenant</button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Company</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">DB Name</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">SAP Host</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Backend</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {tenants.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-900">{t.company_name}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                      {t.company_db}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-mono">
                    <Server size={14} className="inline mr-1 text-gray-400" />
                    {t.sap_host}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    <span className="uppercase text-xs font-semibold text-gray-400">{t.backend_type}</span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {t.is_active ? (
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">Active</span>
                    ) : (
                      <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-rose-100 text-rose-800">Inactive</span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium flex items-center justify-end gap-2">
                    <button
                      onClick={() => handleTestConnection(t.id)}
                      disabled={testingId === t.id}
                      title="Test Connection"
                      className="text-indigo-600 hover:text-indigo-900 bg-indigo-50 p-2 rounded-lg transition-colors cursor-pointer"
                    >
                      <Activity size={16} className={testingId === t.id ? "animate-pulse" : ""} />
                    </button>
                    <button
                      onClick={() => handleDelete(t.id)}
                      title="Delete Tenant"
                      className="text-rose-600 hover:text-rose-900 bg-rose-50 p-2 rounded-lg transition-colors cursor-pointer"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {tenants.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 text-sm">
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
