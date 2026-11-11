import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { nat } from '../lib/format'
import { EST_ACT } from '../lib/labels'
import { Chips, Empty, FrontTag, Head, Loading, Pill, ProjectSelect, Tag } from '../components/ui'
import { ActivityDrawer } from '../components/drawers'

export default function Activities() {
  const { canWrite } = useAuth()
  const [project, setProject] = useState('')
  const [status, setStatus] = useState('todas')
  const [text, setText] = useState('')
  const [open, setOpen] = useState<any | 'new' | null>(null)
  const q = useQuery({ queryKey: ['activities', project], queryFn: () => get<any[]>('/activities', { project_id: project }) })

  const rows = useMemo(() => {
    const t = text.trim().toLowerCase()
    return (q.data ?? []).filter((a) =>
      (status === 'todas' || a.status === status || (status === 'atrasada' && ['atrasada', 'inicio_atrasado'].includes(a.status_info.code))) &&
      (!t || a.id.toLowerCase().includes(t) || a.description.toLowerCase().includes(t) || (a.owner ?? '').toLowerCase().includes(t)),
    ).sort((a, b) => nat(a.project_id, b.project_id) || nat(a.id, b.id))
  }, [q.data, status, text])
  const count = (s: string) => (q.data ?? []).filter((a) => (s === 'atrasada' ? ['atrasada', 'inicio_atrasado'].includes(a.status_info.code) : a.status === s)).length

  return (
    <>
      <Head title="Actividades" sub="Todas las actividades con sus fechas calculadas.">
        <ProjectSelect value={project} onChange={setProject} />
        {canWrite && <button className="btn pri" onClick={() => setOpen('new')}>+ Actividad</button>}
      </Head>
      <div className="gctl">
        <Chips value={status} onChange={setStatus} items={[{ v: 'todas', l: 'Todas', c: q.data?.length }, { v: 'atrasada', l: 'Atrasadas', c: count('atrasada') }, ...EST_ACT.map(([v, l]) => ({ v, l, c: count(v) }))]} />
        <input className="search" placeholder="Buscar código, texto o responsable" value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      {q.isLoading ? <Loading /> : !rows.length ? <Empty>Sin resultados.</Empty> : (
        <div className="tw"><table>
          <thead><tr><th>Código</th><th>Actividad</th><th>Estado</th><th>Fechas</th><th>Resp.</th><th>Depende de</th><th /></tr></thead>
          <tbody>{rows.map((a) => (
            <tr key={a.id} className="click" onClick={() => setOpen(a)}>
              <td className="code">{a.id}</td>
              <td>{a.description} <FrontTag f={a.front} />{a.critical && <Tag kind="r">Ruta crítica</Tag>}{a.violation && <Tag kind="r">Choca con {a.violation}</Tag>}</td>
              <td><Pill tone={a.status_info.tone}>{a.status_info.label}</Pill></td>
              <td className="mono">{a.sched ? `${fd(a.sched.start)} → ${fd(a.sched.end)}` : <span className="tbd">Por definir</span>}{a.sched?.kind === 'esc' && <Tag>proyectada</Tag>}</td>
              <td>{a.owner ?? ''}</td>
              <td className="code">{a.dependencies.join(', ')}</td>
              <td className="muted">{a.note_count ? `${a.note_count} avance(s)` : ''}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {open && <ActivityDrawer activity={open === 'new' ? undefined : open} projectId={project} onClose={() => setOpen(null)} />}
    </>
  )
}
