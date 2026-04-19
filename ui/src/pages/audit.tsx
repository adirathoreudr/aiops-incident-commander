// src/pages/audit.tsx
import Layout from '@/components/Layout'
import AuditTimeline from '@/components/AuditTimeline'
import { useAudit } from '@/lib/api'

export default function AuditPage() {
  const { entries } = useAudit()

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="font-mono text-lg font-semibold text-ink-primary tracking-wide">
          AUDIT LOG
        </h1>
        <p className="font-mono text-xs text-ink-muted mt-1">
          Immutable record of every AI decision, action, and approval — {entries.length} entries
        </p>
      </div>

      <div className="border-crt p-6">
        <div className="flex items-center gap-3 mb-6">
          <p className="font-mono text-2xs tracking-widest text-amber-500/80">◈ ALL EVENTS — NEWEST FIRST</p>
          <span className="font-mono text-2xs text-ink-muted ml-auto">30-day retention</span>
        </div>
        <AuditTimeline entries={entries} />
      </div>

      {/* Compliance note */}
      <div className="mt-6 border-crt p-4" style={{ borderColor: 'rgba(245,158,11,0.15)' }}>
        <p className="font-mono text-2xs text-ink-muted leading-relaxed">
          <span className="text-amber-500/70">◈ COMPLIANCE: </span>
          Every automated action records: timestamp (UTC), incident ID, action type, target resource, actor (executor or approver name), success status, and outcome message.
          No action is executed without a corresponding audit entry. Records are append-only with 30-day retention in Redis and optionally streamed to S3.
        </p>
      </div>
    </Layout>
  )
}
