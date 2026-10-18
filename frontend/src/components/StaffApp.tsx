import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import {
  areaLabel,
  relativeTime,
  STAFF_ACTIONS,
  STATUS_LABEL,
  URGENCY_LABEL,
} from '../lib/format'
import type { ConflictParty, IntakeDetail, IntakeStatus, IntakeSummary, Stats } from '../types'

type View = 'queue' | 'conflicts'
const FILTERS: (IntakeStatus | 'all')[] = ['all', 'submitted', 'conflict_hold', 'in_progress', 'accepted', 'declined']

export function StaffApp() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [disabled, setDisabled] = useState(false)

  useEffect(() => {
    api
      .me()
      .then(() => setAuthed(true))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 503) setDisabled(true)
        setAuthed(false)
      })
  }, [])

  if (authed === null) return <div className="staff-loading">Loading…</div>
  if (!authed) return <Login disabled={disabled} onDone={() => setAuthed(true)} />
  return <Dashboard onLogout={() => setAuthed(false)} />
}

function Login({ disabled, onDone }: { disabled: boolean; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      await api.login(password)
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    }
  }
  return (
    <div className="login-wrap">
      <form className="login" onSubmit={submit}>
        <h1>Intake review</h1>
        <p>Staff sign in</p>
        {disabled ? (
          <div className="alert alert-info">Staff access is not configured on this server.</div>
        ) : (
          <>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
              />
            </label>
            {error && <div className="alert alert-error">{error}</div>}
            <button type="submit" disabled={!password}>
              Sign in
            </button>
          </>
        )}
        <a href="/" className="back">
          ← Client intake page
        </a>
      </form>
    </div>
  )
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [view, setView] = useState<View>('queue')
  const [filter, setFilter] = useState<IntakeStatus | 'all'>('all')
  const [items, setItems] = useState<IntakeSummary[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [selected, setSelected] = useState<IntakeDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([
        api.intakes(filter === 'all' ? undefined : filter),
        api.stats(),
      ])
      setItems(list)
      setStats(s)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onLogout()
      else setError(e instanceof Error ? e.message : 'Could not load intakes')
    }
  }, [filter, onLogout])

  useEffect(() => {
    const tick = async () => {
      await refresh()
    }
    void tick()
    const id = window.setInterval(() => void tick(), 15000)
    return () => window.clearInterval(id)
  }, [refresh])

  const open = async (id: number) => {
    try {
      setSelected(await api.intake(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not open intake')
    }
  }

  const update = async (body: { status?: IntakeStatus; staff_notes?: string }) => {
    if (!selected) return
    try {
      setSelected(await api.updateIntake(selected.id, body))
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
    }
  }

  return (
    <div className="staff">
      <header className="staff-head">
        <div className="staff-brand">
          <span className="firm-mark small" aria-hidden>
            ⚖
          </span>
          Intake review
        </div>
        <nav>
          <button className={view === 'queue' ? 'on' : ''} onClick={() => setView('queue')}>
            Queue
          </button>
          <button className={view === 'conflicts' ? 'on' : ''} onClick={() => setView('conflicts')}>
            Conflict list
          </button>
        </nav>
        <button
          className="link-button"
          onClick={async () => {
            await api.logout()
            onLogout()
          }}
        >
          Sign out
        </button>
      </header>

      {error && (
        <div className="alert alert-error staff-error" role="alert">
          {error}
        </div>
      )}

      {view === 'conflicts' ? (
        <ConflictList />
      ) : (
        <div className="staff-body">
          <section className="queue">
            {stats && (
              <div className="stat-row">
                <Stat label="Emergencies open" value={stats.emergencies_open} tone="urgent" />
                <Stat label="Ready for review" value={stats.by_status.submitted} />
                <Stat label="Conflict holds" value={stats.conflict_holds} tone="warn" />
              </div>
            )}
            <div className="filters" role="tablist">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  role="tab"
                  aria-selected={filter === f}
                  className={filter === f ? 'on' : ''}
                  onClick={() => setFilter(f)}
                >
                  {f === 'all' ? 'All' : STATUS_LABEL[f]}
                </button>
              ))}
            </div>
            {items.length === 0 && <p className="empty">No intakes here yet.</p>}
            <ul className="queue-list">
              {items.map((i) => (
                <li key={i.id}>
                  <button
                    className={selected?.id === i.id ? 'queue-item on' : 'queue-item'}
                    onClick={() => open(i.id)}
                  >
                    <span className={`urgency u-${i.urgency}`}>{URGENCY_LABEL[i.urgency]}</span>
                    <span className="qi-name">{i.client_name || 'Name not given yet'}</span>
                    <span className="qi-meta">
                      {areaLabel(i.practice_area)}
                      {i.county && ` · ${i.county}`} · {relativeTime(i.created_at)}
                    </span>
                    <span className={`status s-${i.status}`}>{STATUS_LABEL[i.status]}</span>
                    {i.has_conflict && <span className="flag">Conflict</span>}
                    {i.has_guardrail_flags && <span className="flag muted">Guardrail</span>}
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section className="detail">
            {selected ? (
              <Detail
                key={`${selected.id}:${selected.updated_at}`}
                intake={selected}
                onUpdate={update}
              />
            ) : (
              <p className="empty">Select an intake to review it.</p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export function Detail({
  intake,
  onUpdate,
}: {
  intake: IntakeDetail
  onUpdate: (body: { status?: IntakeStatus; staff_notes?: string }) => void
}) {
  // The parent keys this component by intake, so state resets per intake.
  const [notes, setNotes] = useState(intake.staff_notes)

  return (
    <article className="detail-card">
      <div className="detail-head">
        <div>
          <h2>{intake.client_name || 'Unnamed prospective client'}</h2>
          <div className="detail-sub">
            {areaLabel(intake.practice_area)} · {STATUS_LABEL[intake.status]} · {intake.turns}{' '}
            turns
          </div>
        </div>
        <span className={`urgency u-${intake.urgency} big`}>{URGENCY_LABEL[intake.urgency]}</span>
      </div>

      {intake.conflict_matches.length > 0 && (
        <div className="alert alert-warn">
          <strong>Possible conflict. Attorney review required before contact.</strong>
          <ul>
            {intake.conflict_matches.map((m) => (
              <li key={m.matched_name}>
                “{m.query}” matches <strong>{m.matched_name}</strong> ({m.relationship_type.replace('_', ' ')}
                {m.matter && `, ${m.matter}`}) · {Math.round(m.score * 100)}%
              </li>
            ))}
          </ul>
        </div>
      )}
      {intake.guardrail_flags.length > 0 && (
        <div className="alert alert-info">
          Guardrails replaced {intake.guardrail_flags.length} assistant repl
          {intake.guardrail_flags.length > 1 ? 'ies' : 'y'} that drifted toward legal advice.
        </div>
      )}

      <dl className="facts">
        <dt>Phone</dt>
        <dd>{intake.phone || '—'}</dd>
        <dt>Email</dt>
        <dd>{intake.email || '—'}</dd>
        <dt>County</dt>
        <dd>{intake.county || '—'}</dd>
        <dt>In custody</dt>
        <dd>{intake.in_custody}</dd>
        <dt>Deadline</dt>
        <dd>{intake.deadline || '—'}</dd>
        <dt>Other parties</dt>
        <dd>{intake.adverse_parties.join(', ') || '—'}</dd>
      </dl>

      {intake.summary && (
        <section>
          <h3>Assistant summary</h3>
          <p>{intake.summary}</p>
          {intake.recommended_next_step && (
            <p className="next-step">Next step: {intake.recommended_next_step}</p>
          )}
        </section>
      )}
      {intake.key_facts.length > 0 && (
        <section>
          <h3>Key facts</h3>
          <ul className="fact-list">
            {intake.key_facts.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>Decision</h3>
        <textarea
          className="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes for the team (not shared with the client)"
          rows={3}
        />
        <div className="actions">
          <button className="btn-secondary" onClick={() => onUpdate({ staff_notes: notes })}>
            Save notes
          </button>
          {STAFF_ACTIONS[intake.status].map((s) => (
            <button
              key={s}
              className={s === 'accepted' ? 'btn-primary' : 'btn-danger'}
              onClick={() => onUpdate({ status: s, staff_notes: notes })}
            >
              {s === 'accepted' ? 'Accept · schedule consult' : 'Decline'}
            </button>
          ))}
        </div>
      </section>

      <details>
        <summary>Conversation ({intake.chat.length} messages)</summary>
        <div className="transcript">
          {intake.chat.map((line, i) => (
            <p key={i} className={`t-${line.role}`}>
              <b>{line.role === 'client' ? 'Client' : 'Assistant'}:</b> {line.text}
            </p>
          ))}
        </div>
      </details>
      <details>
        <summary>Audit trail ({intake.events.length})</summary>
        <ul className="audit">
          {intake.events.map((e, i) => (
            <li key={i}>
              {relativeTime(e.created_at)} · {e.actor} · {e.action}
            </li>
          ))}
        </ul>
      </details>
    </article>
  )
}

function ConflictList() {
  const [parties, setParties] = useState<ConflictParty[]>([])
  const [name, setName] = useState('')
  const [rel, setRel] = useState<ConflictParty['relationship_type']>('client')
  const [matter, setMatter] = useState('')

  const load = useCallback(async () => {
    const rows = await api.conflicts()
    setParties(rows)
  }, [])
  useEffect(() => {
    const init = async () => {
      await load()
    }
    void init()
  }, [load])

  return (
    <div className="conflicts">
      <h2>Conflict list</h2>
      <p className="muted-text">
        Current clients, former clients and adverse parties. Every intake is screened against this
        list as soon as the other parties are known (NY Rule 1.18).
      </p>
      <form
        className="conflict-form"
        onSubmit={async (e) => {
          e.preventDefault()
          await api.addConflict({ name, relationship_type: rel, matter })
          setName('')
          setMatter('')
          await load()
        }}
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" required minLength={2} />
        <select value={rel} onChange={(e) => setRel(e.target.value as ConflictParty['relationship_type'])}>
          <option value="client">Client</option>
          <option value="former_client">Former client</option>
          <option value="adverse">Adverse party</option>
        </select>
        <input value={matter} onChange={(e) => setMatter(e.target.value)} placeholder="Matter (optional)" />
        <button className="btn-primary" type="submit">
          Add
        </button>
      </form>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Relationship</th>
            <th>Matter</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {parties.map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td>{p.relationship_type.replace('_', ' ')}</td>
              <td>{p.matter}</td>
              <td>
                <button
                  className="link-button"
                  aria-label={`Remove ${p.name}`}
                  onClick={async () => {
                    await api.deleteConflict(p.id)
                    await load()
                  }}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
