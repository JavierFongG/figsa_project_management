import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd, fdy } from '../lib/dates'
import { Empty, Head, Kpis, Loading, Pill, Prio, Tag } from '../components/ui'
import { ActivityDrawer, ProjectDrawer } from '../components/drawers'
import { Link } from 'react-router-dom'

export default function Portfolio() {
  const { canWrite } = useAuth()
  const pf = useQuery({ queryKey: ['portfolio'], queryFn: () => get('/dashboard/portfolio') })
  const pr = useQuery({ queryKey: ['priorities'], queryFn: () => get<any[]>('/priorities', { limit: 8 }) })
  const rk = useQuery({ queryKey: ['risks'], queryFn: () => get<any[]>('/risks') })
  const [proj, setProj] = useState<any | 'new' | null>(null)
  const [act, setAct] = useState<any | null>(null)

  if (pf.isLoading) return <Loading />
  if (pf.error) return <Empty>{(pf.error as Error).message}</Empty>
  const d = pf.data
  const k = d.kpis

  return (
    <>
      <Head title="Portafolio" sub="Estado de todos los proyectos. Las fechas, estados y prioridades se calculan en el servidor.">
        {canWrite && <button className="btn pri" onClick={() => setProj('new')}>+ Proyecto</button>}
      </Head>
      <Kpis items={[
        { n: k.projects, l: 'Proyectos' }, { n: k.open_activities, l: 'Actividades abiertas' },
        { n: k.late, l: 'Atrasadas', tone: k.late ? 'bad' : undefined }, { n: k.blocked, l: 'Bloqueadas', tone: k.blocked ? 'bad' : undefined },
        { n: k.purchases_unreceived, l: 'Compras sin recibir' }, { n: k.externals_open, l: 'Pendientes externos', tone: k.externals_open ? 'warn' : undefined },
        { n: k.undated, l: 'Sin fecha', tone: k.undated ? 'warn' : undefined },
      ]} />

      <div className="grid g3">
        {d.projects.map((p: any) => {
          const pct = p.total_activities ? Math.round((p.done_activities / p.total_activities) * 100) : 0
          return (
            <article className="pc" key={p.id}>
              <div className="pc-h">
                <div className="r"><span className="code">{p.id}</span><Prio v={p.priority} /><Pill tone={p.health}>{p.status}</Pill></div>
                <h3>{p.name}</h3>
                <span className="muted">{[p.client, p.location].filter(Boolean).join(' · ')}</span>
              </div>
              <div className="pc-b">
                <div className="prog" title={`${pct}%`}><i style={{ width: pct + '%' }} /></div>
                <div className="kv">
                  <div><b>{p.done_activities}/{p.total_activities}</b><span>Actividades</span></div>
                  <div className={p.critical_count ? 'bad' : ''}><b>{p.critical_count}</b><span>Críticas</span></div>
                  <div><b>{p.pending_purchases}</b><span>Compras pend.</span></div>
                  <div className={p.blocking_externals ? 'bad' : ''}><b>{p.blocking_externals}</b><span>Externos</span></div>
                </div>
                {p.next_milestone && <div className="line"><span>Próximo hito</span><span>{p.next_milestone.description}{p.next_milestone.date ? ` · ${fd(p.next_milestone.date)}` : ''}</span></div>}
                {p.blocked_by.length > 0 && <div className="line"><span>Esperando a</span><span>{p.blocked_by.join(', ')}</span></div>}
                {p.next_step && <div className="line"><span>Siguiente paso</span><span><b>{p.next_step.id}</b> {p.next_step.description}</span></div>}
              </div>
              <div className="pc-f">
                <Link className="btn sm" to={`/tareas?project=${p.id}`}>Tareas</Link>
                <Link className="btn sm" to={`/cronograma?project=${p.id}`}>Cronograma</Link>
                <button className="btn sm" onClick={() => setProj(p)}>{canWrite ? 'Editar' : 'Ver'}</button>
              </div>
            </article>
          )
        })}
      </div>

      <div className="grid g2">
        <section className="panel">
          <h3>Prioridades <small>qué atacar primero</small></h3>
          {pr.data?.length ? (
            <div className="list">
              {pr.data.map((x, i) => (
                <div className="li" key={x.activity_id}>
                  <span className="rank">{i + 1}</span>
                  <div>
                    <div className="t"><span className="code">{x.activity_id}</span> {x.activity.description}</div>
                    <div className="s">{x.activity.sched ? `${fd(x.activity.sched.start)} → ${fd(x.activity.sched.end)}` : 'Sin fecha'}</div>
                    <div>{x.tags.map((t: any) => <Tag key={t.text} kind={t.tone === 'bad' ? 'r' : t.tone === 'warn' ? 'a' : undefined}>{t.text}</Tag>)}</div>
                  </div>
                  <button className="btn sm" onClick={() => setAct(x.activity)}>Abrir</button>
                </div>
              ))}
            </div>
          ) : <Empty>No hay actividades accionables.</Empty>}
        </section>
        <section className="panel">
          <h3>Riesgos y alertas <small>{rk.data?.length ?? 0}</small></h3>
          {rk.data?.length ? rk.data.slice(0, 14).map((r, i) => (
            <div key={i} className={`alert ${r.severity}`}><i /><div><b>{r.title}</b><div className="muted">{r.detail}</div></div></div>
          )) : <Empty>Sin alertas.</Empty>}
        </section>
      </div>
      <div className="muted mono">Datos al {fdy(d.today)}</div>

      {proj && <ProjectDrawer project={proj === 'new' ? undefined : proj} onClose={() => setProj(null)} />}
      {act && <ActivityDrawer activity={act} onClose={() => setAct(null)} />}
    </>
  )
}
