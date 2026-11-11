import { useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useIsFetching, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from './lib/auth'
import { get } from './lib/api'
import { fdy, todayISO } from './lib/dates'
import { Toast } from './components/ui'
import Login from './pages/Login'
import Portfolio from './pages/Portfolio'
import Tasks from './pages/Tasks'
import Schedule from './pages/Schedule'
import Activities from './pages/Activities'
import Purchases from './pages/Purchases'
import Finance from './pages/Finance'
import Externals from './pages/Externals'
import PerDiems from './pages/PerDiems'
import Staff from './pages/Staff'
import Reports from './pages/Reports'

const TABS: [string, string][] = [
  ['/portafolio', 'Portafolio'], ['/tareas', 'Mis tareas'], ['/cronograma', 'Cronograma'], ['/actividades', 'Actividades'],
  ['/compras', 'Compras y pagos'], ['/finanzas', 'Rendimiento financiero'], ['/viaticos', 'Viáticos'],
  ['/externos', 'Pendientes externos'], ['/personal', 'Personal'], ['/resumen', 'Resumen'],
]

export default function App() {
  const { user, loading, logout } = useAuth()
  const qc = useQueryClient()
  const fetching = useIsFetching()
  const [spin, setSpin] = useState(false)
  // counters on the tabs come from the portfolio endpoint (already cached by the first screen)
  const { data: pf } = useQuery({ queryKey: ['portfolio'], queryFn: () => get('/dashboard/portfolio'), enabled: !!user })
  const badge = (p: string) => (p === '/tareas' ? pf?.counters?.tasks_late : p === '/externos' ? pf?.counters?.externals_blocking : 0)

  if (loading) return <div className="login"><span className="muted">Cargando…</span></div>
  if (!user) return <><Login /><Toast /></>

  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="bar">
            <div className="brand"><b>FIGSA</b><span>CENTRO DE CONTROL</span></div>
            <span className="today">{fdy(todayISO())}</span>
            <button className="rbtn" disabled={spin} onClick={async () => { setSpin(true); await qc.invalidateQueries(); setSpin(false) }}>
              {spin || fetching ? 'Actualizando…' : '↻ Actualizar'}
            </button>
            <span className="sync" title={user.email}>{user.name} · {user.role === 'editor' ? 'Editor' : 'Solo lectura'}</span>
            <button className="rbtn" onClick={logout}>Salir</button>
          </div>
          <nav className="tabs" aria-label="Secciones">
            {TABS.map(([p, l]) => (
              <NavLink key={p} to={p} className={({ isActive }) => (isActive ? 'active' : '')}>
                {l}{!!badge(p) && <span className="n">{badge(p)}</span>}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="wrap">
        <Routes>
          <Route path="/portafolio" element={<Portfolio />} />
          <Route path="/tareas" element={<Tasks />} />
          <Route path="/cronograma" element={<Schedule />} />
          <Route path="/actividades" element={<Activities />} />
          <Route path="/compras" element={<Purchases />} />
          <Route path="/finanzas" element={<Finance />} />
          <Route path="/viaticos" element={<PerDiems />} />
          <Route path="/externos" element={<Externals />} />
          <Route path="/personal" element={<Staff />} />
          <Route path="/resumen" element={<Reports />} />
          <Route path="*" element={<Navigate to="/portafolio" replace />} />
        </Routes>
      </main>
      <Toast />
    </>
  )
}
