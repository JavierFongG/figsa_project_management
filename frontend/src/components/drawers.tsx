import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EntityDrawer, { type Field } from './EntityDrawer'
import { History, Pill, useAct, useProjects } from './ui'
import { del, get, patch, post, upload } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fdy } from '../lib/dates'
import * as L from '../lib/labels'

const projOpts = (ps: any[]): L.Opt[] => ps.map((p) => [p.id, `${p.short_name || p.id} · ${p.name}`])

// ------------------------------------------------------------------ project
export function ProjectDrawer({ project, onClose }: { project?: any; onClose: () => void }) {
  const creating = !project
  const f: Field[] = [
    { name: 'id', label: 'Código', required: true, upper: true, readOnlyOnEdit: true, half: true, hint: 'Letras, números y guiones' },
    { name: 'short_name', label: 'Nombre corto', half: true },
    { name: 'name', label: 'Nombre', required: true },
    { name: 'client', label: 'Cliente', half: true },
    { name: 'location', label: 'Ubicación', half: true },
    { name: 'scope', label: 'Alcance', type: 'textarea' },
    { name: 'status', label: 'Estado', type: 'select', options: L.EST_PROY.map((x) => [x, x]), half: true },
    { name: 'priority', label: 'Prioridad', type: 'select', options: L.PRIOS.map((x) => [x, x]), half: true },
    { name: 'progress_pct', label: 'Avance (%)', type: 'number', half: true },
    { name: 'sort_order', label: 'Orden', type: 'number', half: true },
    { name: 'scenario_start', label: 'Inicio del escenario', type: 'date', half: true, hint: 'Desde aquí se proyectan las actividades sin fecha' },
    { name: 'exchange_rate', label: 'Tipo de cambio US$→Q', type: 'number', half: true },
    { name: 'req_technicians', label: 'Técnicos requeridos', type: 'number', half: true },
    { name: 'req_helpers', label: 'Ayudantes requeridos', type: 'number', half: true },
    { name: 'staffing_activity_id', label: 'Actividad que define la ventana de personal', upper: true },
    { name: 'drive_invoices_folder', label: 'Carpeta de Drive · facturas', hint: 'Enlace o ID de la carpeta' },
    { name: 'drive_receipts_folder', label: 'Carpeta de Drive · comprobantes' },
    { name: 'notes', label: 'Notas', type: 'textarea' },
  ]
  return (
    <EntityDrawer
      title={creating ? 'Nuevo proyecto' : `Proyecto ${project.id}`}
      fields={f} initial={project ?? { status: 'Planificación', priority: 'Media', sort_order: 0 }} creating={creating} onClose={onClose}
      onSave={(b) => (creating ? post('/projects', b) : patch(`/projects/${project.id}`, b, project.updated_at))}
    >
      {!creating && <History entity="project" id={project.id} />}
    </EntityDrawer>
  )
}

// ------------------------------------------------------------------ activity
export function ActivityDrawer({ activity, projectId, onClose }: { activity?: any; projectId?: string; onClose: () => void }) {
  const creating = !activity
  const { data: ps = [] } = useProjects()
  const { data: full } = useQuery({ queryKey: ['activity', activity?.id], queryFn: () => get(`/activities/${activity.id}`), enabled: !creating })
  const a = full ?? activity
  const f: Field[] = [
    { name: 'id', label: 'Código', required: true, upper: true, readOnlyOnEdit: true, half: true },
    { name: 'project_id', label: 'Proyecto', type: 'select', options: projOpts(ps), required: true, readOnlyOnEdit: true, half: true },
    { name: 'description', label: 'Descripción', required: true },
    { name: 'type', label: 'Tipo', type: 'select', options: L.TIPOS, half: true },
    { name: 'front', nullable: true, label: 'Frente', type: 'select', options: L.FRENTES, half: true },
    { name: 'owner', label: 'Responsable', half: true },
    { name: 'status', label: 'Estado', type: 'select', options: L.EST_ACT, half: true },
    { name: 'date_confidence', label: 'Confianza de la fecha', type: 'select', options: L.CONF, half: true },
    { name: 'duration_days', label: 'Duración (días)', type: 'number', half: true },
    { name: 'start_date', label: 'Inicio', type: 'date', half: true },
    { name: 'end_date', label: 'Fin', type: 'date', half: true, hint: 'Si lo dejas vacío se calcula con la duración' },
    { name: 'dependencies', label: 'Depende de (códigos separados por coma)', type: 'codes' },
    { name: 'next_action', label: 'Siguiente acción' },
    { name: 'remarks', label: 'Observaciones', type: 'textarea' },
    { name: 'generates_income', label: 'Genera ingreso', type: 'check' },
  ]
  const initial = creating ? { project_id: projectId ?? '', type: 'ejecucion', status: 'pendiente', date_confidence: 'pendiente', dependencies: [] } : a
  return (
    <EntityDrawer
      key={a?.updated_at ?? 'new'}
      title={creating ? 'Nueva actividad' : `${a.id} · ${a.status_info?.label ?? ''}`}
      fields={f} initial={initial} creating={creating} onClose={onClose}
      onSave={(b) => (creating ? post('/activities', b) : patch(`/activities/${a.id}`, b, a.updated_at))}
      onDelete={creating ? undefined : () => del(`/activities/${a.id}`)}
    >
      {!creating && a && <ActivityExtras a={a} />}
    </EntityDrawer>
  )
}

