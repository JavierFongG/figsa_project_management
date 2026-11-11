import { useEffect, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get } from '../lib/api'
import { clsx } from '../lib/format'
import { FRENTES, lab } from '../lib/labels'

// ---- toast (global, event based so any module can call it)
export const toast = (msg: string, err = false) => window.dispatchEvent(new CustomEvent('figsa:toast', { detail: { msg, err } }))
export function Toast() {
  const [t, setT] = useState<{ msg: string; err: boolean } | null>(null)
  useEffect(() => {
    let id: any
    const h = (e: any) => { setT(e.detail); clearTimeout(id); id = setTimeout(() => setT(null), 4200) }
    window.addEventListener('figsa:toast', h)
    return () => { window.removeEventListener('figsa:toast', h); clearTimeout(id) }
  }, [])
  return t ? <div id="toast" className={t.err ? 'err' : ''} role="status">{t.msg}</div> : null
}

export const errText = (e: unknown) => (e instanceof Error ? e.message : String(e))

/** Run an action, show success/error toast, then refresh every query. */
export function useAct() {
  const qc = useQueryClient()
  return async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
    try {
      const r = await fn()
      await qc.invalidateQueries()
      if (ok) toast(ok)
      return r
    } catch (e) {
      toast(errText(e), true)
      return undefined
    }
  }
}

// ---- small pieces
export const Pill = ({ tone, children }: { tone: string; children: ReactNode }) => <span className={`pill s-${tone}`}>{children}</span>
export const Tag = ({ children, kind }: { children: ReactNode; kind?: 'a' | 'r' }) => <span className={clsx('tag', kind)}>{children}</span>
export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>
export const Loading = () => <div className="empty">Cargando…</div>
export const Prio = ({ v }: { v?: string | null }) => (v ? <span className={`prio prio-${v}`}>{v}</span> : null)
export const FrontTag = ({ f }: { f?: string | null }) => (f ? <span className="frtag"><i className={`fdot f-${f}`} />{lab(FRENTES, f)}</span> : null)

export const Check = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8.5l3.2 3.2L13 4.8" /></svg>
)

export function Head({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="head">
      <div><h2>{title}</h2>{sub && <p>{sub}</p>}</div>
      {children && <div className="act">{children}</div>}
    </div>
  )
}

export function Chips({ value, onChange, items }: { value: string; onChange: (v: string) => void; items: { v: string; l: string; c?: number }[] }) {
  return (
    <div className="chips">
      {items.map((i) => (
        <button key={i.v} className="chip" aria-pressed={value === i.v} onClick={() => onChange(i.v)}>
          {i.l}{i.c != null && <span className="c">{i.c}</span>}
        </button>
      ))}
    </div>
  )
}

export function Kpis({ items }: { items: { n: ReactNode; l: string; tone?: 'bad' | 'warn' }[] }) {
  return <div className="kpis">{items.map((k) => <div key={k.l} className={clsx('kpi', k.tone)}><b>{k.n}</b><span>{k.l}</span></div>)}</div>
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>
}

export function CopyBox({ text, rows }: { text: string; rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <textarea className="rep" readOnly value={text} rows={rows} />
      <div><button className="btn" onClick={() => navigator.clipboard.writeText(text).then(() => toast('Copiado al portapapeles'), () => toast('No se pudo copiar', true))}>Copiar texto</button></div>
    </div>
  )
}

// ---- shared lookups
export const useProjects = () => useQuery({ queryKey: ['projects'], queryFn: () => get<any[]>('/projects') })
export function ProjectSelect({ value, onChange, all = true }: { value: string; onChange: (v: string) => void; all?: boolean }) {
  const { data = [] } = useProjects()
  return (
    <select className="search" style={{ maxWidth: 240 }} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Proyecto">
      {all && <option value="">Todos los proyectos</option>}
      {data.map((p) => <option key={p.id} value={p.id}>{p.short_name || p.id} · {p.name}</option>)}
    </select>
  )
}

// ---- history (audit log) shown inside drawers
export function History({ entity, id }: { entity: string; id: string }) {
  const { data = [] } = useQuery({ queryKey: ['audit', entity, id], queryFn: () => get<any[]>('/audit', { entity, entity_id: id, limit: 30 }) })
  if (!data.length) return null
  return (
    <div className="hist">
      <h3>Historial</h3>
      {data.map((h) => (
        <div key={h.id}>
          <span className="mono muted">{new Date(h.ts).toLocaleDateString('es-GT', { day: 'numeric', month: 'short' })}</span>
          <span>{h.field}{h.before_value || h.after_value ? <>: <span className="muted">{h.before_value ?? '—'}</span> → {h.after_value ?? '—'}</> : ''}</span>
        </div>
      ))}
    </div>
  )
}
