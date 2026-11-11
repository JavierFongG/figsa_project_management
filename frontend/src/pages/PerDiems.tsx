import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EntityDrawer from '../components/EntityDrawer'
import { Chips, CopyBox, Empty, Head, Loading, Pill, ProjectSelect, useProjects } from '../components/ui'
import { del, get, patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { q as Q } from '../lib/format'
import { CAT_V, COMP_V, EST_V, lab } from '../lib/labels'

export default function PerDiems() {
  const { canWrite } = useAuth()
  const { data: ps = [] } = useProjects()
  const [project, setProject] = useState('')
  const [month, setMonth] = useState('')
  const [open, setOpen] = useState<any | 'new' | null>(null)
  const params = { project_id: project, month }
  const list = useQuery({ queryKey: ['per-diems', params], queryFn: () => get<any[]>('/per-diems', params) })
  const sum = useQuery({ queryKey: ['per-diems-sum', params], queryFn: () => get('/per-diems/summary', params) })
  const lines = useQuery({ queryKey: ['lines', open?.project_id || project], queryFn: () => get<any[]>(`/projects/${open?.project_id || project}/budget-lines`), enabled: !!(open?.project_id || project) })
  const pn = (id: string) => ps.find((p) => p.id === id)?.short_name || id

  return (
    <>
      <Head title="Viáticos" sub="Un solo libro: anticipos entregados y gastos. Los gastos con rubro cuentan como ejecutado en Rendimiento financiero.">
        <ProjectSelect value={project} onChange={setProject} />
        <input type="month" className="search" style={{ maxWidth: 160 }} value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Mes" />
        {canWrite && <button className="btn pri" onClick={() => setOpen('new')}>+ Registro</button>}
      </Head>
      {sum.data && (
        <div className="grid g2">
          <section className="panel"><h3>Por persona <small>anticipos − gastos</small></h3>
            {sum.data.people.length ? (
              <div className="tw"><table><thead><tr><th>Persona</th><th style={{ textAlign: 'right' }}>Anticipos</th><th style={{ textAlign: 'right' }}>Gastos</th><th style={{ textAlign: 'right' }}>Saldo</th></tr></thead>
                <tbody>{sum.data.people.map((p: any) => (
                  <tr key={p.person}><td>{p.person}</td><td className="num">{Q(p.advances)}</td><td className="num">{Q(p.expenses)}</td>
                    <td className="num" style={{ color: p.balance < 0 ? 'var(--bad)' : undefined }}>{p.balance > 0 ? `Devuelve ${Q(p.balance)}` : p.balance < 0 ? `Reembolsar ${Q(-p.balance)}` : 'Cuadrado'}</td></tr>))}</tbody></table></div>
            ) : <Empty>Sin registros.</Empty>}
            {sum.data.without_receipt.count > 0 && <p className="muted">{sum.data.without_receipt.count} gasto(s) sin comprobante por {Q(sum.data.without_receipt.amount)}.</p>}
          </section>
          <section className="panel"><h3>Liquidación para compartir</h3><CopyBox text={sum.data.text} rows={12} /></section>
        </div>
      )}
      {list.isLoading ? <Loading /> : !list.data?.length ? <Empty>Sin registros.</Empty> : (
        <div className="tw"><table>
          <thead><tr><th>Fecha</th><th>Proyecto</th><th>Persona</th><th>Tipo</th><th>Detalle</th><th>Comprobante</th><th>Estado</th><th style={{ textAlign: 'right' }}>Monto</th></tr></thead>
          <tbody>{list.data.map((r) => (
            <tr key={r.id} className="click" onClick={() => setOpen(r)}>
              <td className="mono">{fd(r.entry_date)}</td><td className="code">{pn(r.project_id)}</td><td>{r.person}</td>
              <td>{r.kind === 'anticipo' ? <Pill tone="esc">Anticipo</Pill> : lab(CAT_V, r.category)}</td>
              <td>{r.detail ?? ''}</td><td>{r.kind === 'gasto' ? lab(COMP_V, r.receipt_type) : ''}</td>
              <td>{lab(EST_V, r.status)}</td><td className="num">{Q(r.amount)}</td>
            </tr>))}</tbody>
        </table></div>
      )}
      {open && (
        <EntityDrawer
          title={open === 'new' ? 'Nuevo registro de viáticos' : `${open.person} · ${Q(open.amount)}`} creating={open === 'new'}
          initial={open === 'new' ? { project_id: project, entry_date: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Guatemala' }), kind: 'gasto', status: 'pendiente' } : open}
          onClose={() => setOpen(null)}
          fields={[
            { name: 'kind', label: 'Tipo', type: 'select', options: [['gasto', 'Gasto'], ['anticipo', 'Anticipo entregado']], half: true },
            { name: 'entry_date', label: 'Fecha', type: 'date', required: true, half: true },
            { name: 'project_id', label: 'Proyecto', type: 'select', required: true, options: ps.map((p) => [p.id, p.name]) },
            { name: 'person', label: 'Persona', required: true, half: true },
            { name: 'amount', label: 'Monto (Q)', type: 'number', required: true, half: true },
            { name: 'category', label: 'Categoría', type: 'select', nullable: true, options: CAT_V, half: true },
            { name: 'receipt_type', label: 'Comprobante', type: 'select', nullable: true, options: COMP_V, half: true },
            { name: 'document_no', label: 'No. de documento', half: true },
            { name: 'status', label: 'Estado', type: 'select', options: EST_V, half: true },
            { name: 'detail', label: 'Detalle' },
            { name: 'budget_line_id', label: 'Rubro del presupuesto', type: 'select', nullable: true, options: (lines.data ?? []).map((l) => [l.id, `${l.code} · ${l.material || l.activity || ''}`]), hint: 'Solo los gastos con rubro cuentan como ejecutado' },
            { name: 'notes', label: 'Notas', type: 'textarea' },
          ]}
          onSave={(b) => (open === 'new' ? post('/per-diems', b) : patch(`/per-diems/${open.id}`, b, open.updated_at))}
          onDelete={open === 'new' ? undefined : () => del(`/per-diems/${open.id}`)}
        />
      )}
    </>
  )
}