function ActivityExtras({ a }: { a: any }) {
  const { canWrite } = useAuth()
  const act = useAct()
  const [note, setNote] = useState('')
  return (
    <>
      {a.violation && <div className="ferr">La fecha empieza antes de que termine su predecesora {a.violation}.</div>}
      {a.blocked_by?.length > 0 && <div className="ferr">Bloqueada por: {a.blocked_by.map((x: any) => `${x.counterparty} (${x.subject})`).join(' · ')}</div>}
      {a.sched && <div className="muted">Fechas calculadas: {fdy(a.sched.start)} → {fdy(a.sched.end)} {a.sched.kind === 'esc' && <Pill tone="esc">Proyectada</Pill>}</div>}
      <div className="chips">
        {canWrite && a.status !== 'completada' && <button className="btn" onClick={() => act(() => post(`/activities/${a.id}/complete`), 'Completada')}>✓ Marcar completada</button>}
        {canWrite && a.status === 'completada' && <button className="btn" onClick={() => act(() => post(`/activities/${a.id}/reopen`), 'Reabierta')}>Reabrir</button>}
      </div>
      <div className="fld">
        <label>Avances</label>
        {canWrite && (
          <div className="tk" style={{ padding: 0, border: 0, display: 'block' }}>
            <div className="note">
              <input value={note} placeholder="Qué se hizo / qué sigue" onChange={(e) => setNote(e.target.value)} />
              <button className="btn" disabled={!note.trim()} onClick={async () => { await act(() => post(`/activities/${a.id}/notes`, { body: note.trim() }), 'Avance guardado'); setNote('') }}>Agregar</button>
            </div>
          </div>
        )}
        {(a.notes ?? []).map((n: any) => (
          <div key={n.id} className="last"><span>{new Date(n.created_at).toLocaleDateString('es-GT', { day: 'numeric', month: 'short' })}</span>{n.body}</div>
        ))}
      </div>
      <History entity="activity" id={a.id} />
    </>
  )
}

// ------------------------------------------------------------------ purchase
export function PurchaseDrawer({ purchase, projectId, onClose }: { purchase?: any; projectId?: string; onClose: () => void }) {
  const creating = !purchase
  const { data: ps = [] } = useProjects()
  const [pid, setPid] = useState<string>(purchase?.project_id ?? projectId ?? '')
  const { data: lines = [] } = useQuery({ queryKey: ['lines', pid], queryFn: () => get<any[]>(`/projects/${pid}/budget-lines`), enabled: !!pid })
  const f: Field[] = [
    { name: 'project_id', label: 'Proyecto', type: 'select', options: projOpts(ps), required: true, half: true },
    { name: 'product', label: 'Producto o servicio', required: true, half: true },
    { name: 'status', label: 'Estado', type: 'select', options: L.EST_COMP, half: true },
    { name: 'supplier', label: 'Proveedor', half: true },
    { name: 'currency', label: 'Moneda', type: 'select', options: L.MONEDAS, half: true },
    { name: 'total_amount', label: 'Monto total', type: 'number', half: true },
    { name: 'advance_required', label: 'Anticipo requerido', type: 'number', half: true },
    { name: 'advance_paid', label: 'Anticipo pagado', type: 'number', half: true },
    { name: 'invoice_mode', nullable: true, label: 'Facturación', type: 'select', options: L.FACT, half: true },
    { name: 'invoice_no', label: 'No. de factura', half: true },
    { name: 'needed_by', label: 'Se necesita para', type: 'date', half: true },
    { name: 'ordered_on', label: 'Fecha de pedido', type: 'date', half: true },
    { name: 'lead_time_days', label: 'Tiempo de entrega (días)', type: 'number', half: true },
    { name: 'received_on', label: 'Fecha de recepción', type: 'date', half: true },
    { name: 'budget_line_id', nullable: true, label: 'Rubro del presupuesto', type: 'select', options: lines.map((l) => [l.id, `${l.code} · ${l.material || l.activity || ''}`] as L.Opt) },
    { name: 'activity_id', label: 'Actividad relacionada', upper: true },
    { name: 'notes', label: 'Notas', type: 'textarea' },
  ]
  return (
    <EntityDrawer
      key={purchase?.updated_at ?? 'new'}
      title={creating ? 'Nueva compra' : purchase.product}
      fields={f} initial={purchase ?? { project_id: projectId ?? '', status: 'cotizacion', currency: 'GTQ' }} creating={creating} onClose={onClose}
      onSave={(b) => { if (b.project_id) setPid(b.project_id); return creating ? post('/purchases', b) : patch(`/purchases/${purchase.id}`, b, purchase.updated_at) }}
      onDelete={creating ? undefined : () => del(`/purchases/${purchase.id}`)}
    >
      {!creating && <PurchaseFiles purchase={purchase} />}
      {!creating && <History entity="purchase" id={purchase.id} />}
    </EntityDrawer>
  )
}

