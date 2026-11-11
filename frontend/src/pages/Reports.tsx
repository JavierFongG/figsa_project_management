import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Chips, CopyBox, Empty, Head, Kpis, Loading, ProjectSelect, toast } from '../components/ui'
import { get, post } from '../lib/api'
import { fdy } from '../lib/dates'
import { q as Q } from '../lib/format'

export default function Reports() {
  const [period, setPeriod] = useState('semana')
  const [project, setProject] = useState('')
  const [audience, setAudience] = useState('jefe')
  const sum = useQuery({ queryKey: ['summary', period, project], queryFn: () => get('/reports/summary', { period, project_id: project }) })
  const wa = useMutation({
    mutationFn: () => post('/reports/whatsapp', { period, audience, project_id: project || null }),
    onError: (e: Error) => toast(e.message, true),
  })
  const d = sum.data
  return (
    <>
      <Head title="Resumen" sub="Lo que se logró en el período y un mensaje de WhatsApp listo para enviar (plantilla fija, sin IA).">
        <ProjectSelect value={project} onChange={setProject} />
      </Head>
      <Chips value={period} onChange={(v) => { setPeriod(v); wa.reset() }} items={[{ v: 'hoy', l: 'Hoy' }, { v: 'semana', l: 'Esta semana' }, { v: 'mes', l: 'Este mes' }]} />
      {sum.isLoading ? <Loading /> : !d ? <Empty>No se pudo cargar.</Empty> : (
        <>
          <Kpis items={[
            { n: d.activities.length, l: 'Actividades completadas' }, { n: d.notes.length, l: 'Avances registrados' },
            { n: Q(d.payments.reduce((s: number, p: any) => s + p.amount, 0)), l: `Ejecutado · ${d.payments.length} pagos` },
            { n: d.files.length, l: 'Facturas y comprobantes' }, { n: d.externals.length, l: 'Externos resueltos' }, { n: d.lines.length, l: 'Líneas cerradas' },
          ]} />
          <div className="grid g2">
            <section className="panel"><h3>Resumen <small>{fdy(d.start)}{d.start !== d.end ? ' – ' + fdy(d.end) : ''}</small></h3><CopyBox text={d.text} rows={14} /></section>
            <section className="panel"><h3>Mensaje de WhatsApp</h3>
              <div className="gctl" style={{ marginBottom: 10 }}>
                <Chips value={audience} onChange={(v) => { setAudience(v); wa.reset() }} items={[{ v: 'jefe', l: 'Para el jefe (con gastos)' }, { v: 'cliente', l: 'Para el cliente' }]} />
                <button className="btn pri" disabled={wa.isPending} onClick={() => wa.mutate()}>{wa.isPending ? 'Generando…' : 'Generar'}</button>
              </div>
              {wa.data ? (wa.data.has_content ? <CopyBox text={wa.data.text} rows={14} /> : <Empty>No hay avances en el período.</Empty>) : <Empty>Pulsa “Generar”.</Empty>}
            </section>
          </div>
        </>
      )}
    </>
  )
}
