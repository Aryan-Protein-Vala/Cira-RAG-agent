'use client'

import React, { useState, useEffect } from 'react'
import { Upload, ArrowRight, CheckCircle2, XCircle, FileSpreadsheet, Loader2, Play } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api'

export default function MigrationPage() {
  const [token, setToken] = useState<string | null>(null)
  
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  
  const [uploadResult, setUploadResult] = useState<any>(null)
  const [mapping, setMapping] = useState<any[]>([])
  
  const [validationResult, setValidationResult] = useState<any>(null)
  const [validating, setValidating] = useState(false)
  
  const [pushing, setPushing] = useState(false)
  const [pushResult, setPushResult] = useState<any>(null)

  useEffect(() => {
    const stored = localStorage.getItem('cira-partner-admin-token')
    if (stored) setToken(stored)
  }, [])

  if (!token) {
    return (
      <div className="min-h-screen bg-[#FDFCF8] p-8 flex items-center justify-center">
        <div className="text-center text-red-500">
          Not authenticated. Please go to /admin to sign in first.
        </div>
      </div>
    )
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0])
      setUploadResult(null)
      setValidationResult(null)
      setPushResult(null)
      setError('')
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setUploading(true)
    setError('')
    
    const formData = new FormData()
    formData.append('file', file)
    
    try {
      const res = await fetch(`${API_BASE}/admin/migration/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })
      
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      
      setUploadResult(data)
      setMapping(data.headers)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }

  const handleMappingChange = (index: number, newTarget: string) => {
    const newMapping = [...mapping]
    newMapping[index].target = newTarget
    setMapping(newMapping)
  }

  const handleValidate = async () => {
    setValidating(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/admin/migration/validate`, {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mapping,
          rows: uploadResult.raw_data
        })
      })
      
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Validation failed')
      
      setValidationResult(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setValidating(false)
    }
  }

  const handlePush = async () => {
    setPushing(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/admin/migration/push`, {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          valid_rows: validationResult.valid_rows
        })
      })
      
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Push failed')
      
      setPushResult(data)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setPushing(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#FDFCF8] text-[#1E1E1E] p-8 md:p-12 font-sans selection:bg-[#E8E6DB]">
      <div className="max-w-4xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-medium tracking-tight">Data Migration</h1>
          <p className="text-sm text-[#5D5D5D] mt-1">Import Business Partners into SAP Business One</p>
        </div>
        
        {error && (
          <div className="bg-red-50 text-red-700 p-4 rounded-xl text-sm border border-red-100 flex items-center gap-2">
            <XCircle size={16} />
            {error}
          </div>
        )}

        {/* Step 1: Upload */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-[#E8E6DB] space-y-4">
          <h2 className="text-lg font-medium flex items-center gap-2">
            <span className="w-6 h-6 rounded-full bg-[#F3F2EA] flex items-center justify-center text-xs">1</span>
            Upload File
          </h2>
          <div className="border-2 border-dashed border-[#E8E6DB] rounded-xl p-8 text-center bg-[#FDFCF8]">
            <input 
              type="file" 
              id="file-upload" 
              className="hidden" 
              accept=".xlsx,.csv"
              onChange={handleFileChange}
            />
            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-2">
              <div className="w-12 h-12 bg-white rounded-xl shadow-sm border border-[#E8E6DB] flex items-center justify-center text-[#5D5D5D]">
                <FileSpreadsheet size={24} />
              </div>
              <span className="font-medium text-[#1E1E1E]">
                {file ? file.name : 'Select Excel or CSV file'}
              </span>
              <span className="text-xs text-[#5D5D5D]">Click to browse (max 5MB)</span>
            </label>
          </div>
          
          {file && !uploadResult && (
            <div className="flex justify-end">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="bg-[#1E1E1E] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-black transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {uploading && <Loader2 size={16} className="animate-spin" />}
                Upload & Parse
              </button>
            </div>
          )}
        </div>

        {/* Step 2: Mapping */}
        {uploadResult && !validationResult && (
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-[#E8E6DB] space-y-4 animate-in fade-in slide-in-from-bottom-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-[#F3F2EA] flex items-center justify-center text-xs">2</span>
                Field Mapping
              </h2>
              <span className="text-xs font-medium bg-[#F3F2EA] px-2 py-1 rounded text-[#5D5D5D]">
                {uploadResult.total_rows} rows found
              </span>
            </div>
            
            <div className="bg-[#FDFCF8] rounded-xl border border-[#E8E6DB] overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-[#F3F2EA] text-[#5D5D5D]">
                  <tr>
                    <th className="px-4 py-3 font-medium">Source Column</th>
                    <th className="px-4 py-3 font-medium w-8"></th>
                    <th className="px-4 py-3 font-medium">SAP Field</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E8E6DB]">
                  {mapping.map((m, i) => (
                    <tr key={i} className={m.confidence > 0 ? "bg-green-50/30" : ""}>
                      <td className="px-4 py-3 font-medium">{m.source}</td>
                      <td className="px-4 py-3 text-[#A8A8A8]"><ArrowRight size={14} /></td>
                      <td className="px-4 py-2">
                        <select 
                          className="w-full p-2 rounded bg-white border border-[#E8E6DB] outline-none focus:border-[#1E1E1E] transition-colors"
                          value={m.target}
                          onChange={e => handleMappingChange(i, e.target.value)}
                        >
                          <option value="">-- Ignore --</option>
                          <option value="CardCode">CardCode (BP Code)</option>
                          <option value="CardName">CardName (BP Name)</option>
                          <option value="CardType">CardType (C/S/L)</option>
                          <option value="Phone1">Phone1</option>
                          <option value="Cellular">Cellular</option>
                          <option value="E_Mail">E_Mail</option>
                          <option value="VatIdUnCmp">VatIdUnCmp (GSTIN)</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            
            <div className="flex justify-end pt-2">
              <button
                onClick={handleValidate}
                disabled={validating}
                className="bg-[#1E1E1E] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-black transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {validating && <Loader2 size={16} className="animate-spin" />}
                Validate Data
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Validation Results & Push */}
        {validationResult && !pushResult && (
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-[#E8E6DB] space-y-6 animate-in fade-in slide-in-from-bottom-4">
            <h2 className="text-lg font-medium flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-[#F3F2EA] flex items-center justify-center text-xs">3</span>
              Review & Push
            </h2>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-[#E8E6DB] bg-[#FDFCF8]">
                <div className="text-[#5D5D5D] text-xs font-medium mb-1 uppercase tracking-wider">Valid Rows</div>
                <div className="text-3xl font-light text-green-600">{validationResult.valid_count}</div>
              </div>
              <div className="p-4 rounded-xl border border-[#E8E6DB] bg-[#FDFCF8]">
                <div className="text-[#5D5D5D] text-xs font-medium mb-1 uppercase tracking-wider">Errors</div>
                <div className="text-3xl font-light text-red-600">{validationResult.error_count}</div>
              </div>
            </div>
            
            {validationResult.errors.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-red-600">Validation Issues</h3>
                <div className="bg-red-50 rounded-xl border border-red-100 overflow-hidden text-sm">
                  <div className="max-h-48 overflow-y-auto">
                    {validationResult.errors.map((err: any, i: number) => (
                      <div key={i} className="p-3 border-b border-red-100 last:border-0">
                        <div className="font-medium text-red-700 mb-1">Row {err.row}</div>
                        <ul className="list-disc pl-5 text-red-600/80 space-y-1">
                          {err.errors.map((msg: string, j: number) => (
                            <li key={j}>{msg}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            
            <div className="flex justify-end pt-2">
              <button
                onClick={handlePush}
                disabled={pushing || validationResult.valid_count === 0}
                className="bg-blue-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-2 shadow-sm"
              >
                {pushing ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} fill="currentColor" />}
                Push {validationResult.valid_count} Rows to SAP
              </button>
            </div>
          </div>
        )}
        
        {/* Step 4: Final Result */}
        {pushResult && (
          <div className="bg-white p-8 rounded-2xl shadow-sm border border-green-200 space-y-4 animate-in fade-in zoom-in-95 text-center">
            <div className="w-16 h-16 bg-green-50 text-green-500 rounded-full flex items-center justify-center mx-auto mb-2">
              <CheckCircle2 size={32} />
            </div>
            <h2 className="text-2xl font-medium">Migration Complete</h2>
            
            <div className="flex justify-center gap-8 pt-4">
              <div className="text-center">
                <div className="text-3xl font-light">{pushResult.success}</div>
                <div className="text-xs font-medium text-[#5D5D5D] uppercase tracking-wider mt-1">Successfully Pushed</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-light text-red-500">{pushResult.failed}</div>
                <div className="text-xs font-medium text-red-500/70 uppercase tracking-wider mt-1">Failed</div>
              </div>
            </div>
            
            {pushResult.errors.length > 0 && (
              <div className="text-left mt-6 bg-red-50 p-4 rounded-xl border border-red-100 max-h-40 overflow-y-auto text-sm text-red-700">
                <div className="font-medium mb-2">Push Errors:</div>
                <ul className="space-y-2">
                  {pushResult.errors.map((e: any, i: number) => (
                    <li key={i}><span className="font-medium">{e.cardcode}</span>: {e.error}</li>
                  ))}
                </ul>
              </div>
            )}
            
            <div className="pt-6">
              <button
                onClick={() => {
                  setFile(null); setUploadResult(null); setValidationResult(null); setPushResult(null);
                }}
                className="text-sm font-medium text-[#5D5D5D] hover:text-[#1E1E1E] transition-colors"
              >
                Start New Migration
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
