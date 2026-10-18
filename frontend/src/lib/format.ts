import type { IntakeStatus, Urgency } from '../types'

export const STATUS_LABEL: Record<IntakeStatus, string> = {
  in_progress: 'In progress',
  submitted: 'Ready for review',
  accepted: 'Accepted',
  declined: 'Declined',
  conflict_hold: 'Conflict hold',
}

export const URGENCY_LABEL: Record<Urgency, string> = {
  low: 'Low',
  normal: 'Normal',
  high: 'High',
  emergency: 'Emergency',
}

export const AREA_LABEL: Record<string, string> = {
  immigration: 'Immigration',
  real_estate: 'Real estate',
  criminal_defense: 'Criminal defense',
  other: 'Other',
  '': 'Not yet known',
}

/** Actions a reviewer can take; mirrors STAFF_TRANSITIONS in the API. */
export const STAFF_ACTIONS: Record<IntakeStatus, IntakeStatus[]> = {
  in_progress: ['declined'],
  submitted: ['accepted', 'declined'],
  conflict_hold: ['accepted', 'declined'],
  accepted: ['declined'],
  declined: [],
}

export function areaLabel(area: string): string {
  return AREA_LABEL[area] ?? area
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  // API timestamps are UTC; SQLite drops the offset, so assume UTC when missing.
  const stamp = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`
  const diff = Math.max(0, now.getTime() - new Date(stamp).getTime())
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

export const TOKEN_KEY = 'intake_token'

export function loadToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function saveToken(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token)
    else window.sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable; the session just won't survive a reload
  }
}
