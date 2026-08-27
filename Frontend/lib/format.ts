/**
 * Shared number formatting.
 *
 * The product promise is Indian rupees with Indian digit grouping (₹1,50,000),
 * and the LLM is told so in the system prompt — but a prompt is not a guarantee.
 * Everything the UI renders itself goes through here instead, so tables, axes and
 * tooltips are consistent whether or not the model obeyed.
 */

const MONEY_HINT = /(doctotal|linetotal|nettotal|gross|amount|balance|price|rate|value|total|debit|credit|paid|salary|cost|sum|fc|vatsum|linecnt)/i
const NOT_MONEY = /(count|qty|quantity|num|lines|year|month|day|pos|rank|percent|share|id|entry|days|hours)/i

/** Heuristic: does this column name look like an amount rather than a count? */
export function isMoneyColumn(name?: string | null): boolean {
  if (!name) return false
  const key = name.replace(/_/g, '').toLowerCase()
  if (NOT_MONEY.test(key)) return false
  return MONEY_HINT.test(key)
}

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const inrMoney = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 2,
})

export function formatNumber(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') {
    return Number.isNaN(value) ? '' : inr.format(value)
  }
  return String(value)
}

export function formatMoney(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return formatNumber(value)
  return inrMoney.format(value)
}

/** Cell-level dispatch used by the data table. */
export function formatCellValue(value: unknown, column?: string | null): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value !== 'number') return String(value)
  return isMoneyColumn(column) ? formatMoney(value) : formatNumber(value)
}

/**
 * Axis labels in Indian units: 1,000 = 1T, 1,00,000 = 1L, 1,00,00,000 = 1Cr.
 * (en-US "K/M" reads wrong to the audience this tool is built for.)
 */
export function formatCompact(value: number, money = false): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return String(value ?? '')
  const sign = value < 0 ? '-' : ''
  const abs = Math.abs(value)
  const prefix = money ? '₹' : ''
  if (abs >= 1e7) return `${sign}${prefix}${trim(abs / 1e7)}Cr`
  if (abs >= 1e5) return `${sign}${prefix}${trim(abs / 1e5)}L`
  if (abs >= 1e3) return `${sign}${prefix}${trim(abs / 1e3)}K`
  return `${sign}${prefix}${Math.round(abs)}`
}

function trim(n: number): string {
  return n.toFixed(1).replace(/\.0$/, '')
}
