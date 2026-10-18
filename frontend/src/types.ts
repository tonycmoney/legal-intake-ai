export type IntakeStatus = 'in_progress' | 'submitted' | 'accepted' | 'declined' | 'conflict_hold'
export type Urgency = 'low' | 'normal' | 'high' | 'emergency'

export interface PublicConfig {
  firm_name: string
  firm_phone: string
  ai_enabled: boolean
  max_message_chars: number
}

export interface ChatLine {
  role: 'assistant' | 'client'
  text: string
}

export interface Session {
  token: string
  status: IntakeStatus
  chat: ChatLine[]
  open: boolean
}

export interface MessageResult {
  reply: string
  status: IntakeStatus
  open: boolean
  emergency: boolean
  show_crisis_resources: boolean
}

export interface IntakeSummary {
  id: number
  status: IntakeStatus
  urgency: Urgency
  practice_area: string
  client_name: string
  county: string
  in_custody: string
  deadline: string
  has_conflict: boolean
  has_guardrail_flags: boolean
  turns: number
  created_at: string
  updated_at: string
}

export interface ConflictMatch {
  query: string
  matched_name: string
  relationship_type: string
  matter: string
  score: number
}

export interface IntakeDetail extends IntakeSummary {
  phone: string
  email: string
  adverse_parties: string[]
  key_facts: string[]
  summary: string
  recommended_next_step: string
  conflict_matches: ConflictMatch[]
  guardrail_flags: string[]
  staff_notes: string
  chat: ChatLine[]
  events: { actor: string; action: string; created_at: string }[]
}

export interface ConflictParty {
  id: number
  name: string
  relationship_type: 'client' | 'former_client' | 'adverse'
  matter: string
}

export interface Stats {
  by_status: Record<IntakeStatus, number>
  emergencies_open: number
  conflict_holds: number
}
