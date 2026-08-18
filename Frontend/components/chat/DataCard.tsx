"use client";

import React, { useState } from 'react';
import { Download, Copy, Check, Database } from 'lucide-react';

interface DataCardProps {
  data: any[];
}

export function DataCard({ data }: DataCardProps) {
  const [copied, setCopied] = useState(false);

  if (!data || data.length === 0) return null;

  const headers = Object.keys(data[0]);

  const generateCSV = () => {
    const headerRow = headers.join(',');
    const rows = data.map(item => headers.map(header => `"${item[header]}"`).join(','));
    return [headerRow, ...rows].join('\n');
  };

  const downloadCSV = () => {
    const csvContent = generateCSV();
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'export.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const copyToClipboard = () => {
    const csvContent = generateCSV();
    navigator.clipboard.writeText(csvContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="data-card">
      <div className="data-card-head">
        <div className="data-label">
          <Database className="w-3 h-3" />
          <span>OData Result</span>
        </div>
        <div className="row-count">{data.length} records found</div>
      </div>
      <strong>SAP Tabular Data</strong>
      <div className="data-period">Previewing up to 5 rows</div>
      
      <div className="mini-table">
        <div className="mini-row mini-head" style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 3)}, 1fr)` }}>
          {headers.slice(0, 3).map(header => (
            <span key={header}>{header}</span>
          ))}
        </div>
        {data.slice(0, 5).map((row, i) => (
          <div key={i} className="mini-row" style={{ gridTemplateColumns: `repeat(${Math.min(headers.length, 3)}, 1fr)` }}>
            {headers.slice(0, 3).map(header => (
              <span key={header}>{row[header]}</span>
            ))}
          </div>
        ))}
      </div>
      
      <div className="data-actions">
        <button onClick={copyToClipboard}>
          {copied ? <Check className="w-3 h-3 text-[#7a9c7b]" /> : <Copy className="w-3 h-3" />}
          Copy CSV
        </button>
        <button onClick={downloadCSV}>
          <Download className="w-3 h-3" />
          Download CSV
        </button>
      </div>
    </div>
  );
}
