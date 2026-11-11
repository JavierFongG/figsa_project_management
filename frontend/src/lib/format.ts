export const money = (v: number | string | null | undefined, cur: string = 'GTQ') => {
  if (v == null || v === '') return null
  const n = Number(v)
  if (Number.isNaN(n)) return null
  return (cur === 'USD' ? 'US$ ' : 'Q ') + n.toLocaleString('es-GT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
export const q = (v: number | string | null | undefined) => money(v ?? 0, 'GTQ')!
export const pct = (v: number | null | undefined) => (v == null ? '—' : (v < 10 ? v.toFixed(1) : Math.round(v)) + '%')
export const nat = (a: string, b: string) => a.localeCompare(b, 'es', { numeric: true })
export const num = (v: any): number | null => (v === '' || v == null || Number.isNaN(Number(v)) ? null : Number(v))
export const clsx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(' ')
