// src/pages/index.tsx
import Link from 'next/link'
import { clsx } from 'clsx'
import Layout from '@/components/Layout'
import { StatCard } from '@/components/StatCard'
import { useStats } from '@/lib/api'

const STACK = [
  { cat: 'PLATFORM',       items: ['AWS EKS', 'Terraform', 'ArgoCD', 'Helm'] },
  { cat: 'OBSERVABILITY',  items: ['Prometheus', 'Alertmanager', 'Loki', 'Grafana'] },
  { cat: 'AI / AGENT',     items: ['Python', 'LangChain', 'OpenAI', 'FAISS'] },
  { cat: 'AUTOMATION',     items: ['K8s Python Client', 'kubectl', 'ArgoCD REST', 'Webhooks'] },
  { cat: 'SECURITY',       items: ['RBAC', 'Network Policies', 'Trivy', 'Secrets Manager'] },
  { cat: 'CI/CD',          items: ['GitHub Actions', 'Docker', 'ECR', 'ArgoCD GitOps'] },
]

const PHASES = [
  { num: '01', title: 'Telemetry Ingestion',     desc: 'Alertmanager webhook → normalize alerts, pull Loki logs, fetch rollout history → canonical IncidentContext object' },
  { num: '02', title: 'AI Reasoning',            desc: 'LangChain agent retrieves similar incidents + runbooks via FAISS, prompts LLM with structured evidence, returns typed hypothesis' },
  { num: '03', title: 'Policy Gate',             desc: 'Confidence threshold check, namespace allowlist, action allowlist. High-risk actions route to human approval queue' },
  { num: '04', title: 'Safe Remediation',        desc: 'Kubernetes Python client executes restart/scale. ArgoCD REST API triggers rollback. Post-action health polling confirms recovery' },
  { num: '05', title: 'Audit & Observability',   desc: 'Every decision, approval, and action appended atomically to a Redis list, so concurrent writers cannot overwrite each other. Prometheus metrics on all services' },
]

