import * as XLSX from 'xlsx';

/** Flatten a row: nested objects/arrays become readable strings */
function flattenRow(row: Record<string, any>): Record<string, any> {
  const flat: Record<string, any> = {};
  for (const [key, value] of Object.entries(row)) {
    if (value === null || value === undefined) {
      flat[key] = '';
    } else if (typeof value === 'object' && !Array.isArray(value)) {
      // Inline nested object keys as "parent.child"
      for (const [subKey, subVal] of Object.entries(value)) {
        flat[`${key}.${subKey}`] = subVal ?? '';
      }
    } else if (Array.isArray(value)) {
      flat[key] = value.join(', ');
    } else {
      flat[key] = value;
    }
  }
  return flat;
}

export function exportToExcel(data: any[], filename: string = 'sap_export.xlsx') {
  if (!data || data.length === 0) return;
  
  // Fix Functionality-7: flatten nested objects to avoid [object Object] in cells
  const flat = data.map(flattenRow);

  const worksheet = XLSX.utils.json_to_sheet(flat);
  
  // Auto-size columns for readability
  const colWidths = Object.keys(flat[0]).map((key) => ({
    wch: Math.max(key.length, ...flat.map((row) => String(row[key] ?? '').length)) + 2
  }));
  worksheet['!cols'] = colWidths;
  
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, 'SAP_Data');
  XLSX.writeFile(workbook, filename);
}
