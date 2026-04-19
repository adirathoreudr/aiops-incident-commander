// src/pages/incident/[id].tsx
import { useState } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import { clsx } from 'clsx'
import { format } from 'date-fns'
import Layout from '@/components/Layout'
import AuditTimeline from '@/components/AuditTimeline'
import { useIncident, useAudit, approveAction } from '@/lib/api'

const ACTION_DESCRIPTIONS: Record<string, string> = {
  rollout_restart: 'Patch pod template annotation to trigger a zero-downtime rolling restart. No pods deleted before replacements are ready.',
  scale_up:        'Increase replica count to distribute load. Reversible — can scale back down at any time.',
  scale_down:      'Reduce replica count. May impact capacity. Requires explicit approval.',
  argocd_rollback: 'Restore previous ArgoCD revision. Always requires human approval.',
  notify_only:     'Send incident summary notification. No cluster changes.',
}

export default function IncidentDetail() {
  const router = useRouter()
  const id = router.query.id as string
  const { incident, isLoading } = useIncident(id)
  const { entries } = useAudit(id)
  const [approving, setApproving] = useState(false)
  const [approveResult, setApproveResult] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'logs' | 'rollouts' | 'audit'>('overview')

  const handleApprove = async (approved: boolean) => {
    setApproving(true)
    try {
      await approveAction(id, approved, 'operator@demo')
      setApproveResult(approved ? 'Action approved and enqueued for execution.' : 'Action rejected. Incident escalated for manual review.')
    } finally {
      setApproving(false)
    }
  }

  if (isLoading) {
    return (
      <Layout>
        <div className="font-mono text-xs text-ink-muted py-24 text-center animate-pulse">
          LOADING INCIDENT<span className="cursor" />
        </div>
      </Layout>
    )
  }

  if (!incident) {
    return (
      <Layout>
        <div className="font-mono text-xs text-ink-muted py-24 text-center">
          INCIDENT NOT FOUND
          <div className="mt-4">
            <Link href="/dashboard" className="text-amber-400 hover:text-amber-300 transition-colors">
              ← BACK TO DASHBOARD
            </Link>
          </div>
        </div>
      </Layout>
    )
  }

  const conf = incident.confidence_score ?? 0
  const confPct = Math.round(conf * 100)

  return (
    <Layout>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 font-mono text-2xs text-ink-muted">
        <Link href="/dashboard" className="hover:text-amber-400 transition-colors">INCIDENTS</Link>
        <span>/</span>
        <span className="text-ink-secondary truncate max-w-xs">{incident.incident_id.slice(0, 16)}…</span>
      </div>

      {/* Header */}
      <div className="border-crt p-6 mb-6 relative overflow-hidden">
        {incident.severity === 'critical' && (
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: 'linear-gradient(90deg, rgba(255,59,59,0.04) 0%, transparent 60%)' }} />
        )}
        <div className="flex items-start gap-4 relative">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2 flex-wrap">
              <span className={clsx('font-mono text-2xs px-2 py-1', `badge-${incident.severity}`)}>
                {incident.severity.toUpperCase()}
              </span>
              <span className={clsx('font-mono text-2xs font-semibold tracking-wide', `status-${incident.status}`)}>
                {incident.status.replace('_', ' ').toUpperCase()}
              </span>
              <span className="font-mono text-2xs text-ink-muted">
                {format(new Date(incident.created_at), 'dd MMM yyyy HH:mm:ss')} UTC
              </span>
              {incident.grouped_alert_count > 1 && (
                <span className="font-mono text-2xs text-amber-500/70">
                  {incident.grouped_alert_count} alerts grouped
                </span>
              )}
            </div>
            <h1 className="font-mono text-sm font-semibold text-ink-primary leading-snug mb-1">
              {incident.title}
            </h1>
            <div className="flex items-center gap-3 flex-wrap mt-2 font-mono text-2xs text-ink-muted">
              <span>ns/{incident.namespace}</span>
              {incident.service    && <span>svc/{incident.service}</span>}
              {incident.deployment && <span>deploy/{incident.deployment}</span>}
              {incident.pod        && <span>pod/{incident.pod}</span>}
              {incident.image_tag  && <span className="text-amber-500/70">{incident.image_tag}</span>}
            </div>
          </div>
        </div>
      </div>

      {/* AI Analysis + Approval (if needs approval) */}
      {incident.probable_root_cause && (
        <div className="grid md:grid-cols-3 gap-4 mb-6">
          {/* Root cause */}
          <div className="md:col-span-2 border-crt p-5">
            <p className="font-mono text-2xs tracking-widest text-amber-500/80 mb-3">◈ AI ROOT CAUSE ANALYSIS</p>
            {incident.incident_type && (
              <div className="flex items-center gap-2 mb-3">
                <span className="font-mono text-2xs px-2 py-0.5 text-sky-400 border border-sky-400/30 bg-sky-400/5">
                  {incident.incident_type.replace('_', ' ').toUpperCase()}
                </span>
              </div>
            )}
            <p className="font-mono text-xs text-ink-secondary leading-relaxed">
              {incident.probable_root_cause}
            </p>

            {incident.supporting_evidence.length > 0 && (
              <div className="mt-4">
                <p className="font-mono text-2xs tracking-wider text-ink-muted mb-2">EVIDENCE</p>
                <ul className="space-y-1.5">
                  {incident.supporting_evidence.map((ev, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-amber-500/70 font-mono text-xs mt-0.5 shrink-0">›</span>
                      <span className="font-mono text-xs text-ink-secondary">{ev}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Confidence + action */}
          <div className="border-crt p-5 flex flex-col">
            <p className="font-mono text-2xs tracking-widest text-amber-500/80 mb-4">◈ RECOMMENDATION</p>

            {/* Confidence dial */}
            <div className="mb-4">
              <div className="flex justify-between mb-2">
                <span className="font-mono text-2xs text-ink-muted">CONFIDENCE</span>
                <span className={clsx(
                  'font-mono text-lg font-bold stat-num',
                  conf >= 0.75 ? 'text-emerald-400' : conf >= 0.5 ? 'text-amber-400' : 'text-red-400'
                )}>
                  {confPct}%
                </span>
              </div>
              <div className="confidence-bar h-1.5" style={{ '--confidence': `${confPct}%` } as React.CSSProperties} />
              <p className="font-mono text-2xs text-ink-muted mt-1">
                {conf >= 0.75 ? 'HIGH — auto-execute eligible' : conf >= 0.5 ? 'MEDIUM — review recommended' : 'LOW — escalate'}
              </p>
            </div>

            {/* Recommended action */}
            {incident.recommended_action && (
              <div className="mb-4 p-3" style={{ background: 'var(--surface-raised)', border: '1px solid var(--surface-border)' }}>
                <p className="font-mono text-2xs text-ink-muted mb-1">RECOMMENDED ACTION</p>
                <p className="font-mono text-xs font-semibold text-sky-400 mb-2">
                  {incident.recommended_action.replace('_', ' ').toUpperCase()}
                </p>
                <p className="font-mono text-2xs text-ink-muted leading-relaxed">
                  {ACTION_DESCRIPTIONS[incident.recommended_action] ?? ''}
                </p>
              </div>
            )}

            {/* Approval buttons */}
            {incident.requires_approval && !approveResult && (
              <div className="mt-auto">
                <p className="font-mono text-2xs text-amber-400 mb-3">⏸ AWAITING HUMAN APPROVAL</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(true)}
                    disabled={approving}
                    className="flex-1 font-mono text-2xs py-2 bg-emerald-400/10 border border-emerald-400/40 text-emerald-400 hover:bg-emerald-400/20 transition-all disabled:opacity-50 tracking-wide"
                  >
                    {approving ? '...' : '✓ APPROVE'}
                  </button>
                  <button
                    onClick={() => handleApprove(false)}
                    disabled={approving}
                    className="flex-1 font-mono text-2xs py-2 bg-red-400/10 border border-red-400/40 text-red-400 hover:bg-red-400/20 transition-all disabled:opacity-50 tracking-wide"
                  >
                    {approving ? '...' : '✗ REJECT'}
                  </button>
                </div>
              </div>
            )}

            {approveResult && (
              <div className="mt-auto p-3 border border-amber-400/30 bg-amber-400/5">
                <p className="font-mono text-2xs text-amber-400">{approveResult}</p>
              </div>
            )}

            {incident.last_action && (
              <div className="mt-auto p-3 border border-emerald-400/20 bg-emerald-400/5">
                <p className="font-mono text-2xs text-emerald-400 mb-1">◎ ACTION EXECUTED</p>
                <p className="font-mono text-2xs text-ink-muted">{incident.last_action.result}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b mb-0" style={{ borderColor: 'var(--surface-border)' }}>
        {(['overview', 'logs', 'rollouts', 'audit'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              'font-mono text-2xs tracking-widest px-4 py-2.5 border-b-2 transition-all uppercase',
              activeTab === tab
                ? 'border-amber-400 text-amber-400'
                : 'border-transparent text-ink-muted hover:text-ink-secondary'
            )}
          >
            {tab}
            {tab === 'logs'    && incident.logs.length > 0   && <span className="ml-1 text-ink-muted">({incident.logs.length})</span>}
            {tab === 'audit'   && entries.length > 0          && <span className="ml-1 text-ink-muted">({entries.length})</span>}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="border-crt border-t-0 p-5">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            <div>
              <p className="font-mono text-2xs text-ink-muted tracking-widest mb-3">ACTIVE ALERTS</p>
              {incident.alerts.map((a, i) => (
                <div key={i} className="flex items-center gap-3 py-2 border-b last:border-0" style={{ borderColor: 'var(--surface-border)' }}>
                  <span className={clsx('font-mono text-2xs px-1.5 py-0.5', `badge-${a.severity}`)}>
                    {a.severity.toUpperCase()}
                  </span>
                  <span className="font-mono text-xs text-ink-secondary">{a.alertname}</span>
                  <span className="font-mono text-2xs text-ink-muted">{a.namespace}</span>
                  {a.pod && <span className="font-mono text-2xs text-ink-muted">{a.pod}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="data-cell space-y-1">
            {incident.logs.length === 0 ? (
              <p className="text-ink-muted py-4 text-center">NO LOGS CAPTURED</p>
            ) : [...incident.logs].reverse().map((log, i) => (
              <div key={i} className="flex gap-3 py-1 border-b last:border-0" style={{ borderColor: 'var(--surface-border)' }}>
                <span className="text-ink-muted shrink-0 w-32 text-2xs">
                  {log.timestamp ? format(new Date(log.timestamp), 'HH:mm:ss.SSS') : '—'}
                </span>
                <span className={clsx('uppercase w-10 shrink-0 text-2xs font-semibold', `log-${log.level}`)}>
                  {log.level.slice(0, 4)}
                </span>
                <span className="text-ink-secondary text-xs break-all">{log.message}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'rollouts' && (
          <div>
            {incident.rollout_events.length === 0 ? (
              <p className="font-mono text-xs text-ink-muted py-4 text-center">NO ROLLOUT EVENTS</p>
            ) : incident.rollout_events.map((r, i) => (
              <div key={i} className="flex items-start gap-4 py-3 border-b last:border-0 font-mono text-xs" style={{ borderColor: 'var(--surface-border)' }}>
                <span className="text-ink-muted shrink-0">rev {r.revision}</span>
                <span className="text-amber-400/80">{r.image}</span>
                <span className={clsx('shrink-0', r.status === 'complete' ? 'text-emerald-400' : 'text-red-400')}>
                  {r.status}
                </span>
                <span className="text-ink-muted ml-auto text-2xs">
                  {format(new Date(r.started_at), 'dd MMM HH:mm')}
                </span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'audit' && (
          <AuditTimeline entries={entries} />
        )}
      </div>
    </Layout>
  )
}
