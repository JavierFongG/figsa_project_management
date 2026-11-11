import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { get } from '../lib/api'
import { dow, fd, isoWeek, mondayOf, toN } from '../lib/dates'
import { FRENTES } from '../lib/labels'
import { Empty, Head, Loading, Notice, ProjectSelect } from '../components/ui'
import { ActivityDrawer } from '../components/drawers'

const ROW = 30
type Row = { kind: 'ph'; project: any } | { kind: 'act'; a: any }

export default function Schedule() {
  const [sp, setSp] = useSearchParams()
  const project = sp.get('project') ?? ''
  const [zoom, setZoom] = useState(24)
  const [color, setColor] = useState<'estado' | 'frente'>('estado')
  const [open, setOpen] = useState<any | null>(null)
  const q = useQuery({ queryKey: ['schedule', project], queryFn: () => get('/schedule', { project_id: project }) })

  const model = useMemo(() => {
    const d = q.data
    if (!d) return null
    const today = toN(d.today)!
    const rows: Row[] = []
    for (const p of d.projects) {
      const acts = d.activities.filter((a: any) => a.project_id === p.id)
      if (!acts.length) continue
      rows.push({ kind: 'ph', project: p })
      acts.forEach((a: any) => rows.push({ kind: 'act', a }))
    }
    let lo = today - 7, hi = today + 30
    for (const a of d.activities) if (a.sched) {
      lo = Math.min(lo, toN(a.sched.start)!)
      hi = Math.max(hi, toN(a.sched.end)!)
    }
    lo = mondayOf(lo - 3)
    hi = hi + 10
    const idx = new Map<string, number>()
    rows.forEach((r, i) => r.kind === 'act' && idx.set(r.a.id, i))
    return { rows, lo, hi, today, idx }
  }, [q.data])

  if (q.isLoading || !model) return q.error ? <Empty>{(q.error as Error).message}</Empty> : <Loading />
  const { rows, lo, hi, today, idx } = model
  const d = q.data
  const W = (hi - lo + 1) * zoom
  const x = (n: number) => (n - lo) * zoom
  const barOf = (a: any) => {
    if (!a.sched) return null
    const s = toN(a.sched.start)!, e = Math.max(toN(a.sched.end)!, s)
    return { s, e, left: x(s), width: Math.max(4, (e - s + 1) * zoom - 2) }
  }

  // ticks: weeks (zoom<30) or days
  const ticks: { left: number; text: string; we?: boolean }[] = []
  for (let n = lo; n <= hi; n++) {
    const day = dow(n)
    if (zoom >= 30) ticks.push({ left: x(n), text: `${fd(n).split(' ')[0]}`, we: day === 0 || day === 6 })
    else if (day === 1) ticks.push({ left: x(n), text: `S${isoWeek(n)} · ${fd(n)}` })
  }
  const weekends: number[] = []
  if (zoom >= 12) for (let n = lo; n <= hi; n++) if (dow(n) === 0 || dow(n) === 6) weekends.push(n)

  const barClass = (a: any) => {
    const st = a.status_info
    const c = ['gb']
    if (a.type === 'hito') return ''
    if (color === 'frente' && a.front) c.push('f-' + a.front)
    else c.push(st.tone)
    if (a.sched.kind === 'est') c.push('est')
    if (a.sched.kind === 'esc') c.push('esc')
    if (a.critical && a.status !== 'completada') c.push('crit')
    if (a.violation) c.push('viol')
    if (a.status === 'completada') c.push('done')
    return c.join(' ')
  }

  const arrows: string[] = []
  rows.forEach((r, i) => {
    if (r.kind !== 'act') return
    const to = barOf(r.a)
    if (!to) return
    for (const dep of r.a.dependencies) {
      const j = idx.get(dep)
      if (j == null) continue
      const pr = rows[j] as any
      const from = barOf(pr.a)
      if (!from) continue
      const x1 = from.left + from.width, y1 = j * ROW + ROW / 2 + 0 // rows are offset by header in the container
      const x2 = to.left, y2 = i * ROW + ROW / 2
      const mid = Math.max(x1 + 8, Math.min(x2 - 8, x1 + 12))
      arrows.push(`M${x1},${y1} H${mid} V${y2} H${x2 - 1}`)
    }
  })

  return (
    <>
      <Head title="Cronograma" sub="Diagrama de Gantt con dependencias. Las barras rayadas son estimadas; las punteadas azules, proyectadas por el sistema.">
        <ProjectSelect value={project} onChange={(v) => setSp(v ? { project: v } : {})} />
      </Head>
      <div className="gctl">
        <div className="seg" role="group" aria-label="Zoom">
          {[[12, 'Semanas'], [24, 'Normal'], [40, 'Días']].map(([z, l]) => <button key={z} aria-pressed={zoom === z} onClick={() => setZoom(z as number)}>{l}</button>)}
        </div>
        <div className="seg" role="group" aria-label="Color">
          <button aria-pressed={color === 'estado'} onClick={() => setColor('estado')}>Por estado</button>
          <button aria-pressed={color === 'frente'} onClick={() => setColor('frente')}>Por frente</button>
        </div>
        <div className="legend">
          {color === 'estado' ? <><span><i style={{ background: 'var(--ok)' }} />Completada</span><span><i style={{ background: 'var(--warn)' }} />En proceso / próxima</span><span><i style={{ background: 'var(--bad)' }} />Atrasada / bloqueada</span><span><i style={{ background: 'var(--idle)' }} />Pendiente</span></>
            : FRENTES.map(([v, l]) => <span key={v}><i className={`fdot f-${v}`} style={{ width: 18, height: 10 }} />{l}</span>)}
          <span><i style={{ boxShadow: '0 0 0 2px var(--bad)', background: 'var(--surface)' }} />Ruta crítica</span>
        </div>
      </div>
      {d.unscheduled.length > 0 && <Notice>{d.unscheduled.length} actividad(es) sin fecha ni predecesoras: {d.unscheduled.slice(0, 12).join(', ')}{d.unscheduled.length > 12 ? '…' : ''}</Notice>}
      <div className="gscroll"><div className="gin" style={{ width: `calc(var(--gl) + ${W}px)` }}>
        <div className="ghead"><div className="grow"><div className="gl">Actividad</div>
          <div className="gt" style={{ width: W }}>{ticks.map((t, i) => <span key={i} className="tick" style={{ left: t.left, opacity: t.we ? .5 : 1 }}>{t.text}</span>)}</div></div></div>
        <div style={{ position: 'relative' }}>
          {rows.map((r, i) => r.kind === 'ph' ? (
            <div className="grow ph" key={'p' + r.project.id} style={{ height: ROW }}><div className="gl">{r.project.short_name || r.project.id}<span className="muted" style={{ fontWeight: 400, fontSize: 12 }}> {r.project.name}</span></div><div className="gt" style={{ width: W }} /></div>
          ) : (() => {
            const a = r.a, b = barOf(a)
            return (
              <div className="grow" key={a.id} style={{ height: ROW }}>
                <div className="gl" onClick={() => setOpen(a)} title={a.description}><span className={`fdot ${a.front ? 'f-' + a.front : ''}`} /><span className="code">{a.id}</span><span className="d">{a.description}</span></div>
                <div className="gt" style={{ width: W }}>
                  {b ? (a.type === 'hito'
                    ? <span className={`gm ${a.sched.kind === 'esc' ? 'esc' : ''} ${a.status === 'completada' ? 'ok' : ''}`} style={{ left: b.left + zoom / 2 }} title={`${a.id} · ${fd(a.sched.start)}`} onClick={() => setOpen(a)} />
                    : <span className={barClass(a)} style={{ left: b.left, width: b.width }} title={`${a.id} · ${a.description}\n${fd(a.sched.start)} → ${fd(a.sched.end)} · ${a.status_info.label}${a.owner ? ' · ' + a.owner : ''}`} onClick={() => setOpen(a)} />)
                    : <span className="gtbd" style={{ left: x(today) + 8 }} onClick={() => setOpen(a)}>Por definir</span>}
                </div>
              </div>
            )
          })())}
          <div style={{ position: 'absolute', left: 'var(--gl)', top: 0, width: W, height: rows.length * ROW, pointerEvents: 'none' }}>
            {weekends.map((n) => <div key={n} className="wk" style={{ left: x(n), width: zoom }} />)}
            <div className="today-l" style={{ left: x(today) + zoom / 2 }} title="Hoy" />
            <svg className="garrows" width={W} height={rows.length * ROW}>{arrows.map((p, i) => <path key={i} d={p} />)}</svg>
          </div>
        </div>
      </div></div>
      {open && <ActivityDrawer activity={open} onClose={() => setOpen(null)} />}
    </>
  )
}
