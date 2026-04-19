// src/components/StatCard.tsx
import { clsx } from 'clsx'

interface StatCardProps {
  label: string
  value: string | number
  unit?: string
  delta?: string
  deltaPositive?: boolean
  accent?: 'amber' | 'green' | 'red' | 'blue'
  sub?: string
}

const ACCENT_COLORS = {
  amber: 'text-amber-400',
  green: 'text-emerald-400',
  red:   'text-red-400',
  blue:  'text-sky-400',
}

export function StatCard({
  label,
  value,
  unit,
  delta,
  deltaPositive,
  accent = 'amber',
  sub,
}: StatCardProps) {
  return (
    <div className="border-crt p-4 card-hover animate-fade-up">
      <p className="font-mono text-2xs tracking-[0.2em] text-ink-muted uppercase mb-3">{label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className={clsx('stat-num text-3xl font-semibold', ACCENT_COLORS[accent])}>
          {value}
        </span>
        {unit && (
          <span className="font-mono text-sm text-ink-muted">{unit}</span>
        )}
      </div>
      <div className="flex items-center justify-between mt-2">
        {sub && <p className="font-mono text-2xs text-ink-muted">{sub}</p>}
        {delta && (
          <span className={clsx(
            'font-mono text-2xs ml-auto',
            deltaPositive ? 'text-emerald-400' : 'text-red-400'
          )}>
            {deltaPositive ? '▲' : '▼'} {delta}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Mini bar chart ─────────────────────────────────────────────────────────

interface MiniBarProps {
  data: number[]
  color?: string
  height?: number
}

export function MiniBar({ data, color = '#f59e0b', height = 32 }: MiniBarProps) {
  const max = Math.max(...data, 1)
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${data.length * 8} ${height}`}
      preserveAspectRatio="none" className="w-full">
      {data.map((v, i) => {
        const barH = Math.max(2, (v / max) * height)
        return (
          <rect
            key={i}
            x={i * 8}
            y={height - barH}
            width={6}
            height={barH}
            fill={color}
            opacity={0.3 + (v / max) * 0.7}
          />
        )
      })}
    </svg>
  )
}
