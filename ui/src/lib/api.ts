// src/lib/api.ts
//
// Data access for the dashboard. Every hook talks to the real backend: the
// collector for incidents, the executor for the audit trail and approvals.
// Both are reached through the Next rewrites in next.config.js rather than
// directly, so the browser never needs to know the service URLs and any
// credentials stay server-side.
import useSWR from 'swr'
import { AuditEntry, DashboardStats, Incident } from './types'

const COLLECTOR = '/api/collector'
const EXECUTOR = '/api/executor'

class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * Throwing on a non-2xx matters: `fetch` only rejects on network failure, so
 * without this a 502 returning an HTML error page either parses into nonsense
 * or throws deep inside SWR. Callers need to be able to tell "the backend is
 * down" from "there are no incidents" — those look identical otherwise, and
 * only one of them is a problem.
 */
async function fetcher<T>(url: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(url)
  } catch (e) {
    throw new ApiError(`Cannot reach ${url}`)
  }
  if (!res.ok) {
    throw new ApiError(`${url} returned ${res.status}`, res.status)
  }
  return res.json() as Promise<T>
}

export function useIncidents() {
  const { data, error, isLoading, mutate } = useSWR<{ incidents: Incident[] }>(
    `${COLLECTOR}/incidents?limit=50`,
    fetcher,
    { refreshInterval: 5000, keepPreviousData: true }
  )

  return {
    incidents: data?.incidents ?? [],
    isLoading,
    error: error as ApiError | undefined,
    refresh: mutate,
  }
}

export function useIncident(id: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<Incident>(
    id ? `${COLLECTOR}/incidents/${id}` : null,
    fetcher,
    { refreshInterval: 3000 }
  )

  return {
    incident: data ?? null,
    isLoading,
    // A 404 means this incident does not exist (or its retention window has
    // passed), which the detail page renders as "not found" rather than as a
    // backend failure.
    notFound: (error as ApiError | undefined)?.status === 404,
    error: error as ApiError | undefined,
    refresh: mutate,
  }
}

/**
 * Stats derived from the incidents actually on screen.
 *
 * This deliberately reports only what can be counted. Earlier versions also
 * surfaced MTTR improvement, alert-noise reduction and an auto-resolved rate,
 * but those were fixed literals rendered under a heading that said LIVE — the
 * platform has never measured them.
 */
export function useStats(): { stats: DashboardStats } {
  const { incidents } = useIncidents()

  const open = incidents.filter(i => i.status !== 'resolved')

  return {
    stats: {
      total_open: open.length,
      critical_count: open.filter(i => i.severity === 'critical').length,
      resolved: incidents.filter(i => i.status === 'resolved').length,
      awaiting_approval: incidents.filter(i => i.requires_approval && i.status !== 'resolved').length,
    },
  }
}

/**
 * Audit entries. With an incident id, that incident's trail; without one, the
 * global feed across every retained incident.
 */
export function useAudit(incidentId?: string) {
  const key = incidentId
    ? `${EXECUTOR}/incidents/${incidentId}/audit`
    : `${EXECUTOR}/audit?limit=50`

  const { data, error, isLoading } = useSWR<{ entries: AuditEntry[] }>(
    key,
    fetcher,
    { refreshInterval: 5000, keepPreviousData: true }
  )

  return {
    entries: data?.entries ?? [],
    isLoading,
    error: error as ApiError | undefined,
  }
}

export async function approveAction(
  incidentId: string,
  approved: boolean,
  approver = 'operator'
) {
  const res = await fetch(`${EXECUTOR}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident_id: incidentId, approved, approver }),
  })
  if (!res.ok) {
    throw new ApiError(`Approval failed (${res.status})`, res.status)
  }
  return res.json()
}

/**
 * Incident volume over time, bucketed from real timestamps.
 *
 * The window follows the data rather than being fixed at 24h: incidents are
 * held for INCIDENT_TTL_SECONDS, so a hardcoded day-long axis would mostly be
 * empty and imply the platform had been quiet when it had simply forgotten.
 */
export function useIncidentTimeline(buckets = 12) {
  const { incidents } = useIncidents()

  if (incidents.length === 0) return []

  const times = incidents.map(i => new Date(i.created_at).getTime()).filter(t => !isNaN(t))
  if (times.length === 0) return []

  const now = Date.now()
  const start = Math.min(...times)
  const span = Math.max(now - start, 60_000)
  const width = span / buckets

  return Array.from({ length: buckets }, (_, idx) => {
    const from = start + idx * width
    const to = from + width

    const inBucket = incidents.filter(i => {
      const t = new Date(i.created_at).getTime()
      return t >= from && (idx === buckets - 1 ? t <= to : t < to)
    })

    return {
      time: new Date(from).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      incidents: inBucket.length,
      resolved: inBucket.filter(i => i.status === 'resolved').length,
    }
  })
}
