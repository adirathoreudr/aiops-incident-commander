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
  { num: '05', title: 'Audit & Observability',   desc: 'Every prompt, decision, approval, and action appended to immutable audit log. Prometheus metrics on all services' },
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
            Reduces MTTR by 50%+. Cuts alert noise by 40%. Resolves 60%+ of common incidents without shell access.
          </p>

          <div className="flex items-center gap-4 mt-8">
            <Link
              href="/dashboard"
              className="font-mono text-xs px-5 py-2.5 bg-amber-400 text-surface-base font-semibold tracking-widest hover:bg-amber-300 transition-colors"
            >
              ▶ LIVE DEMO
            </Link>
            <a
              href="https://github.com/your-org/aiops-incident-commander"
              target="_blank" rel="noreferrer"
              className="font-mono text-xs px-5 py-2.5 border border-surface-border text-ink-secondary hover:text-ink-primary hover:border-amber-400/40 transition-all tracking-widest"
            >
              ↗ SOURCE CODE
            </a>
          </div>
        </div>
      </section>

      {/* Live stats */}
      <section className="mb-16">
        <p className="font-mono text-2xs tracking-[0.25em] text-ink-muted uppercase mb-4">
          ◈ PLATFORM METRICS — LIVE
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            label="MTTR IMPROVEMENT"
            value={stats.mttr_improvement_pct}
            unit="%"
            accent="green"
            delta="vs baseline"
            deltaPositive
            sub="simulated incidents"
          />
          <StatCard
            label="ALERT NOISE CUT"
            value={stats.noise_reduction_pct}
            unit="%"
            accent="amber"
            delta="via dedup + grouping"
            deltaPositive
            sub="dedup + grouping"
          />
          <StatCard
            label="AUTO-RESOLVED"
            value={stats.auto_resolved_pct}
            unit="%"
            accent="blue"
            sub="no manual shell access"
          />
          <StatCard
            label="AVG RESOLUTION"
            value={stats.avg_resolution_minutes}
            unit="min"
            accent="amber"
            sub="triage to close"
          />
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
            ['◎', 'Reduces MTTR', '50%+ reduction in mean time to resolve in simulated incidents'],
            ['◎', 'Cuts alert noise', '40%+ via deduplication and grouping of related alerts'],
            ['◎', 'Autonomous resolution', '60%+ of common incidents resolved without manual shell access'],
            ['◎', 'Auditability', 'Every prompt, decision, approval, and action logged with full traceability'],
            ['◎', 'Human control preserved', 'High-risk actions require explicit approval. Agent cannot call arbitrary tools.'],
            ['◎', 'Policy-gated execution', 'Allowlist-only actions. Blocked namespaces. Confidence thresholds enforced.'],
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
          Open the live incident dashboard to see AI triage, confidence scoring, and remediation decisions on simulated Kubernetes incidents.
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
