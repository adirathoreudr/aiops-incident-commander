// src/pages/dashboard.tsx
import { useState } from 'react'
import { clsx } from 'clsx'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import Layout from '@/components/Layout'
import IncidentCard from '@/components/IncidentCard'
import { StatCard } from '@/components/StatCard'
import { useIncidents, useIncidentTimeline, useStats } from '@/lib/api'
import type { IncidentStatus, Severity } from '@/lib/types'

const FILTERS: { label: string; value: IncidentStatus | 'all' }[] = [
  { label: 'ALL',        value: 'all' },
  { label: 'OPEN',       value: 'open' },
  { label: 'IN TRIAGE',  value: 'in_triage' },
  { label: 'REMEDIATING',value: 'remediating' },
  { label: 'RESOLVED',   value: 'resolved' },
  { label: 'ESCALATED',  value: 'escalated' },
]

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="border-crt p-3" style={{ background: 'var(--surface-overlay)' }}>
      <p className="font-mono text-2xs text-ink-muted mb-1">{label}</p>
      <p className="font-mono text-2xs text-amber-400">incidents: {payload[0]?.value}</p>
      <p className="font-mono text-2xs text-emerald-400">resolved: {payload[1]?.value}</p>
    </div>
  )
}

export default function Dashboard() {
  const { incidents, isLoading, error } = useIncidents()
  const { stats } = useStats()
  const timeline = useIncidentTimeline()
  const [filter, setFilter] = useState<IncidentStatus | 'all'>('all')
  const [sevFilter, setSevFilter] = useState<Severity | 'all'>('all')

  const filtered = incidents.filter(i => {
    const statusOk = filter === 'all' || i.status === filter
    const sevOk    = sevFilter === 'all' || i.severity === sevFilter
    return statusOk && sevOk
  })

  return (
    <Layout>
      {/* Page header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="font-mono text-lg font-semibold text-ink-primary tracking-wide cursor">
            INCIDENT FEED
          </h1>
          <p className="font-mono text-xs text-ink-muted mt-1">
            {incidents.length} retained · {stats.critical_count} critical · {stats.resolved} resolved
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={clsx('pulse-dot', error ? 'text-red-400' : 'text-amber-400')}
            style={{ background: error ? '#ff3b3b' : '#f59e0b' }}
          />
          <span className={clsx(
            'font-mono text-2xs tracking-widest',
            error ? 'text-red-400' : 'text-amber-500/70'
          )}>
            {error ? 'COLLECTOR UNREACHABLE' : 'POLLING 5s'}
          </span>
        </div>
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <StatCard label="OPEN"       value={stats.total_open}        accent="red"   sub="active incidents" />
        <StatCard label="CRITICAL"   value={stats.critical_count}    accent="red"   sub="need attention" />
        <StatCard label="AWAITING"   value={stats.awaiting_approval} accent="amber" sub="need approval" />
        <StatCard label="RESOLVED"   value={stats.resolved}          accent="green" sub="in retained window" />
      </div>

      {/* Timeline chart */}
      <div className="border-crt p-5 mb-8">
        <p className="font-mono text-2xs tracking-widest text-ink-muted mb-4">
          ◈ INCIDENT VOLUME — RETAINED WINDOW
        </p>
        {timeline.length === 0 ? (
          <p className="font-mono text-xs text-ink-muted py-10 text-center">
            NO INCIDENT HISTORY TO PLOT
          </p>
        ) : (
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={timeline} margin={{ top: 0, right: 0, left: -24, bottom: 0 }}>
            <defs>
              <linearGradient id="incGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="resGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="time" tick={{ fontFamily: 'JetBrains Mono', fontSize: 9, fill: '#5c5850' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontFamily: 'JetBrains Mono', fontSize: 9, fill: '#5c5850' }} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="incidents" stroke="#f59e0b" strokeWidth={1.5} fill="url(#incGrad)" dot={false} />
            <Area type="monotone" dataKey="resolved"  stroke="#22c55e" strokeWidth={1.5} fill="url(#resGrad)" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
        )}
        <div className="flex gap-6 mt-2">
          <div className="flex items-center gap-2">
            <span className="w-6 h-px" style={{ background: '#f59e0b', display: 'inline-block' }} />
            <span className="font-mono text-2xs text-ink-muted">incidents</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-6 h-px" style={{ background: '#22c55e', display: 'inline-block' }} />
            <span className="font-mono text-2xs text-ink-muted">resolved</span>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap mb-6">
        <span className="font-mono text-2xs text-ink-muted mr-1">STATUS:</span>
        {FILTERS.map(f => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={clsx(
              'font-mono text-2xs px-2.5 py-1 border transition-all tracking-widest',
              filter === f.value
                ? 'border-amber-400/50 text-amber-400 bg-amber-400/10'
                : 'border-surface-border text-ink-muted hover:border-surface-muted hover:text-ink-secondary'
            )}
          >
            {f.label}
          </button>
        ))}

        <span className="font-mono text-2xs text-ink-muted ml-4 mr-1">SEV:</span>
        {(['all', 'critical', 'high', 'warning'] as const).map(s => (
          <button
            key={s}
            onClick={() => setSevFilter(s)}
            className={clsx(
              'font-mono text-2xs px-2.5 py-1 border transition-all tracking-widest uppercase',
              sevFilter === s
                ? `badge-${s === 'all' ? 'info' : s} opacity-100`
                : 'border-surface-border text-ink-muted hover:text-ink-secondary'
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Incident list.
          "The collector is down" and "nothing is on fire" look identical if
          both render as an empty list, and only one of them is good news. */}
      {error ? (
        <div className="border-crt p-12 text-center" style={{ borderColor: 'rgba(255,59,59,0.3)' }}>
          <p className="font-mono text-2xl text-red-400 mb-2">⚠</p>
          <p className="font-mono text-xs text-red-400 tracking-widest mb-2">CANNOT REACH COLLECTOR</p>
          <p className="font-mono text-2xs text-ink-muted">
            {error.message} — incidents cannot be listed, so this page is not
            evidence that the cluster is healthy.
          </p>
        </div>
      ) : isLoading ? (
        <div className="font-mono text-xs text-ink-muted py-16 text-center animate-pulse">
          CONNECTING TO COLLECTOR<span className="cursor" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="border-crt p-12 text-center">
          <p className="font-mono text-2xl text-emerald-400 mb-2">◎</p>
          <p className="font-mono text-xs text-ink-muted tracking-widest">
            {incidents.length === 0 ? 'NO ACTIVE INCIDENTS' : 'NO INCIDENTS MATCHING FILTER'}
          </p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3">
          {filtered.map(inc => (
            <IncidentCard key={inc.incident_id} incident={inc} />
          ))}
        </div>
      )}
    </Layout>
  )
}
