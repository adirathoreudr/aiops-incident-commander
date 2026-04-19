// src/components/IncidentCard.tsx
import Link from 'next/link'
import { clsx } from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { Incident } from '@/lib/types'

const SEV_ICONS: Record<string, string> = {
  critical: '◉',
  high:     '◈',
  warning:  '◇',
  info:     '○',
}

const ACTION_LABELS: Record<string, string> = {
  rollout_restart:  'RESTART',
  scale_up:         'SCALE ↑',
  scale_down:       'SCALE ↓',
  argocd_rollback:  'ROLLBACK',
  notify_only:      'NOTIFY',
}

export default function IncidentCard({ incident }: { incident: Incident }) {
  const conf = incident.confidence_score ?? 0
  const confPct = Math.round(conf * 100)
  const age = formatDistanceToNow(new Date(incident.created_at), { addSuffix: false })

  return (
    <Link href={`/incident/${incident.incident_id}`}>
      <article className={clsx(
        'card-hover border-crt p-4 cursor-pointer',
        'animate-fade-up',
        incident.status === 'resolved' && 'opacity-60',
      )}>
        {/* Header row */}
        <div className="flex items-start gap-3 mb-3">
          <span className={clsx('font-mono text-lg leading-none mt-0.5', `badge-${incident.severity}`)}
            title={incident.severity}>
            {SEV_ICONS[incident.severity] ?? '○'}
          </span>

          <div className="flex-1 min-w-0">
            <p className="font-mono text-xs font-semibold text-ink-primary leading-snug line-clamp-2">
              {incident.title}
            </p>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={clsx('font-mono text-2xs px-1.5 py-0.5', `badge-${incident.severity}`)}>
                {incident.severity.toUpperCase()}
              </span>
              <span className="font-mono text-2xs text-ink-muted">{incident.namespace}</span>
              {incident.service && (
                <span className="font-mono text-2xs text-ink-muted">/&nbsp;{incident.service}</span>
              )}
              {incident.grouped_alert_count > 1 && (
                <span className="font-mono text-2xs text-amber-500/70">
                  ×{incident.grouped_alert_count} grouped
                </span>
              )}
            </div>
          </div>

          {/* Status + age */}
          <div className="text-right shrink-0">
            <p className={clsx('font-mono text-2xs font-semibold tracking-wide', `status-${incident.status}`)}>
              {incident.status.replace('_', ' ').toUpperCase()}
            </p>
            <p className="font-mono text-2xs text-ink-muted mt-0.5">{age} ago</p>
          </div>
        </div>

        {/* Root cause */}
        {incident.probable_root_cause && (
          <p className="font-mono text-xs text-ink-secondary line-clamp-2 mb-3">
            {incident.probable_root_cause}
          </p>
        )}

        {/* Footer: confidence + action */}
        <div className="flex items-center gap-4">
          {/* Confidence */}
          <div className="flex-1">
            <div className="flex justify-between mb-1">
              <span className="font-mono text-2xs text-ink-muted">CONFIDENCE</span>
              <span className={clsx(
                'font-mono text-2xs font-semibold',
                conf >= 0.75 ? 'text-emerald-400' : conf >= 0.5 ? 'text-amber-400' : 'text-red-400'
              )}>
                {confPct}%
              </span>
            </div>
            <div className="confidence-bar" style={{ '--confidence': `${confPct}%` } as React.CSSProperties} />
          </div>

          {/* Recommended action */}
          {incident.recommended_action && (
            <div className="shrink-0">
              <span className={clsx(
                'font-mono text-2xs px-2 py-1 border',
                incident.requires_approval
                  ? 'text-amber-400 border-amber-400/30 bg-amber-400/5'
                  : 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5'
              )}>
                {ACTION_LABELS[incident.recommended_action] ?? incident.recommended_action}
                {incident.requires_approval ? ' ⏸' : ' ▶'}
              </span>
            </div>
          )}
        </div>
      </article>
    </Link>
  )
}
