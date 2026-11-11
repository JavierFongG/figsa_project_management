// Dates travel as 'YYYY-MM-DD' strings and are handled as UTC day numbers to avoid time-zone shifts.
const DAY = 864e5
export const MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
export const MESL = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
export const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']

export const toN = (s?: string | null): number | null => {
  if (!s || !/^\d{4}-\d{2}-\d{2}/.test(s)) return null
  return Math.round(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / DAY)
}
export const fromN = (n: number) => new Date(n * DAY).toISOString().slice(0, 10)
export const dObj = (n: number) => new Date(n * DAY)
export const dow = (n: number) => dObj(n).getUTCDay()
export const mondayOf = (n: number) => n - ((dow(n) + 6) % 7)

export function isoWeek(n: number) {
  const d = dObj(n)
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))
  const dn = (t.getUTCDay() + 6) % 7
  t.setUTCDate(t.getUTCDate() - dn + 3)
  const f = new Date(Date.UTC(t.getUTCFullYear(), 0, 4))
  return 1 + Math.round(((t.getTime() - f.getTime()) / DAY - 3 + ((f.getUTCDay() + 6) % 7)) / 7)
}

type D = string | number | null | undefined
const asN = (v: D) => (typeof v === 'number' ? v : toN(v))
export const fd = (v: D) => {
  const n = asN(v)
  if (n == null) return ''
  const d = dObj(n)
  return d.getUTCDate() + ' ' + MES[d.getUTCMonth()]
}
export const fdy = (v: D) => {
  const n = asN(v)
  if (n == null) return ''
  const d = dObj(n)
  return d.getUTCDate() + ' ' + MES[d.getUTCMonth()] + ' ' + d.getUTCFullYear()
}

/** Today in Guatemala (UTC-6, no DST) as YYYY-MM-DD, independent of the browser's time zone. */
export const todayISO = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Guatemala' })
export const todayN = () => toN(todayISO())!
export const rangeText = (a?: string, b?: string) => (!a ? '' : a === b ? fdy(a) : `${fd(a)} – ${fdy(b)}`)