function PurchaseFiles({ purchase }: { purchase: any }) {
  const { canWrite } = useAuth()
  const act = useAct()
  const [files, setFiles] = useState<Record<string, any>>(purchase.files ?? {})
  const slot = (kind: 'factura' | 'comprobante', label: string) => {
    const cur = files[kind]
    return (
      <div className={`fdz ${cur ? 'has' : ''}`} key={kind}>
        <span className="fdz-k">{label}</span>
        {cur ? <a href={cur.url} target="_blank" rel="noreferrer">{cur.filename}</a> : <span className="muted">Sin archivo</span>}
        {canWrite && (
          <div className="chips">
            <label className="btn sm">
              {cur ? 'Reemplazar' : 'Subir a Drive'}
              <input type="file" hidden onChange={async (e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (!file) return
                const r = await act(() => upload(`/purchases/${purchase.id}/files`, file, { kind }), 'Archivo subido a Drive')
                if (r) setFiles((s) => ({ ...s, [kind]: r }))
              }} />
            </label>
            {cur && <button className="btn sm danger" onClick={async () => { const ok = await act(async () => { await del(`/purchases/${purchase.id}/files/${kind}`); return true }, 'Archivo quitado'); if (ok) setFiles((s) => { const n = { ...s }; delete n[kind]; return n }) }}>Quitar</button>}
          </div>
        )}
      </div>
    )
  }
  return <div style={{ display: 'grid', gap: 8 }}>{slot('factura', 'Factura')}{slot('comprobante', 'Comprobante de pago')}</div>
}

// ------------------------------------------------------------------ budget line
export function BudgetLineDrawer({ line, projectId, onClose }: { line?: any; projectId: string; onClose: () => void }) {
  const creating = !line
  const f: Field[] = [
    { name: 'code', label: 'Código', required: true, half: true },
    { name: 'phase', label: 'Fase', half: true },
    { name: 'activity', label: 'Actividad' },
    { name: 'material', label: 'Material / servicio' },
    { name: 'specification', label: 'Especificación' },
    { name: 'quantity', label: 'Cantidad', type: 'number', half: true },
    { name: 'unit', label: 'Unidad', half: true },
    { name: 'unit_price', label: 'Precio unitario (Q)', type: 'number', half: true },
    { name: 'total', label: 'Total (Q)', type: 'number', half: true, hint: 'Si queda vacío se calcula cantidad × precio' },
    { name: 'planned_start', label: 'Inicio previsto', type: 'date', half: true },
    { name: 'planned_end', label: 'Fin previsto', type: 'date', half: true },
    { name: 'remarks', label: 'Observaciones', type: 'textarea' },
  ]
  return (
    <EntityDrawer
      key={line?.updated_at ?? 'new'}
      title={creating ? 'Nueva línea de presupuesto' : `Línea ${line.code}`}
      fields={f} initial={line ?? { phase: 'Otros' }} creating={creating} onClose={onClose}
      onSave={(b) => (creating ? post(`/projects/${projectId}/budget-lines`, b) : patch(`/budget-lines/${line.id}`, b, line.updated_at))}
      onDelete={creating ? undefined : () => del(`/budget-lines/${line.id}`)}
    />
  )
}
