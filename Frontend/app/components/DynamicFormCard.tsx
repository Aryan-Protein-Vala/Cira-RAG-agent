import React, { useState } from 'react';
import { Sparkles, Save, Check, X, Loader2 } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

export interface FormField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'date' | 'select' | 'email' | 'phone';
  required?: boolean;
  options?: { value: string; label: string }[];
  default?: any;
  hint?: string;
}

export interface FormPayload {
  entity: string;
  table: string;
  title: string;
  fields: FormField[];
}

interface DynamicFormCardProps {
  payload: FormPayload;
  token?: string;
  messageKey?: string;
  onSuccess?: () => void;
}

export function DynamicFormCard({ payload, token, messageKey, onSuccess }: DynamicFormCardProps) {
  const [formData, setFormData] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    for (const field of payload.fields) {
      if (field.default !== undefined) {
        initial[field.name] = field.default;
      } else if (field.type === 'date') {
        initial[field.name] = new Date().toISOString().split('T')[0];
      }
    }
    return initial;
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(() => {
    if (messageKey && typeof window !== 'undefined') {
      return localStorage.getItem(`form-success-${messageKey}`) === 'true';
    }
    return false;
  });

  const handleChange = (name: string, value: any) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/sap/write`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`,
        },
        body: JSON.stringify({
          entity: payload.entity,
          table: payload.table,
          data: formData,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to create record');
      }

      setSuccess(true);
      if (messageKey) {
        localStorage.setItem(`form-success-${messageKey}`, 'true');
      }
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="chart-card-wrapper bg-white border border-indigo-100 rounded-2xl p-6 w-full shadow-lg my-2 transform hover:-translate-y-1 transition-all duration-300">
        <div className="flex items-center gap-3 text-indigo-600 mb-2">
          <div className="p-2 rounded-full bg-indigo-100">
            <Check size={20} />
          </div>
          <h3 className="font-bold text-lg">Record Created</h3>
        </div>
        <p className="text-sm text-gray-600 ml-11 font-medium">
          The {payload.entity} record has been successfully written to SAP Business One.
        </p>
      </div>
    );
  }

  return (
    <div 
      className="chart-card-wrapper bg-white rounded-2xl shadow-lg border border-gray-100 w-full flex flex-col animate-fade-in text-gray-900 overflow-hidden transform hover:-translate-y-1 hover:shadow-xl transition-all duration-300 my-2"
      style={{ animationFillMode: 'both', animationDelay: '100ms' }}
    >
      <div className="bg-gradient-to-r from-indigo-500 to-blue-500 px-4 py-3 flex items-center justify-between text-white">
        <div>
          <span className="text-[10px] font-extrabold tracking-wider uppercase text-indigo-100 flex items-center gap-1">
            <Sparkles size={11} className="text-white" /> SAP WRITE OP
          </span>
          <strong className="text-xs md:text-sm font-black text-white line-clamp-1">
            {payload.title || `Create ${payload.entity}`}
          </strong>
        </div>
      </div>
      
      <form onSubmit={handleSubmit} className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5 bg-white">
        {payload.fields.map((field) => (
          <div key={field.name} className="flex flex-col gap-1.5">
            <label htmlFor={field.name} className="text-gray-500 text-[11px] uppercase tracking-wider font-extrabold">
              {field.label} {field.required && <span className="text-indigo-500">*</span>}
            </label>
            
            {field.type === 'select' ? (
              <select
                id={field.name}
                required={field.required}
                value={formData[field.name] || ''}
                onChange={(e) => handleChange(field.name, e.target.value)}
                className="bg-gray-50 border border-gray-200 rounded-xl p-2.5 text-sm font-semibold text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all hover:border-gray-300"
              >
                <option value="" disabled>Select {field.label}...</option>
                {(Array.isArray(field.options) 
                  ? field.options 
                  : (typeof field.options === 'object' && field.options !== null)
                    ? Object.entries(field.options).map(([k, v]) => ({ value: k, label: typeof v === 'string' ? v : String(v) }))
                    : []
                ).map((opt: any) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label} ({opt.value})
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={field.name}
                type={field.type === 'number' ? 'number' : field.type === 'date' ? 'date' : 'text'}
                required={field.required}
                value={formData[field.name] || ''}
                onChange={(e) => handleChange(field.name, field.type === 'number' ? parseFloat(e.target.value) : e.target.value)}
                placeholder={`Enter ${field.label}...`}
                className="bg-gray-50 border border-gray-200 rounded-xl p-2.5 text-sm font-semibold text-gray-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all hover:border-gray-300 placeholder:text-gray-400"
              />
            )}
            {field.hint && (
              <span className="text-gray-500 text-[10px] pl-1 font-medium">{field.hint}</span>
            )}
          </div>
        ))}

        {error && (
          <div className="col-span-1 md:col-span-2 bg-rose-50 border border-rose-200 text-rose-600 p-4 rounded-xl flex items-start gap-3 text-xs mt-2 shadow-sm font-semibold">
            <X size={16} className="mt-0.5 shrink-0" />
            <p className="leading-relaxed">{error}</p>
          </div>
        )}

        <div className="col-span-1 md:col-span-2 pt-5 pb-1 flex justify-end">
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-blue-500 text-white font-extrabold rounded-xl hover:from-indigo-500 hover:to-blue-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-indigo-500/20 active:scale-[0.98]"
          >
            {isSubmitting ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            {isSubmitting ? 'Saving...' : 'Submit to SAP'}
          </button>
        </div>
      </form>
    </div>
  );
}
