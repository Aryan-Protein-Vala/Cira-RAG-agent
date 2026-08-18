"use client";

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Download, Copy, Check } from 'lucide-react';

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
    <Card className="w-full max-w-2xl bg-zinc-950 border-zinc-800 text-zinc-100 my-4 shadow-lg">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-zinc-400">Data Preview</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border border-zinc-800 overflow-x-auto">
          <Table>
            <TableHeader className="bg-zinc-900/50">
              <TableRow className="border-zinc-800 hover:bg-transparent">
                {headers.map(header => (
                  <TableHead key={header} className="text-zinc-300 font-semibold">{header}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.slice(0, 5).map((row, i) => (
                <TableRow key={i} className="border-zinc-800 hover:bg-zinc-900/50">
                  {headers.map(header => (
                    <TableCell key={header} className="text-zinc-400 py-2">{row[header]}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {data.length > 5 && (
          <p className="text-xs text-zinc-500 mt-2 text-center">Showing 5 of {data.length} rows</p>
        )}
      </CardContent>
      <CardFooter className="flex justify-end gap-2 pt-0">
        <Button variant="outline" size="sm" onClick={copyToClipboard} className="bg-zinc-900 border-zinc-700 hover:bg-zinc-800 hover:text-zinc-100 text-zinc-300 transition-colors">
          {copied ? <Check className="w-4 h-4 mr-2 text-green-400" /> : <Copy className="w-4 h-4 mr-2" />}
          Copy CSV
        </Button>
        <Button size="sm" onClick={downloadCSV} className="bg-indigo-600 hover:bg-indigo-700 text-white transition-colors border-0">
          <Download className="w-4 h-4 mr-2" />
          Download CSV
        </Button>
      </CardFooter>
    </Card>
  );
}
