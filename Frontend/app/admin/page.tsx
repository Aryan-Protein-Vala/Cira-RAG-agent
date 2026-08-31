'use client'

import React, { useState, useEffect } from 'react'
import { Database, Plus, Trash2, Key, Server, Lock, LogOut } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [connections, setConnections] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [formData, setFormData] = useState({
    company_db: '',
    hana_address: '',
    hana_port: 30013,
    hana_user: '',
    hana_password: '',
    service_layer_port: 50000
  })

  useEffect(() => {
    const stored = localStorage.getItem('cira-admin-token')
    if (stored) {
      setToken(stored)
      loadConnections(stored)
    }
  }, [])

  const loadConnections = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/admin/connections`, {
        headers: { Authorization: `Bearer ${authToken}` }
      })
      if (!res.ok) throw new Error('Failed to load connections')
      const data = await res.json()
      setConnections(data)
    } catch (err) {
      setError('Failed to load connections. Session may be expired.')
      setToken(null)
      localStorage.removeItem('cira-admin-token')
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
      if (!res.ok) throw new Error('Invalid admin credentials')
      const data = await res.json()
      setToken(data.token)
      localStorage.setItem('cira-admin-token', data.token)
      loadConnections(data.token)
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch(`${API_BASE}/admin/connections`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify(formData)
      })
      if (!res.ok) {
        const d = await res.json()
        throw new Error(d.detail || 'Failed to add connection')
      }
      setShowAdd(false)
      loadConnections(token!)
      setFormData({
        company_db: '',
        hana_address: '',
        hana_port: 30013,
        hana_user: '',
        hana_password: '',
        service_layer_port: 50000
      })
    } catch (err: any) {
      alert(err.message)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this connection?')) return
    try {
      const res = await fetch(`${API_BASE}/admin/connections/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to delete')
      loadConnections(token!)
    } catch (err: any) {
      alert(err.message)
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
            <h2 className="mt-2 mb-6 text-center text-2xl font-bold text-gray-900">Admin Control Panel</h2>
            {error && <div className="mb-4 text-sm text-rose-500 text-center bg-rose-50 p-2 rounded-lg">{error}</div>}
            <form onSubmit={handleLogin} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700">Username</label>
                <input required type="text" value={username} onChange={e => setUsername(e.target.value)} className="mt-1 block w-full rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Password</label>
                <input required type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 block w-full rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer" />
              </div>
              <button type="submit" className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-xl shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 cursor-pointer">Sign in to Admin</button>
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
              <h1 className="text-xl font-bold text-gray-900">Tenant Connections</h1>
              <p className="text-xs text-gray-500">Manage multi-tenant SAP HANA databases</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-indigo-700 shadow-sm transition-colors cursor-pointer">
              <Plus size={16} /> Add Connection
            </button>
            <button onClick={() => { setToken(null); localStorage.removeItem('cira-admin-token') }} className="flex items-center gap-2 text-gray-500 hover:text-gray-700 bg-gray-100 px-3 py-2 rounded-xl text-sm font-semibold cursor-pointer">
              <LogOut size={16} /> Logout
            </button>
          </div>
        </div>

        {showAdd && (
          <div className="mb-8 bg-white p-6 rounded-2xl shadow-lg border border-indigo-100">
            <h3 className="text-lg font-bold mb-4 text-gray-900">New Database Connection</h3>
            <form onSubmit={handleAdd} className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Company DB Name (Unique Identifier)</label>
                <input required type="text" value={formData.company_db} onChange={e => setFormData({...formData, company_db: e.target.value})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" placeholder="e.g. CIRA_DEMO_NEW" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">HANA Address (IP/Host)</label>
                <input required type="text" value={formData.hana_address} onChange={e => setFormData({...formData, hana_address: e.target.value})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" placeholder="e.g. 20.204.5.237" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">HANA Port</label>
                <input required type="number" value={formData.hana_port} onChange={e => setFormData({...formData, hana_port: parseInt(e.target.value)})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Service Layer Port</label>
                <input required type="number" value={formData.service_layer_port} onChange={e => setFormData({...formData, service_layer_port: parseInt(e.target.value)})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Database Username</label>
                <input required type="text" value={formData.hana_user} onChange={e => setFormData({...formData, hana_user: e.target.value})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" placeholder="e.g. SYSTEM" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Database Password</label>
                <input required type="password" value={formData.hana_password} onChange={e => setFormData({...formData, hana_password: e.target.value})} className="w-full rounded-lg border border-gray-300 p-2 text-sm cursor-pointer" />
              </div>
              <div className="col-span-1 md:col-span-2 flex justify-end gap-3 mt-2">
                <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 rounded-lg cursor-pointer">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm cursor-pointer">Save Connection</button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">ID</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Company DB</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">HANA Host</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Ports (SQL/SL)</th>
                <th className="px-6 py-3 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">User</th>
                <th className="px-6 py-3 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {connections.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">#{c.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                      {c.company_db}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-mono">
                    <Server size={14} className="inline mr-1 text-gray-400" />
                    {c.hana_address}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {c.hana_port} / {c.service_layer_port}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    <Key size={14} className="inline mr-1 text-gray-400" />
                    {c.hana_user}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button onClick={() => handleDelete(c.id)} className="text-rose-600 hover:text-rose-900 bg-rose-50 p-2 rounded-lg transition-colors cursor-pointer">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {connections.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 text-sm">
                    No tenant connections found. Add one to get started.
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
