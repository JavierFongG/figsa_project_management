import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EntityDrawer from '../components/EntityDrawer'
import { Chips, Empty, Head, Loading, Pill, ProjectSelect, Tag, useAct, useProjects } from '../components/ui'
import { del, get, patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { CANALES, EST_EXT, lab } from '../lib/labels'

export default function Externals() {
  const { canWrite } = useAuth()
  const act = useAct()
  const { data: ps = [] } = useProjects()
  const [project, setProject] = useState('')
  const [status, setStatus] = useState('abiertos')
  const [open, setOpen] = useState<any | 'new' | null>(null)
  const q = useQuery({ queryKey: ['externals', project, status], queryFn: () => get<any[]>('/externals', { project_id: project, status }) })
  const pn = (id: string) => ps.find((p) => p.id === id)?.short_name || id

  return (
    <>
      <Head title="Pendientes externos" sub="Cosas que dependen de terceros: permisos, planos, respuestas de proveedores. Las que bloquean actividades aparecen primero.">
        <ProjectSelect value={project} onChange={setProject} />
        {canWrite && <button className="btn pri" onClick={() => setOpen('new')}>+ Pendiente</button>}
      </Head>
      <Chips value={status} onChange={setStatus} items={[{ v: 'abiertos', l: 'Abiertos' }, ...EST_EXT.map(([v, l]) => ({ v, l })), { v: '', l: 'Todos' }]} />
      {q.isLoading ? <Loading /> : !q.data?.length ? <Empty>Nada pendiente con terceros.</Empty> : (
        <div className="grid g2">
          {q.data.map((x) => (
            <article className="req" key={x.id}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Pill tone={x.status === 'resuelto' ? 'ok' : x.status === 'esperando' ? 'warn' : 'idle'}>{lab(EST_EXT, x.status)}</Pill>
                <span className="code">{pn(x.project_id)}</span>
                {x.waiting_days != null && <span className="muted">{x.waiting_days} d esperando</span>}
              </div>
              <h3>{x.counterparty}</h3>
              <div>{x.subject}</div>
              <div className="muted">{[x.channel && lab(CANALES, x.channel), x.contact, x.follow_up_on && `Seguimiento ${fd(x.follow_up_on)}`].filter(Boolean).join(' · ')}</div>
              <div>{x.blocks.map((b: string) => <Tag key={b} kind="r">Bloquea {b}</Tag>)}{x.impacted_activities > 0 && <Tag kind="a">{x.impacted_activities} actividades afectadas</Tag>}</div>
              {x.response && <div className="last">{x.response}</div>}
              <div className="chips">
                {canWrite && x.status !== 'resuelto' && <button className="btn sm" onClick={() => act(() => post(`/externals/${x.id}/follow-up`), x.status === 'por_solicitar' ? 'Marcado como solicitado' : 'Seguimiento registrado')}>{x.status === 'por_solicitar' ? 'Ya lo solicité hoy' : 'Di seguimiento hoy'}</button>}
                {canWrite && x.status !== 'resuelto' && <button className="btn sm" onClick={() => act(() => post(`/externals/${x.id}/resolve`), 'Resuelto')}>✓ Resuelto</button>}
                <button className="btn sm" onClick={() => setOpen(x)}>{canWrite ? 'Editar' : 'Ver'}</button>
              </div>
            </article>
          ))}
        </div>
      )}
      {open && (
        <EntityDrawer
          title={open === 'new' ? 'Nuevo pendiente externo' : open.counterparty} creating={open === 'new'}
          initial={open === 'new' ? { project_id: project, status: 'por_solicitar', blocks: [] } : open} onClose={() => setOpen(null)}
          fields={[
            { name: 'project_id', label: 'Proyecto', type: 'select', required: true, options: ps.map((p) => [p.id, p.name]) },
            { name: 'counterparty', label: 'Quién (persona o entidad)', required: true },
            { name: 'subject', label: 'Qué se espera', required: true },
            { name: 'status', label: 'Estado', type: 'select', options: EST_EXT, half: true },
            { name: 'channel', label: 'Canal', type: 'select', nullable: true, options: CANALES, half: true },
            { name: 'requested_on', label: 'Solicitado el', type: 'date', half: true },
            { name: 'follow_up_on', label: 'Próximo seguimiento', type: 'date', half: true },
            { name: 'contact', label: 'Contacto' },
            { name: 'blocks', label: 'Bloquea actividades (códigos separados por coma)', type: 'codes' },
            { name: 'response', label: 'Respuesta recibida', type: 'textarea' },
          ]}
          onSave={(b) => (open === 'new' ? post('/externals', b) : patch(`/externals/${open.id}`, b, open.updated_at))}
          onDelete={open === 'new' ? undefined : () => del(`/externals/${open.id}`)}
        />
      )}
    </>
  )
}
