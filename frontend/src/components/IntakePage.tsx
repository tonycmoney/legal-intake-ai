import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { loadToken, saveToken, telHref } from '../lib/format'
import type { ChatLine, PublicConfig } from '../types'

export function IntakePage() {
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [chat, setChat] = useState<ChatLine[]>([])
  const [open, setOpen] = useState(true)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [emergency, setEmergency] = useState(false)
  const [crisis, setCrisis] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  const begin = useCallback(async () => {
    const session = await api.start()
    saveToken(session.token)
    setToken(session.token)
    setChat(session.chat)
    setOpen(session.open)
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        setConfig(await api.config())
        const saved = loadToken()
        if (saved) {
          try {
            const session = await api.session(saved)
            setToken(session.token)
            setChat(session.chat)
            setOpen(session.open)
            return
          } catch {
            saveToken(null)
          }
        }
        await begin()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not start the intake')
      }
    }
    void load()
  }, [begin])

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [chat, sending])

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text || !token || sending) return
    setDraft('')
    setError(null)
    setSending(true)
    setChat((c) => [...c, { role: 'client', text }])
    try {
      const res = await api.send(token, text)
      setChat((c) => [...c, { role: 'assistant', text: res.reply }])
      setOpen(res.open)
      if (res.emergency) setEmergency(true)
      if (res.show_crisis_resources) setCrisis(true)
    } catch (err) {
      setChat((c) => c.slice(0, -1))
      setDraft(text)
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Message not sent')
    } finally {
      setSending(false)
    }
  }

  const restart = async () => {
    saveToken(null)
    setEmergency(false)
    setCrisis(false)
    setError(null)
    await begin()
  }

  const phone = config?.firm_phone ?? ''
  const max = config?.max_message_chars ?? 2000

  return (
    <div className="intake">
      <div className="demo-banner" role="note">
        Portfolio demo. {config?.firm_name ?? 'This firm'} is fictional. Please don't enter real
        personal or legal information.
      </div>

      <header className="intake-head">
        <div className="firm-mark" aria-hidden>
          ⚖
        </div>
        <div>
          <h1>{config?.firm_name ?? 'Loading…'}</h1>
          <p className="tagline">Immigration · Real estate · Criminal defense · New York</p>
        </div>
        {phone && (
          <a className="call-link" href={telHref(phone)}>
            Call {phone}
          </a>
        )}
      </header>

      <main className="chat-card">
        <div className="chat-intro">
          <h2>Tell us about your situation</h2>
          <p>
            An assistant will ask a few questions so an attorney can review your matter. It can't
            give legal advice, and sharing information here does not create an attorney client
            relationship.
          </p>
        </div>

        {emergency && (
          <div className="alert alert-urgent" role="alert">
            <strong>This sounds urgent.</strong> Please call us now at{' '}
            <a href={telHref(phone)}>{phone}</a>. If anyone is in immediate danger, call 911.
          </div>
        )}
        {crisis && (
          <div className="alert alert-care" role="alert">
            <strong>You don't have to go through this alone.</strong> Call or text{' '}
            <a href="tel:988">988</a> (Suicide &amp; Crisis Lifeline) any time, day or night.
          </div>
        )}

        <div className="messages" aria-live="polite">
          {chat.map((line, i) => (
            <div key={i} className={`bubble ${line.role}`}>
              {line.text}
            </div>
          ))}
          {sending && (
            <div className="bubble assistant typing" aria-label="Assistant is typing">
              <span />
              <span />
              <span />
            </div>
          )}
          <div ref={bottom} />
        </div>

        {config && !config.ai_enabled && (
          <div className="alert alert-info">
            The online assistant isn't available right now. Please call {phone}.
          </div>
        )}
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {open ? (
          <form className="composer" onSubmit={send}>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  e.currentTarget.form?.requestSubmit()
                }
              }}
              placeholder="Type your message…"
              maxLength={max}
              rows={2}
              aria-label="Your message"
              disabled={!token || config?.ai_enabled === false}
            />
            <button type="submit" disabled={!draft.trim() || sending || !token}>
              Send
            </button>
          </form>
        ) : (
          <div className="closed">
            <p>Thank you. Your information has been sent to the firm.</p>
            <button type="button" className="link-button" onClick={restart}>
              Start a new intake
            </button>
          </div>
        )}
      </main>

      <footer className="intake-foot">
        Do not share Social Security numbers, immigration case numbers, or financial account
        details here. · <a href="/staff">Staff sign in</a>
      </footer>
    </div>
  )
}
