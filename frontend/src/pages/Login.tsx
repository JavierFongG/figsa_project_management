import { useState, type FormEvent } from 'react'
import { useAuth } from '../lib/auth'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try { await login(email, password) } catch (x: any) { setErr(x.message) }
    setBusy(false)
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <div className="brand"><b>FIGSA</b><span>CENTRO DE CONTROL</span></div>
        <div className="fld"><label htmlFor="em">Correo</label><input id="em" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div className="fld"><label htmlFor="pw">Contraseña</label><input id="pw" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        {err && <div className="ferr" role="alert">{err}</div>}
        <button className="btn pri" disabled={busy}>{busy ? 'Entrando…' : 'Entrar'}</button>
      </form>
    </div>
  )
}
