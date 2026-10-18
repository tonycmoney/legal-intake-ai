import type {
  ConflictParty,
  IntakeDetail,
  IntakeStatus,
  IntakeSummary,
  MessageResult,
  PublicConfig,
  Session,
  Stats,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail[0]?.msg ?? detail
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  config: () => request<PublicConfig>('/api/config'),
  start: () => post<Session>('/api/intakes'),
  session: (token: string) => request<Session>(`/api/intakes/${encodeURIComponent(token)}`),
  send: (token: string, text: string) =>
    post<MessageResult>(`/api/intakes/${encodeURIComponent(token)}/messages`, { text }),

  login: (password: string) => post<void>('/api/staff/login', { password }),
  logout: () => post<void>('/api/staff/logout'),
  me: () => request<{ role: string }>('/api/staff/me'),
  stats: () => request<Stats>('/api/staff/stats'),
  intakes: (status?: IntakeStatus) =>
    request<IntakeSummary[]>(`/api/staff/intakes${status ? `?status=${status}` : ''}`),
  intake: (id: number) => request<IntakeDetail>(`/api/staff/intakes/${id}`),
  updateIntake: (id: number, body: { status?: IntakeStatus; staff_notes?: string }) =>
    request<IntakeDetail>(`/api/staff/intakes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  conflicts: () => request<ConflictParty[]>('/api/staff/conflicts'),
  addConflict: (body: Omit<ConflictParty, 'id'>) => post<ConflictParty>('/api/staff/conflicts', body),
  deleteConflict: (id: number) =>
    request<void>(`/api/staff/conflicts/${id}`, { method: 'DELETE' }),
}
