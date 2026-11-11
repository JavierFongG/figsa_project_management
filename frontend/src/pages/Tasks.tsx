import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { Check, Chips, CopyBox, Empty, FrontTag, Head, Loading, Pill, ProjectSelect, Tag, useAct } from '../components/ui'
import { ActivityDrawer } from '../components/drawers'
import { patch } from '../lib/api'

function Task({ t, onOpen }: { t: any; onOpen: (t: any) => void }) {
  const { canWrite } = useAuth()
  const act = useAct()
  const [note, setNote] = useState('')
  const done = t.status === 'completada'
  const st = t.status_info
  return (
    <div className={`tk ${done ? 'done' : ''}`}>
      <button className="ck" disabled={!canWrite} aria-label={done ? 'Reabrir' : 'Completar'} onClick={() => act(() => post(`/activities/${t.id}/${done ? 'reopen' : 'complete'}`), done ? 'Reabierta' : 'Completada')}><Check /></button>
      <div>
        <div className="tt" onClick={() => onOpen(t)}><span className="code">{t.id}</span> {t.description}</div>
        <div className="meta">
          <Pill tone={st.tone}>{st.label}</Pill>
          <FrontTag f={t.front} />
          {t.sched && <span>{fd(t.sched.start)}{t.sched.end > t.sched.start ? ` → ${fd(t.sched.end)}` : ''}{t.sched.kind === 'esc' ? ' (proyectada)' : ''}</span>}
          {t.owner && <span>· {t.owner}</span>}
          {(t.tags ?? []).map((g: any) => <Tag key={g.text} kind={g.tone === 'bad' ? 'r' : g.tone === 'warn' ? 'a' : undefined}>{g.text}</Tag>)}
          {t.blocked_by?.map((b: any) => <Tag key={b.id} kind="r">Espera: {b.counterparty}</Tag>)}
        </div>
        {t.last_note && <div className="last"><span>{new Date(t.last_note.created_at ?? t.last_note.at ?? Date.now()).toLocaleDateString('es-GT', { day: 'numeric', month: 'short' })}</span>{t.last_note.body}</div>}
        {canWrite && !done && (
          <>
            <div className="ops">
              <label className="muted" style={{ fontSize: 12 }}>Fecha confirmada:&nbsp;
                <input type="date" defaultValue={t.date_confidence === 'confirmada' ? t.start_date ?? '' : ''} onChange={(e) => e.target.value && act(() => patch(`/activities/${t.id}`, { start_date: e.target.value, end_date: null, date_confidence: 'confirmada' }), 'Fecha confirmada')} />
              </label>
              {t.status === 'pendiente' && <button className="btn sm" onClick={() => act(() => patch(`/activities/${t.id}`, { status: 'proceso' }), 'En proceso')}>Iniciar</button>}
            </div>
            <div className="note">
              <input value={note} placeholder="Registrar avance…" onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && note.trim() && act(() => post(`/activities/${t.id}/notes`, { body: note.trim() }), 'Avance guardado').then(() => setNote(''))} />
              <button className="btn sm" disabled={!note.trim()} onClick={() => act(() => post(`/activities/${t.id}/notes`, { body: note.trim() }), 'Avance guardado').then(() => setNote(''))}>Guardar</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function Tasks() {
  const [sp, setSp] = useSearchParams()
  const project = sp.get('project') ?? ''
  const [days, setDays] = useState(7)
  const [front, setFront] = useState('ALL')
  const [open, setOpen] = useState<any | null>(null)
  const [showRep, setShowRep] = useState(false)
  const params = { days, project_id: project, front: project ? front : undefined }
  const q = useQuery({ queryKey: ['tasks', params], queryFn: () => get('/dashboard/my-tasks', params) })
  const rep = useQuery({ queryKey: ['daily', params], queryFn: () => get('/reports/daily', params), enabled: showRep })

  const g = q.data
  const groups: [string, any[], string?][] = g ? [
    ['Atrasado', g.overdue], ['Hoy', g.today_items], [`Próximos ${days} días`, g.upcoming], ['En proceso', g.in_progress],
    ['Listas para atacar (sin fecha)', g.ready], ['Completado recientemente', g.done],
  ] : []

  return (
    <>
      <Head title="Mis tareas" sub="Lo que toca hacer, en orden de urgencia.">
        <ProjectSelect value={project} onChange={(v) => setSp(v ? { project: v } : {})} />
        <button className="btn" onClick={() => setShowRep((s) => !s)}>{showRep ? 'Ocultar resumen' : 'Resumen para compartir'}</button>
      </Head>
      <div className="gctl">
        <Chips value={String(days)} onChange={(v) => setDays(+v)} items={[{ v: '3', l: '3 días' }, { v: '7', l: '7 días' }, { v: '14', l: '14 días' }, { v: '30', l: '30 días' }]} />
        {g?.front_filter_active && <Chips value={front} onChange={setFront} items={[{ v: 'ALL', l: 'Todo' }, { v: 'obra', l: 'Obra' }, { v: 'admin', l: 'Administrativo' }]} />}
      </div>
      {showRep && <section className="panel">{rep.data ? <CopyBox text={rep.data.text} /> : <Loading />}</section>}
      {q.isLoading ? <Loading /> : q.error ? <Empty>{(q.error as Error).message}</Empty> : (
        <section className="panel">
          {groups.map(([title, items]) => items.length > 0 && (
            <div className="tk-g" key={title}>
              <h3>{title} <span className="n">{items.length}</span></h3>
              {items.map((t) => <Task key={t.id} t={t} onOpen={setOpen} />)}
            </div>
          ))}
          {g.externals.length > 0 && (
            <div className="tk-g">
              <h3>Pendiente de terceros <span className="n">{g.externals.length}</span></h3>
              {g.externals.map((x: any) => (
                <div className="tk" key={x.id}><span /><div><div className="tt" style={{ cursor: 'default' }}>{x.counterparty}: {x.subject}</div>
                  <div className="meta"><Pill tone={x.status === 'esperando' ? 'warn' : 'idle'}>{x.status === 'esperando' ? 'Esperando' : 'Por solicitar'}</Pill>
                    {x.waiting_days != null && <span>{x.waiting_days} d</span>}{x.blocks.map((b: string) => <Tag key={b} kind="r">Bloquea {b}</Tag>)}</div></div></div>
              ))}
            </div>
          )}
          {!groups.some((x) => x[1].length) && !g.externals.length && <Empty>Nada pendiente. 🎉</Empty>}
        </section>
      )}
      {open && <ActivityDrawer activity={open} onClose={() => setOpen(null)} />}
    </>
  )
}