export default function Home() {
  const { stats } = useStats()

  return (
    <Layout>
      {/* Hero */}
      <section className="pt-8 pb-16 relative">
        {/* Amber glow behind title */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(ellipse, rgba(245,158,11,0.08) 0%, transparent 70%)' }} />

        <div className="relative">
          <p className="font-mono text-2xs tracking-[0.3em] text-amber-500/70 mb-4 uppercase">
            Portfolio Project · AIOps · Kubernetes
          </p>
          <h1 className="font-display text-5xl md:text-6xl text-ink-primary leading-tight mb-2">
            Autonomous Incident
            <br />
            <em className="text-glow-amber text-amber-400 not-italic">Commander</em>
          </h1>
          <p className="font-mono text-sm text-ink-secondary mt-6 max-w-xl leading-relaxed">
            AI-powered incident detection, root-cause analysis, and safe remediation for Kubernetes.
            Alerts are correlated into incidents, reasoned over with cited evidence, and remediated
            through an allowlist of reversible actions — with every decision recorded.
          </p>

          <div className="flex items-center gap-4 mt-8">
            <Link
              href="/dashboard"
              className="font-mono text-xs px-5 py-2.5 bg-amber-400 text-surface-base font-semibold tracking-widest hover:bg-amber-300 transition-colors"
            >
              ▶ OPEN DASHBOARD
            </Link>
            <a
              href="https://github.com/adirathoreudr/aiops-incident-commander"
              target="_blank" rel="noreferrer"
              className="font-mono text-xs px-5 py-2.5 border border-surface-border text-ink-secondary hover:text-ink-primary hover:border-amber-400/40 transition-all tracking-widest"
            >
              ↗ SOURCE CODE
            </a>
          </div>
        </div>
      </section>

      {/* Current state, counted from the incidents the collector is holding.
          This block used to advertise MTTR improvement, alert-noise reduction
          and an auto-resolved rate under a heading that read LIVE. Every one of
          those numbers was a hardcoded literal — nothing in the platform has
          ever measured them. */}
      <section className="mb-16">
        <p className="font-mono text-2xs tracking-[0.25em] text-ink-muted uppercase mb-4">
          ◈ CURRENT STATE
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="OPEN"      value={stats.total_open}        accent="red"   sub="active incidents" />
          <StatCard label="CRITICAL"  value={stats.critical_count}    accent="red"   sub="need attention" />
          <StatCard label="AWAITING"  value={stats.awaiting_approval} accent="amber" sub="need approval" />
          <StatCard label="RESOLVED"  value={stats.resolved}          accent="green" sub="in retained window" />
        </div>
      </section>

      {/* Architecture flow */}
      <section className="mb-16">
        <p className="font-mono text-2xs tracking-[0.25em] text-ink-muted uppercase mb-6">
          ◈ CONTROL LOOP ARCHITECTURE
        </p>
        <div className="border-crt p-6 relative overflow-hidden">
          {/* BG grid accent */}
          <div className="absolute inset-0 bg-grid opacity-20" />
          <div className="relative space-y-0">
            {PHASES.map((phase, i) => (
              <div key={phase.num} className="flex gap-5 group">
                <div className="flex flex-col items-center">
                  <div className={clsx(
                    'w-8 h-8 flex items-center justify-center font-mono text-xs font-bold border shrink-0',
                    'transition-all group-hover:border-amber-400/60 group-hover:text-amber-400',
                    'border-surface-border text-ink-muted'
                  )}>
                    {phase.num}
                  </div>
                  {i < PHASES.length - 1 && (
                    <div className="w-px flex-1 min-h-[28px]" style={{ background: 'var(--surface-border)' }} />
                  )}
                </div>
                <div className="pb-6 pt-1 flex-1">
                  <p className="font-mono text-xs font-semibold text-ink-primary tracking-wide mb-1">
                    {phase.title}
                  </p>
                  <p className="font-mono text-xs text-ink-muted leading-relaxed">
                    {phase.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Tech stack */}
      <section className="mb-16">
        <p className="font-mono text-2xs tracking-[0.25em] text-ink-muted uppercase mb-6">
          ◈ TECHNOLOGY STACK
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {STACK.map(({ cat, items }) => (
            <div key={cat} className="border-crt p-4 card-hover">
              <p className="font-mono text-2xs tracking-widest text-amber-500/80 mb-3">{cat}</p>
              <div className="flex flex-wrap gap-1.5">
                {items.map(item => (
                  <span key={item} className="font-mono text-2xs px-2 py-1 text-ink-secondary"
                    style={{ background: 'var(--surface-raised)', border: '1px solid var(--surface-border)' }}>
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Outcomes */}
      <section className="mb-12">
        <p className="font-mono text-2xs tracking-[0.25em] text-ink-muted uppercase mb-6">
          ◈ BUSINESS OUTCOMES
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          {[
            ['◎', 'Alert correlation', 'Related alerts are fingerprinted and grouped into a single incident rather than paging separately'],
            ['◎', 'Evidence-backed triage', 'Root-cause hypotheses cite the specific logs, alerts and rollout events they rest on'],
            ['◎', 'Auditability', 'Every decision, approval, and action appended atomically to a log writers cannot overwrite'],
            ['◎', 'Human control preserved', 'High-risk actions require explicit approval, and the model can only ever escalate to review, never away from it'],
            ['◎', 'Policy-gated execution', 'Allowlist-only actions. Blocked namespaces. Confidence thresholds enforced. Approval is not an override.'],
            ['◎', 'No shell access required', 'Remediation is limited to reversible, parameterised actions through the Kubernetes API'],
          ].map(([icon, title, desc]) => (
            <div key={title as string} className="border-crt p-4 card-hover flex gap-3">
              <span className="text-amber-400 font-mono text-sm mt-0.5 shrink-0">{icon}</span>
              <div>
                <p className="font-mono text-xs font-semibold text-ink-primary mb-1">{title}</p>
                <p className="font-mono text-xs text-ink-muted leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-crt p-8 text-center relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at 50% 100%, rgba(245,158,11,0.06) 0%, transparent 60%)' }} />
        <p className="font-mono text-2xs tracking-[0.3em] text-amber-500/70 uppercase mb-3">
          ◈ READY TO EXPLORE
        </p>
        <h2 className="font-display text-3xl text-ink-primary mb-4">
          See it in action
        </h2>
        <p className="font-mono text-sm text-ink-secondary mb-8 max-w-md mx-auto">
          Open the incident dashboard to see live AI triage, confidence scoring, and remediation decisions from the collector.
        </p>
        <Link
          href="/dashboard"
          className="font-mono text-sm px-8 py-3 bg-amber-400 text-surface-base font-semibold tracking-widest hover:bg-amber-300 transition-colors inline-block"
        >
          OPEN DASHBOARD →
        </Link>
      </section>
    </Layout>
  )
}
