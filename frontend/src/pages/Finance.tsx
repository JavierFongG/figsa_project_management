import { Fragment, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { pct, q as Q } from '../lib/format'
import { BudgetLineDrawer } from '../components/drawers'
import { Check, Empty, Head, Kpis, Loading, Notice, Tag, useAct } from '../components/ui'

export default function Finance() {
  const { canWrite } = useAuth()
  const act = useAct()
  const projects = useQuery({ queryKey: ['fin-projects'], queryFn: () => get<any[]>('/finance/projects') })
  const [pid, setPid] = useState('')
  useEffect(() => { if (!pid && projects.data?.length) setPid(projects.data[0].id) }, [projects.data, pid])
  const fin = useQuery({ queryKey: ['finance', pid], queryFn: () => get(`/projects/${pid}/finance`), enabled: !!pid })
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [edit, setEdit] = useState<any | 'new' | null>(null)

  if (projects.isLoading) return <Loading />
  const d = fin.data
  const t = d?.totals

  return (
    <>
      <Head title="Rendimiento financiero" sub="Presupuesto vs ejecutado por rubro. Ejecutado = compras pagadas + anticipos + viáticos etiquetados.">
        <select className="search" value={pid} onChange={(e) => setPid(e.target.value)} aria-label="Proyecto">
          {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.short_name || p.id} · {p.name}</option>)}
          {!projects.data?.length && <option value="">Sin presupuestos</option>}
        </select>
        {canWrite && pid && <button className="btn pri" onClick={() => setEdit('new')}>+ Línea</button>}
      </Head>
      {!pid ? <Empty>Ningún proyecto tiene presupuesto todavía. Crea la primera línea desde un proyecto.</Empty> : fin.isLoading || !d ? <Loading /> : (
        <>
          <Kpis items={[
            { n: Q(t.budget), l: 'Presupuesto' }, { n: Q(t.executed), l: `Ejecutado (${pct(t.percent)})` },
            { n: Q(t.committed), l: 'Comprometido' }, { n: Q(t.available), l: 'Disponible', tone: t.available < 0 ? 'bad' : undefined },
            { n: Q(t.savings), l: `Ahorro en ${t.completed_lines}/${t.lines} líneas cerradas` },
          ]} />
          {d.usd_purchases > 0 && <Notice>{d.usd_purchases} compra(s) en dólares convertidas a Q a {d.exchange_rate}. Cambia el tipo de cambio en el proyecto.</Notice>}
          {t.unlabeled_count > 0 && <Notice>{t.unlabeled_count} movimiento(s) por {Q(t.unlabeled_amount)} sin rubro asignado — no cuentan en ninguna línea.</Notice>}
          <div className="tw"><table className="ftab">
            <thead><tr><th style={{ width: 40 }} /><th>Código</th><th>Rubro</th><th style={{ textAlign: 'right' }}>Presupuesto</th><th style={{ textAlign: 'right' }}>Ejecutado</th><th style={{ textAlign: 'right' }}>Comprometido</th><th style={{ textAlign: 'right' }}>Disponible</th><th style={{ minWidth: 140 }}>Avance</th></tr></thead>
            <tbody>
              {d.phases.map((ph: any) => (
                <Fragment key={ph.phase}>
                  <tr className="fphase"><td colSpan={3}>{ph.phase}</td><td className="num">{Q(ph.budget)}</td><td className="num">{Q(ph.executed)}</td><td colSpan={3} className="muted">{ph.completed}/{ph.lines} líneas cerradas{ph.completed ? ` · ahorro ${Q(ph.savings)}` : ''}</td></tr>
                  {d.lines.filter((l: any) => (l.phase || 'Otros') === ph.phase).map((l: any) => {
                    const over = l.executed > l.budget
                    return (
                      <Fragment key={l.id}>
                        <tr className={l.completed ? 'done' : ''}>
                          <td><button className={`ckb ${l.completed ? 'on' : ''}`} disabled={!canWrite} aria-label="Cerrar línea" onClick={() => act(() => post(`/budget-lines/${l.id}/${l.completed ? 'reopen' : 'complete'}`), l.completed ? 'Línea reabierta' : 'Línea cerrada')}><Check /></button></td>
                          <td className="code">{l.code}</td>
                          <td style={{ cursor: 'pointer' }} onClick={() => setOpenRow(openRow === l.id ? null : l.id)}>
                            {l.material || l.activity} {l.movement_count > 0 && <Tag>{l.movement_count} mov.</Tag>}{l.review_note && <Tag kind="r">Revisar</Tag>}
                            {canWrite && <button className="btn sm" style={{ marginLeft: 8 }} onClick={(e) => { e.stopPropagation(); setEdit(l) }}>Editar</button>}
                          </td>
                          <td className="num">{Q(l.budget)}</td><td className="num">{Q(l.executed)}</td><td className="num">{l.committed ? Q(l.committed) : ''}</td>
                          <td className="num" style={{ color: l.available < 0 ? 'var(--bad)' : undefined }}>{l.completed && l.savings != null ? `Ahorro ${Q(l.savings)}` : Q(l.available)}</td>
                          <td><div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><div className={`fbar ${over ? 'over' : ''}`}><i className="ej" style={{ width: Math.min(100, l.percent ?? 0) + '%' }} /></div><span className="mono muted">{pct(l.percent)}</span></div></td>
                        </tr>
                        {openRow === l.id && l.movements.map((m: any) => (
                          <tr key={m.kind + m.id}><td /><td /><td colSpan={2} className="muted">{m.kind === 'viatico' ? 'Viático' : 'Compra'} · {m.title}{m.party ? ` · ${m.party}` : ''}{m.date ? ` · ${fd(m.date)}` : ''}</td><td className="num">{Q(m.executed)}</td><td colSpan={3} className="muted">{m.status_label}</td></tr>
                        ))}
                      </Fragment>
                    )
                  })}
                </Fragment>
              ))}
              <tr className="ftot"><td colSpan={3}>Total</td><td className="num">{Q(t.budget)}</td><td className="num">{Q(t.executed)}</td><td className="num">{Q(t.committed)}</td><td className="num">{Q(t.available)}</td><td className="mono">{pct(t.percent)}</td></tr>
            </tbody>
          </table></div>
          {d.unlabeled.length > 0 && (
            <section className="panel"><h3>Sin rubro <small>asígnalos desde la compra o el viático</small></h3>
              {d.unlabeled.map((m: any) => <div className="line" key={m.kind + m.id}><span>{m.kind === 'viatico' ? 'Viático' : 'Compra'} · {m.title}</span><span className="mono">{Q(m.executed)}</span></div>)}
            </section>
          )}
        </>
      )}
      {edit && pid && <BudgetLineDrawer line={edit === 'new' ? undefined : edit} projectId={pid} onClose={() => setEdit(null)} />}
    </>
  )
}
