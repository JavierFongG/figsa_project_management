import { useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '../lib/auth'
import type { Opt } from '../lib/labels'
import { useAct } from './ui'

export type Field = {
  name: string
  label: string
  type?: 'text' | 'textarea' | 'number' | 'date' | 'select' | 'check' | 'codes'
  options?: Opt[]
  hint?: string
  required?: boolean
  readOnlyOnEdit?: boolean
  upper?: boolean
  half?: boolean
  nullable?: boolean
}

const toForm = (fields: Field[], init: any) => {
  const o: Record<string, any> = {}
  for (const f of fields) {
    const v = init?.[f.name]
    if (f.type === 'check') o[f.name] = !!v
    else if (f.type === 'codes') o[f.name] = (v || []).join(', ')
    else o[f.name] = v ?? ''
  }
  return o
}

const toBody = (fields: Field[], form: Record<string, any>, creating: boolean) => {
  const out: Record<string, any> = {}
  for (const f of fields) {
    if (f.readOnlyOnEdit && !creating) continue
    const v = form[f.name]
    if (f.type === 'check') out[f.name] = !!v
    else if (f.type === 'codes') out[f.name] = String(v).split(/[,\s]+/).map((x) => x.trim().toUpperCase()).filter(Boolean)
    else {
      const empty = v === '' || v == null || (typeof v === 'string' && v.trim() === '')
      // On create, empty means "use the server default". Selects without "—" are never cleared.
      if (empty && (creating || (f.type === 'select' && !f.nullable))) continue
      if (empty) out[f.name] = null
      else out[f.name] = f.type === 'number' ? Number(v) : typeof v === 'string' ? v.trim() : v
    }
  }
  return out
}

type Props = {
  title: string
  fields: Field[]
  initial?: any
  creating?: boolean
  onClose: () => void
  /** receives the request body; return the saved row or throw */
  onSave: (body: Record<string, any>) => Promise<any>
  onDelete?: () => Promise<any>
  deleteLabel?: string
  children?: ReactNode
  footerExtra?: ReactNode
}

export default function EntityDrawer({ title, fields, initial, creating, onClose, onSave, onDelete, deleteLabel = 'Eliminar', children, footerExtra }: Props) {
  const { canWrite } = useAuth()
  const act = useAct()
  const [form, setForm] = useState(() => toForm(fields, initial))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  const set = (n: string, v: any) => setForm((f) => ({ ...f, [n]: v }))

  const save = async () => {
    setErr('')
    const missing = fields.filter((f) => f.required && (form[f.name] === '' || form[f.name] == null))
    if (missing.length) return setErr('Falta: ' + missing.map((m) => m.label).join(', '))
    setBusy(true)
    const r = await act(() => onSave(toBody(fields, form, !!creating)).catch((e) => { setErr(e.message); throw e }), creating ? 'Creado' : 'Guardado')
    setBusy(false)
    if (r !== undefined) onClose()
  }

  const remove = async () => {
    setBusy(true)
    const r = await act(async () => { await onDelete!(); return true }, 'Eliminado')
    setBusy(false)
    if (r) onClose()
  }

  const disabled = !canWrite

  const render = (f: Field) => {
    const id = 'f-' + f.name
    const ro = disabled || (f.readOnlyOnEdit && !creating)
    let input: ReactNode
    if (f.type === 'textarea') input = <textarea id={id} disabled={ro} value={form[f.name]} onChange={(e) => set(f.name, e.target.value)} />
    else if (f.type === 'select')
      input = (
        <select id={id} disabled={ro} value={form[f.name]} onChange={(e) => set(f.name, e.target.value)}>
          {(f.nullable || creating) && <option value="">—</option>}
          {f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      )
    else if (f.type === 'check')
      return (
        <div className="fld" key={f.name}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--ink)' }}>
            <input type="checkbox" style={{ width: 'auto' }} disabled={ro} checked={form[f.name]} onChange={(e) => set(f.name, e.target.checked)} /> {f.label}
          </label>
          {f.hint && <span className="hint">{f.hint}</span>}
        </div>
      )
    else
      input = (
        <input
          id={id}
          disabled={ro}
          type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
          step={f.type === 'number' ? 'any' : undefined}
          value={form[f.name]}
          onChange={(e) => set(f.name, f.upper ? e.target.value.toUpperCase() : e.target.value)}
        />
      )
    return (
      <div className="fld" key={f.name}>
        <label htmlFor={id}>{f.label}{f.required ? ' *' : ''}</label>
        {input}
        {f.hint && <span className="hint">{f.hint}</span>}
      </div>
    )
  }

  // pair consecutive "half" fields on one row
  const rows: ReactNode[] = []
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].half && fields[i + 1]?.half) {
      rows.push(<div className="frow" key={fields[i].name}>{render(fields[i])}{render(fields[i + 1])}</div>)
      i++
    } else rows.push(render(fields[i]))
  }

  return (
    <>
      <div id="scrim" onClick={onClose} />
      <aside id="drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="dh"><h3>{title}</h3><button className="btn sm" onClick={onClose} aria-label="Cerrar">✕</button></div>
        <div className="db">
          {!canWrite && <div className="notice">Tu usuario es de solo lectura.</div>}
          {rows}
          {children}
          {err && <div className="ferr" role="alert">{err}</div>}
        </div>
        <div className="df">
          {canWrite && onDelete && !creating && (confirm ? (
            <div className="confirm">¿Seguro?<button className="btn danger sm" disabled={busy} onClick={remove}>Sí, {deleteLabel.toLowerCase()}</button><button className="btn sm" onClick={() => setConfirm(false)}>No</button></div>
          ) : <button className="btn danger" onClick={() => setConfirm(true)}>{deleteLabel}</button>)}
          {footerExtra}
          <span className="sp" />
          <button className="btn" onClick={onClose}>{canWrite ? 'Cancelar' : 'Cerrar'}</button>
          {canWrite && <button className="btn pri" disabled={busy} onClick={save}>{busy ? 'Guardando…' : 'Guardar'}</button>}
        </div>
      </aside>
    </>
  )
}
