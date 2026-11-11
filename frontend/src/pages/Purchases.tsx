import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import EntityDrawer from '../components/EntityDrawer'
import { PurchaseDrawer } from '../components/drawers'
import { Chips, Empty, Head, Loading, Pill, ProjectSelect, useProjects } from '../components/ui'
import { del, get, patch, post } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fd } from '../lib/dates'
import { money } from '../lib/format'
import { EST_COB, EST_COMP, MONEDAS, lab } from '../lib/labels'

const tone = (s: string) => (s === 'recibida' ? 'ok' : s === 'realizada' ? 'ok' : s === 'anticipo' ? 'warn' : s === 'aprobada' ? 'esc' : 'idle')

export default function Purchases() {
  const { canWrite } = useAuth()
  const [project, setProject] = useState('')
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState<any | 'new' | null>(null)
  const [bill, setBill] = useState<any | 'new' | null>(null)
  const { data: ps = [] } = useProjects()
  const pq = useQuery({ queryKey: ['purchases', project, status], queryFn: () => get<any[]>('/purchases', { project_id: project, status }) })
  const bq = useQuery({ queryKey: ['billing', project], queryFn: () => get<any[]>('/billing', { project_id: project }) })
  const pn = (id: string) => ps.find((p) => p.id === id)?.short_name || id

  return (
    <>
      <Head title="Compras y pagos" sub="Compras por proveedor, anticipos, facturas en Drive y cobros al cliente.">
        <ProjectSelect value={project} onChange={setProject} />
        {canWrite && <button className="btn pri" onClick={() => setOpen('new')}>+ Compra</button>}
      </Head>
      <Chips value={status} onChange={setStatus} items={[{ v: '', l: 'Todas' }, ...EST_COMP.map(([v, l]) => ({ v, l }))]} />
      {pq.isLoading ? <Loading /> : !pq.data?.length ? <Empty>Sin compras.</Empty> : (
        <div className="tw"><table>
          <thead><tr><th>Proyecto</th><th>Producto</th><th>Proveedor</th><th>Estado</th><th style={{ textAlign: 'right' }}>Total</th><th style={{ textAlign: 'right' }}>Anticipo</th><th>Se necesita</th><th>Archivos</th></tr></thead>
          <tbody>{pq.data.map((c) => (
            <tr key={c.id} className="click" onClick={() => setOpen(c)}>
              <td className="code">{pn(c.project_id)}</td><td>{c.product}</td><td>{c.supplier ?? ''}</td>
              <td><Pill tone={tone(c.status)}>{lab(EST_COMP, c.status)}</Pill></td>
              <td className="num">{money(c.total_amount, c.currency) ?? <span className="tbd">—</span>}</td>
              <td className="num">{money(c.advance_paid, c.currency) ?? ''}</td>
              <td className="mono">{c.needed_by ? fd(c.needed_by) : ''}</td>
              <td>{c.files?.factura && <a href={c.files.factura.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Factura</a>}{' '}{c.files?.comprobante && <a href={c.files.comprobante.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Comprobante</a>}</td>
            </tr>))}</tbody>
        </table></div>
      )}

      <Head title="Cobros al cliente">{canWrite && <button className="btn" onClick={() => setBill('new')}>+ Cobro</button>}</Head>
      {bq.isLoading ? <Loading /> : !bq.data?.length ? <Empty>Sin cobros registrados.</Empty> : (
        <div className="tw"><table>
          <thead><tr><th>Proyecto</th><th>Concepto</th><th>Estado</th><th style={{ textAlign: 'right' }}>Monto</th><th>Fecha</th></tr></thead>
          <tbody>{bq.data.map((b) => (
            <tr key={b.id} className="click" onClick={() => setBill(b)}>
              <td className="code">{pn(b.project_id)}</td><td>{b.concept}</td>
              <td><Pill tone={b.status === 'cobrado' ? 'ok' : b.status === 'facturado' ? 'warn' : 'idle'}>{lab(EST_COB, b.status)}</Pill></td>
              <td className="num">{money(b.amount, b.currency) ?? ''}</td><td className="mono">{b.billing_date ? fd(b.billing_date) : ''}</td>
            </tr>))}</tbody>
        </table></div>
      )}

      {open && <PurchaseDrawer purchase={open === 'new' ? undefined : open} projectId={project} onClose={() => setOpen(null)} />}
      {bill && (
        <EntityDrawer
          title={bill === 'new' ? 'Nuevo cobro' : bill.concept} creating={bill === 'new'} initial={bill === 'new' ? { project_id: project, status: 'por_facturar', currency: 'GTQ' } : bill}
          onClose={() => setBill(null)}
          fields={[
            { name: 'project_id', label: 'Proyecto', type: 'select', required: true, options: ps.map((p) => [p.id, p.name]) },
            { name: 'concept', label: 'Concepto', required: true },
            { name: 'scope', label: 'Alcance' },
            { name: 'status', label: 'Estado', type: 'select', options: EST_COB, half: true },
            { name: 'billing_date', label: 'Fecha', type: 'date', half: true },
            { name: 'amount', label: 'Monto', type: 'number', half: true },
            { name: 'currency', label: 'Moneda', type: 'select', options: MONEDAS, half: true },
            { name: 'notes', label: 'Notas', type: 'textarea' },
          ]}
          onSave={(b) => (bill === 'new' ? post('/billing', b) : patch(`/billing/${bill.id}`, b))}
          onDelete={bill === 'new' ? undefined : () => del(`/billing/${bill.id}`)}
        />
      )}
    </>
  )
}
