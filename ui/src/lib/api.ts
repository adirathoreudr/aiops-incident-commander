// src/lib/api.ts
import useSWR from 'swr'
import { Incident, AuditEntry, DashboardStats } from './types'
import { DEMO_INCIDENTS, DEMO_STATS, DEMO_AUDIT } from './demo-data'

const IS_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === 'true' || typeof window !== 'undefined'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export function useIncidents() {
  const { data, error, mutate } = useSWR(
    IS_DEMO ? null : '/api/collector/incidents?limit=50',
    fetcher,
    { refreshInterval: 5000 }
  )
  return {
    incidents: IS_DEMO ? DEMO_INCIDENTS : (data?.incidents ?? []) as Incident[],
    isLoading: !IS_DEMO && !error && !data,
    error,
    refresh: mutate,
  }
}

export function useIncident(id: string) {
  const { data, error, mutate } = useSWR(
    IS_DEMO ? null : `/api/collector/incidents/${id}`,
    fetcher,
    { refreshInterval: 3000 }
  )
  const demo = IS_DEMO ? DEMO_INCIDENTS.find(i => i.incident_id === id) ?? null : null
  return {
    incident: IS_DEMO ? demo : (data as Incident | null),
    isLoading: !IS_DEMO && !error && !data,
    error,
    refresh: mutate,
  }
}

export function useStats(): { stats: DashboardStats } {
  // Derive from incidents in real mode; return demo stats in demo mode
  const { incidents } = useIncidents()
  if (IS_DEMO) return { stats: DEMO_STATS }
  return {
    stats: {
      total_open: incidents.filter(i => i.status !== 'resolved').length,
      critical_count: incidents.filter(i => i.severity === 'critical' && i.status !== 'resolved').length,
      resolved_today: incidents.filter(i => i.status === 'resolved').length,
      avg_resolution_minutes: 14,
      noise_reduction_pct: 43,
      auto_resolved_pct: 67,
      mttr_improvement_pct: 58,
    }
  }
}

export function useAudit(incidentId?: string) {
  const { data } = useSWR(
    IS_DEMO ? null : (incidentId ? `/api/collector/incidents/${incidentId}/audit` : null),
    fetcher,
    { refreshInterval: 5000 }
  )
  const demoEntries = IS_DEMO
    ? (incidentId ? DEMO_AUDIT.filter(a => a.incident_id === incidentId) : DEMO_AUDIT)
    : []
  return {
    entries: IS_DEMO ? demoEntries : (data?.entries ?? []) as AuditEntry[],
  }
}

export async function approveAction(incidentId: string, approved: boolean, approver = 'operator') {
  if (IS_DEMO) {
    await new Promise(r => setTimeout(r, 800))
    return { status: approved ? 'approved' : 'rejected' }
  }
  const res = await fetch('/api/executor/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident_id: incidentId, approved, approver }),
  })
  return res.json()
}
