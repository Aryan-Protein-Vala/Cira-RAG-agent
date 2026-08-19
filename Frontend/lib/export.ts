/**
 * Export helpers for the DataCard.
 *
 * The previous version pulled SheetJS straight from cdn.sheetjs.com, which is
 * not on the npm registry: `npm install` fails on any machine that cannot
 * reach that CDN (corporate proxies, the RDP box, CI). We now use
 * `write-excel-file`, a registry-hosted, browser-safe writer, and CSV/JSON
 * exports have no dependency at all.
 */

type Row = Record<string, any>

/** Flatten a row: nested objects/arrays become readable scalars. */
export function flattenRow(row: Row): Row {
  const flat: Row = {}
  for (const [key, value] of Object.entries(row ?? {})) {
    if (value === null || value === undefined) {
      flat[key] = ''
    } else if (Array.isArray(value)) {
      flat[key] = value.map((v) => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(', ')
    } else if (typeof value === 'object') {
      for (const [subKey, subVal] of Object.entries(value)) {
        flat[`${key}.${subKey}`] =
          subVal === null || subVal === undefined
            ? ''
            : typeof subVal === 'object'
              ? JSON.stringify(subVal)
              : subVal
      }
    } else {
      flat[key] = value
    }
  }
  return flat
}

function collectColumns(rows: Row[]): string[] {
  const seen = new Set<string>()
  for (const row of rows) for (const key of Object.keys(row)) seen.add(key)
  return Array.from(seen)
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export async function exportToExcel(data: Row[], filename = 'sap_export.xlsx') {
  if (!data || data.length === 0) return
  const flat = data.map(flattenRow)
  const columns = collectColumns(flat)

  try {
    const writeXlsxFile = (await import('write-excel-file/browser')).default
    const sheetColumns = columns.map((column) => {
      const sample = flat.find((row) => row[column] !== '' && row[column] !== undefined)?.[column]
      const isNumeric = typeof sample === 'number'
      return {
        header: { value: column, fontWeight: 'bold' as const },
        width: Math.min(
          46,
          Math.max(column.length + 2, ...flat.slice(0, 200).map((r) => String(r[column] ?? '').length + 2)),
        ),
        cell: (row: Row) => {
          const value = row[column]
          if (value === '' || value === null || value === undefined) return { value: undefined }
          return isNumeric && typeof value === 'number'
            ? { value, type: Number, format: '#,##0.00' }
            : { value: String(value), type: String }
        },
      }
    })
    await writeXlsxFile(flat, { columns: sheetColumns, sheet: 'SAP Data' }).toFile(filename)
  } catch (error) {
    // Never leave the user without their data: fall back to CSV.
    console.error('XLSX export failed, falling back to CSV', error)
    exportToCsv(data, filename.replace(/\.xlsx$/i, '.csv'))
  }
}

export function exportToCsv(data: Row[], filename = 'sap_export.csv') {
  if (!data || data.length === 0) return
  const flat = data.map(flattenRow)
  const columns = collectColumns(flat)
  const escape = (value: any) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[",\n;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const csv = [
    columns.join(','),
    ...flat.map((row) => columns.map((c) => escape(row[c])).join(',')),
  ].join('\r\n')
  // BOM so Excel opens UTF-8 correctly
  triggerDownload(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' }), filename)
}

export function exportToJson(data: Row[], filename = 'sap_export.json') {
  if (!data) return
  triggerDownload(
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
    filename,
  )
}
