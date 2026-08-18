import * as XLSX from 'xlsx';

export function exportToExcel(data: any[], filename: string = 'sap_export.xlsx') {
  if (!data || data.length === 0) return;
  
  const worksheet = XLSX.utils.json_to_sheet(data);
  
  // Auto-size columns for readability
  const colWidths = Object.keys(data[0]).map((key) => ({
    wch: Math.max(key.length, ...data.map((row) => String(row[key] ?? '').length)) + 2
  }));
  worksheet['!cols'] = colWidths;
  
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'SAP_Data');
  XLSX.writeFile(workbook, filename);
}
