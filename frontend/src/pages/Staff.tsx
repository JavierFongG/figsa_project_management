import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EntityDrawer from '../components/EntityDrawer'
import { Empty, Head, Kpis, Loading, Pill, useProjects } from '../components/ui'
import { del, get, patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { DIAS, dow, fd, todayN, toN } from '../lib/dates'
import { ROLES, lab } from '../lib/labels'

export default function Staff() {
  const { canWrite } = useAuth()
  const { data: ps = [] } = useProjects()
  const workers = useQuery({ queryKey: ['workers'], queryFn: () => get<any[]>('/workers') })
  const assigns = useQuery({ queryKey: ['assignments'], queryFn: () => get<any[]>('/assignments') })
  const needs = useQuery({ queryKey: ['needs'], queryFn: () => get('/staffing/needs') })
  const [w, setW] = useState<any | 'new' | null>(null)
  const [a, setA] = useState<any | 'new' | null>(null)
  const pn = (id: string) => ps.find((p) => p.id === id)?.short_name || id
  const wn = (id: string) => workers.data?.find((x) => x.id === id)?.name ?? '—'

  const t0 = todayN()
  const days = Array.from({ length: 21 }, (_, i) => t0 + i)

  return (
    <>
      <Head title="Personal" sub="Quién está dónde. Una persona no puede estar en dos proyectos el mismo día: el sistema lo rechaza.">
        {canWrite && <button className="btn" onClick={() => setW('new')}>+ Persona</button>}
        {canWrite && <button className="btn pri" onClick={() => setA('new')}>+ Asignación</button>}
      </Head>
      {needs.data && (
        <>
          <Kpis items={[
            { n: needs.data.capacity.technicians, l: 'Técnicos activos' }, { n: needs.data.capacity.helpers, l: 'Ayudantes activos' },
            { n: needs.data.if_all_overlap.technicians + ' / ' + needs.data.if_all_overlap.helpers, l: 'Necesarios si todo coincide (téc./ayud.)' },
            ...(needs.data.peak ? [{ n: `${needs.data.peak.technicians} / ${needs.data.peak.helpers}`, l: `Pico el ${fd(needs.data.peak.day)}`, tone: 'warn' as const }] : []),
          ]} />
          <div className="grid g3">
            {needs.data.projects.map((n: any) => (
              <article className="req" key={n.project_id}>
                <div style={{ display: 'flex', gap: 8 }}><b>{pn(n.project_id)}</b>{n.missing > 0 ? <Pill tone="bad">Faltan {n.missing}</Pill> : <Pill tone="ok">Cubierto</Pill>}</div>
                <div className="muted">{n.window ? `Ventana ${fd(n.window.start)} → ${fd(n.window.end)} (${n.activity_id})` : 'Sin ventana definida'}</div>
                <div>Técnicos {n.assigned_technicians}/{n.required_technicians} · Ayudantes {n.assigned_helpers}/{n.required_helpers}</div>
              </article>
            ))}
          </div>
        </>
      )}
      <section className="panel"><h3>Calendario <small>próximos 21 días</small></h3>
        {workers.isLoading || assigns.isLoading ? <Loading /> : (
          <div className="tw"><table className="mx">
            <thead><tr><th className="nm">Persona</th>{days.map((n) => <th key={n} className={`dd ${[0, 6].includes(dow(n)) ? 'we' : ''}`}>{DIAS[dow(n)]}<br />{fd(n).split(' ')[0]}</th>)}</tr></thead>
            <tbody>{workers.data!.filter((x) => x.active).map((x) => (
              <tr key={x.id}><td className="nm">{x.name} <span className="muted">· {lab(ROLES, x.role)}</span></td>
                {days.map((n) => {
                  const as = assigns.data!.find((g) => g.worker_id === x.id && toN(g.start_date)! <= n && (toN(g.end_date ?? g.start_date)!) >= n)
                  return <td key={n} className={`c ${as ? 'on' : ''} ${n === t0 ? 't' : ''}`} title={as ? `${pn(as.project_id)}` : ''} onClick={() => as && setA(as)}>{as ? pn(as.project_id).slice(0, 4) : ''}</td>
                })}</tr>))}</tbody>
          </table></div>
        )}
      </section>
      <div className="grid g2">
        <section className="panel"><h3>Personas</h3>
          {!workers.data?.length ? <Empty>Aún no hay personal.</Empty> : (
            <div className="tw"><table><thead><tr><th>Nombre</th><th>Rol</th><th>Teléfono</th><th /></tr></thead>
              <tbody>{workers.data.map((x) => <tr key={x.id} className="click" onClick={() => setW(x)}><td>{x.name}</td><td>{lab(ROLES, x.role)}</td><td>{x.phone ?? ''}</td><td>{!x.active && <Pill tone="idle">Inactivo</Pill>}</td></tr>)}</tbody></table></div>
          )}
        </section>
        <section className="panel"><h3>Asignaciones</h3>
          {!assigns.data?.length ? <Empty>Sin asignaciones.</Empty> : (
            <div className="tw"><table><thead><tr><th>Persona</th><th>Proyecto</th><th>Desde</th><th>Hasta</th></tr></thead>
              <tbody>{assigns.data.map((g) => <tr key={g.id} className="click" onClick={() => setA(g)}><td>{wn(g.worker_id)}</td><td className="code">{pn(g.project_id)}</td><td className="mono">{fd(g.start_date)}</td><td className="mono">{g.end_date ? fd(g.end_date) : '—'}</td></tr>)}</tbody></table></div>
          )}
        </section>
      </div>
      {w && (
        <EntityDrawer title={w === 'new' ? 'Nueva persona' : w.name} creating={w === 'new'} initial={w === 'new' ? { role: 'tecnico', active: true } : w} onClose={() => setW(null)}
          fields={[
            { name: 'name', label: 'Nombre', required: true },
            { name: 'role', label: 'Rol', type: 'select', options: ROLES, half: true },
            { name: 'phone', label: 'Teléfono', half: true },
            { name: 'specialty', label: 'Especialidad' },
            { name: 'active', label: 'Activo', type: 'check' },
            { name: 'notes', label: 'Notas', type: 'textarea' },
          ]}
          onSave={(b) => (w === 'new' ? post('/workers', b) : patch(`/workers/${w.id}`, b))}
          onDelete={w === 'new' ? undefined : () => del(`/workers/${w.id}`)} />
      )}
      {a && (
        <EntityDrawer title={a === 'new' ? 'Nueva asignación' : `${wn(a.worker_id)} · ${pn(a.project_id)}`} creating={a === 'new'} initial={a === 'new' ? {} : a} onClose={() => setA(null)}
          fields={[
            { name: 'worker_id', label: 'Persona', type: 'select', required: true, options: (workers.data ?? []).filter((x) => x.active || x.id === a.worker_id).map((x) => [x.id, x.name]) },
            { name: 'project_id', label: 'Proyecto', type: 'select', required: true, options: ps.map((p) => [p.id, p.name]) },
            { name: 'start_date', label: 'Desde', type: 'date', required: true, half: true },
            { name: 'end_date', label: 'Hasta', type: 'date', half: true, hint: 'Vacío = un solo día' },
            { name: 'activity_id', label: 'Actividad (opcional)', upper: true },
            { name: 'notes', label: 'Notas', type: 'textarea' },
          ]}
          onSave={(b) => (a === 'new' ? post('/assignments', b) : patch(`/assignments/${a.id}`, b))}
          onDelete={a === 'new' ? undefined : () => del(`/assignments/${a.id}`)} />
      )}
    </>
  )
}
