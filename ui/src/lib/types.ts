// src/lib/types.ts
export type Severity = 'critical' | 'high' | 'warning' | 'info'
export type IncidentStatus = 'open' | 'in_triage' | 'remediating' | 'resolved' | 'escalated'
export type ActionType = 'rollout_restart' | 'scale_up' | 'scale_down' | 'argocd_rollback' | 'notify_only'

export interface Incident {
  incident_id: string
  created_at: string
  updated_at: string
  status: IncidentStatus
  title: string
  severity: Severity
  namespace: string
  service: string | null
  deployment: string | null
  pod: string | null
  image_tag: string | null
  incident_type: string | null
  probable_root_cause: string | null
  confidence_score: number | null
  supporting_evidence: string[]
  recommended_action: ActionType | null
  requires_approval: boolean
  grouped_alert_count: number
  last_action?: {
    type: string
    result: string
    success: boolean
    ts: string
  }
  alerts: Array<{
    alertname: string
    severity: Severity
    namespace: string
    service?: string
    pod?: string
    deployment?: string
  }>
  logs: Array<{
    timestamp: string
    level: string
    message: string
  }>
  rollout_events: Array<{
    deployment: string
    namespace: string
    image: string
    revision: number
    started_at: string
    status: string
  }>
}

export interface AuditEntry {
  ts: string
  event_type: string
  incident_id: string
  status?: string
  incident_type?: string
  probable_root_cause?: string
  confidence_score?: number
  recommended_action?: string
  requires_approval?: boolean
  action_type?: string
  target?: string
  actor?: string
  success?: boolean
  result?: string
  approved?: boolean
  approver?: string
}

/**
 * Counts derived from the incidents currently retained.
 *
 * Only quantities the platform can actually compute belong here. MTTR
 * improvement, alert-noise reduction and auto-resolved rate used to live on
 * this type and were populated with fixed literals in both demo and live
 * paths — the platform has never measured any of them.
 */
export interface DashboardStats {
  total_open: number
  critical_count: number
  resolved: number
  awaiting_approval: number
}
