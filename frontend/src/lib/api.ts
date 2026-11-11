// Thin fetch wrapper: JWT from localStorage, JSON in/out, readable Spanish errors, optional If-Match.
const BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '/api/v1'
const KEY = 'figsa.token'

export const getToken = () => {
  try { return localStorage.getItem(KEY) } catch { return null }
}
export const setToken = (t: string | null) => {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* private mode */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Opts = { method?: string; body?: any; params?: Record<string, any>; etag?: string; form?: FormData }

function qs(params?: Record<string, any>) {
  if (!params) return ''
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? '?' + s : ''
}

function detailText(d: any, status: number): string {
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((e) => `${(e.loc || []).filter((x: any) => x !== 'body').join('.')}: ${e.msg}`).join(' · ')
  }
  if (status === 412) return 'Alguien más modificó este registro. Recarga y vuelve a intentar.'
  return `Error ${status}`
}

export async function api<T = any>(path: string, o: Opts = {}): Promise<T> {
  const h: Record<string, string> = {}
  const tok = getToken()
  if (tok) h.Authorization = 'Bearer ' + tok
  if (o.etag) h['If-Match'] = o.etag
  let body: BodyInit | undefined
  if (o.form) body = o.form
  else if (o.body !== undefined) { h['Content-Type'] = 'application/json'; body = JSON.stringify(o.body) }
  let r: Response
  try {
    r = await fetch(BASE + path + qs(o.params), { method: o.method || 'GET', headers: h, body })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor. Revisa tu conexión.')
  }
  if (r.status === 401 && path !== '/auth/login') {
    setToken(null)
    window.dispatchEvent(new Event('figsa:logout'))
  }
  if (r.status === 204) return undefined as T
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new ApiError(r.status, detailText(data?.detail, r.status))
  return data as T
}

export const get = <T = any>(path: string, params?: Record<string, any>) => api<T>(path, { params })
export const post = <T = any>(path: string, body?: any, params?: Record<string, any>) => api<T>(path, { method: 'POST', body: body ?? {}, params })
export const patch = <T = any>(path: string, body: any, etag?: string) => api<T>(path, { method: 'PATCH', body, etag })
export const del = (path: string) => api<void>(path, { method: 'DELETE' })
export const upload = <T = any>(path: string, file: File, params: Record<string, any>) => {
  const f = new FormData()
  f.append('file', file)
  return api<T>(path, { method: 'POST', form: f, params })
}
