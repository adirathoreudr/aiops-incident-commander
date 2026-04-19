// src/components/AuditTimeline.tsx
import { clsx } from 'clsx'
import { format } from 'date-fns'
import { AuditEntry } from '@/lib/types'

const EVENT_STYLES: Record<string, { dot: string; label: string }> = {
  reasoning_complete: { dot: 'bg-amber-400',    label: 'AI REASONED' },
  action_executed:    { dot: 'bg-sky-400',       label: 'ACTION' },
  approval_decision:  { dot: 'bg-violet-400',    label: 'APPROVAL' },
  default:            { dot: 'bg-surface-muted', label: 'EVENT' },
}

export default function AuditTimeline({ entries }: { entries: AuditEntry[] }) {
  const sorted = [...entries].sort((a, b) =>
    new Date(b.ts).getTime() - new Date(a.ts).getTime()
  )

  if (sorted.length === 0) {
    return (
      <div className="font-mono text-xs text-ink-muted py-8 text-center">
        NO AUDIT ENTRIES
      </div>
    )
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-3 top-0 bottom-0 w-px" style={{ background: 'var(--surface-border)' }} />

      <div className="space-y-0">
        {sorted.map((entry, idx) => {
          const style = EVENT_STYLES[entry.event_type] ?? EVENT_STYLES.default
          const ts = format(new Date(entry.ts), 'HH:mm:ss')

          return (
            <div key={idx} className="relative pl-8 py-3 group">
              {/* Dot */}
              <div className={clsx(
                'absolute left-1.5 top-4 w-3 h-3 rounded-full border-2 transition-transform group-hover:scale-125',
                style.dot,
                'border-surface-base',
              )} />

              <div className="flex items-start gap-3">
                {/* Time */}
                <span className="font-mono text-2xs text-ink-muted shrink-0 pt-0.5 w-14">{ts}</span>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-2xs font-semibold text-ink-accent tracking-wide">
                      {style.label}
                    </span>

                    {entry.event_type === 'reasoning_complete' && (
                      <>
                        <span className="font-mono text-2xs text-ink-muted">
                          type={entry.incident_type}
                        </span>
                        <span className={clsx(
                          'font-mono text-2xs',
                          (entry.confidence_score ?? 0) >= 0.75 ? 'text-emerald-400' : 'text-amber-400'
                        )}>
                          conf={Math.round((entry.confidence_score ?? 0) * 100)}%
                        </span>
                        <span className="font-mono text-2xs text-sky-400">
                          → {entry.recommended_action}
                        </span>
                        {entry.requires_approval && (
                          <span className="font-mono text-2xs text-amber-500">⏸ needs approval</span>
                        )}
                      </>
                    )}

                    {entry.event_type === 'action_executed' && (
                      <>
                        <span className="font-mono text-2xs text-sky-400">{entry.action_type}</span>
                        <span className="font-mono text-2xs text-ink-muted">{entry.target}</span>
                        <span className="font-mono text-2xs text-ink-muted">by {entry.actor}</span>
                        <span className={clsx(
                          'font-mono text-2xs font-semibold',
                          entry.success ? 'text-emerald-400' : 'text-red-400'
                        )}>
                          {entry.success ? '✓ SUCCESS' : '✗ FAILED'}
                        </span>
                      </>
                    )}

                    {entry.event_type === 'approval_decision' && (
                      <>
                        <span className={clsx(
                          'font-mono text-2xs font-semibold',
                          entry.approved ? 'text-emerald-400' : 'text-red-400'
                        )}>
                          {entry.approved ? 'APPROVED' : 'REJECTED'}
                        </span>
                        <span className="font-mono text-2xs text-ink-muted">by {entry.approver}</span>
                        <span className="font-mono text-2xs text-ink-muted">action={entry.action_type}</span>
                      </>
                    )}
                  </div>

                  {entry.result && (
                    <p className="font-mono text-2xs text-ink-muted mt-1 line-clamp-1">{entry.result}</p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
