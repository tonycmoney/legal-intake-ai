import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Detail } from './components/StaffApp'
import { IntakePage } from './components/IntakePage'
import { relativeTime, STAFF_ACTIONS, telHref } from './lib/format'
import type { IntakeDetail } from './types'

describe('format helpers', () => {
  it('formats relative times and treats offsetless timestamps as UTC', () => {
    const now = new Date('2026-10-18T12:00:00Z')
    expect(relativeTime('2026-10-18T11:59:45Z', now)).toBe('just now')
    expect(relativeTime('2026-10-18T11:30:00', now)).toBe('30m ago')
    expect(relativeTime('2026-10-18T09:00:00+00:00', now)).toBe('3h ago')
    expect(relativeTime('2026-10-16T12:00:00Z', now)).toBe('2d ago')
  })

  it('builds tel links', () => expect(telHref('(555) 010-0199')).toBe('tel:5550100199'))

  it('mirrors API staff transitions', () => {
    expect(STAFF_ACTIONS.declined).toEqual([])
    expect(STAFF_ACTIONS.conflict_hold).toContain('accepted')
  })
})

// Fake fetch for the intake page.
function mockFetch(routes: Record<string, (init?: RequestInit) => unknown>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${url}`
    const handler = routes[key]
    if (!handler) return new Response(JSON.stringify({ detail: 'nope' }), { status: 404 })
    const body = handler(init)
    if (body instanceof Response) return body
    return new Response(JSON.stringify(body), { status: 200 })
  })
}

const CONFIG = {
  firm_name: 'Hudson Row Legal',
  firm_phone: '(555) 010-0199',
  ai_enabled: true,
  max_message_chars: 2000,
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

describe('IntakePage', () => {
  it('starts a session, sends a message and shows the urgent banner', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'GET /api/config': () => CONFIG,
        'POST /api/intakes': () => ({
          token: 'tok123',
          status: 'in_progress',
          open: true,
          chat: [{ role: 'assistant', text: 'Hi, what is your name?' }],
        }),
        'POST /api/intakes/tok123/messages': () => ({
          reply: 'Please call us right away.',
          status: 'in_progress',
          open: true,
          emergency: true,
          show_crisis_resources: false,
        }),
      }),
    )
    render(<IntakePage />)
    expect(await screen.findByText('Hi, what is your name?')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('Portfolio demo')

    fireEvent.change(screen.getByLabelText('Your message'), {
      target: { value: 'ICE detained my husband' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText('Please call us right away.')).toBeInTheDocument()
    expect(screen.getByText('ICE detained my husband')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('This sounds urgent')
    expect(window.sessionStorage.getItem('intake_token')).toBe('tok123')
  })

  it('shows the API error and restores the draft when sending fails', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'GET /api/config': () => ({ ...CONFIG }),
        'POST /api/intakes': () => ({ token: 't', status: 'in_progress', open: true, chat: [] }),
        'POST /api/intakes/t/messages': () =>
          new Response(JSON.stringify({ detail: 'Too many messages, slow down' }), { status: 429 }),
      }),
    )
    render(<IntakePage />)
    const box = await screen.findByLabelText('Your message')
    await waitFor(() => expect(box).not.toBeDisabled())
    fireEvent.change(box, { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Too many messages, slow down')).toBeInTheDocument()
    expect(box).toHaveValue('hello')
  })

  it('explains when the assistant is not configured', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        'GET /api/config': () => ({ ...CONFIG, ai_enabled: false }),
        'POST /api/intakes': () => ({ token: 't', status: 'in_progress', open: true, chat: [] }),
      }),
    )
    render(<IntakePage />)
    expect(await screen.findByText(/isn't available right now/)).toBeInTheDocument()
    expect(screen.getByLabelText('Your message')).toBeDisabled()
  })
})

const DETAIL: IntakeDetail = {
  id: 1,
  status: 'conflict_hold',
  urgency: 'emergency',
  practice_area: 'immigration',
  client_name: 'Ana Lima',
  county: 'Queens',
  in_custody: 'yes',
  deadline: '',
  has_conflict: true,
  has_guardrail_flags: true,
  turns: 3,
  created_at: '2026-10-18T12:00:00Z',
  updated_at: '2026-10-18T12:00:00Z',
  phone: '718-555-0142',
  email: '',
  adverse_parties: ['Dmitri Volkov'],
  key_facts: ['Husband detained by ICE'],
  summary: 'Detention matter.',
  recommended_next_step: 'Call immediately',
  conflict_matches: [
    {
      query: 'Dmitri Volkov',
      matched_name: 'Dmitri Volkov',
      relationship_type: 'adverse',
      matter: 'Volkov v. Patel',
      score: 1,
    },
  ],
  guardrail_flags: ['replaced_reply:legal_advice_or_outcome_prediction'],
  staff_notes: '',
  chat: [],
  events: [],
}

describe('Staff detail', () => {
  it('shows conflict and guardrail warnings and the allowed actions', () => {
    const onUpdate = vi.fn()
    render(<Detail intake={DETAIL} onUpdate={onUpdate} />)
    expect(screen.getByText(/Possible conflict/)).toBeInTheDocument()
    expect(screen.getByText(/Guardrails replaced 1 assistant reply/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }))
    expect(onUpdate).toHaveBeenCalledWith({ status: 'declined', staff_notes: '' })
  })
})
