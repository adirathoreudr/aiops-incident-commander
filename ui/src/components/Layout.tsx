// src/components/Layout.tsx
import Link from 'next/link'
import { useRouter } from 'next/router'
import { clsx } from 'clsx'
import { useIncidents } from '@/lib/api'

const NAV = [
  { href: '/',          label: 'OVERVIEW' },
  { href: '/dashboard', label: 'INCIDENTS' },
  { href: '/audit',     label: 'AUDIT LOG' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useRouter()
  const { error } = useIncidents()

  return (
    <div className="min-h-screen bg-grid" style={{ backgroundSize: '40px 40px' }}>
      {/* Top bar */}
      <header className="sticky top-0 z-50 border-b border-crt" style={{ background: 'rgba(7,7,9,0.95)', backdropFilter: 'blur(12px)' }}>
        <div className="max-w-screen-xl mx-auto px-6 h-12 flex items-center gap-8">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 shrink-0 group">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <circle cx="11" cy="11" r="9" stroke="#f59e0b" strokeWidth="1.5" />
              <circle cx="11" cy="11" r="4.5" stroke="#f59e0b" strokeWidth="1.5" />
              <circle cx="11" cy="11" r="1.5" fill="#f59e0b" />
              <line x1="11" y1="2" x2="11" y2="5" stroke="#f59e0b" strokeWidth="1.5" />
              <line x1="11" y1="17" x2="11" y2="20" stroke="#f59e0b" strokeWidth="1.5" />
              <line x1="2" y1="11" x2="5" y2="11" stroke="#f59e0b" strokeWidth="1.5" />
              <line x1="17" y1="11" x2="20" y2="11" stroke="#f59e0b" strokeWidth="1.5" />
            </svg>
            <span className="font-mono text-xs font-semibold tracking-[0.2em] text-amber-400 group-hover:text-amber-300 transition-colors uppercase">
              AIC//
            </span>
          </Link>

          {/* Nav */}
          <nav className="flex items-center gap-1">
            {NAV.map(n => (
              <Link
                key={n.href}
                href={n.href}
                className={clsx(
                  'px-3 py-1 font-mono text-2xs tracking-widest transition-all',
                  pathname === n.href
                    ? 'text-amber-400 bg-amber-400/10 border border-amber-400/30'
                    : 'text-ink-secondary hover:text-ink-primary border border-transparent hover:border-surface-border'
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>

          {/* Right: connection indicator. Reflects whether the collector is
              actually answering — a status light that reads LIVE regardless of
              backend state tells an operator nothing. SWR dedupes this against
              the pages' own fetch, so it costs no extra request. */}
          <div className="ml-auto flex items-center gap-2">
            <span
              className={clsx('pulse-dot', error ? 'text-red-400' : 'text-emerald-400')}
              style={{ background: error ? '#ff3b3b' : '#22c55e' }}
            />
            <span className={clsx(
              'font-mono text-2xs tracking-widest',
              error ? 'text-red-400' : 'text-ink-muted'
            )}>
              {error ? 'DISCONNECTED' : 'LIVE'}
            </span>
            <span className="font-mono text-2xs text-ink-muted ml-4 hidden sm:block">
              {new Date().toUTCString().slice(0, 25)}Z
            </span>
          </div>
        </div>
      </header>

      {/* Source banner. This previously read "DEMO MODE — simulated incident
          data"; every page now renders whatever the collector is actually
          holding, so the banner would be asserting the opposite of the truth. */}
      <div className="border-b" style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-1.5 flex items-center gap-3">
          <span className="font-mono text-2xs text-amber-500 tracking-widest">◈ LIVE DATA</span>
          <span className="font-mono text-2xs text-ink-muted">
            Incidents served by the collector — an empty feed means no incidents, not a demo
          </span>
          <a
            href="https://github.com/adirathoreudr/aiops-incident-commander"
            target="_blank" rel="noreferrer"
            className="ml-auto font-mono text-2xs text-amber-500/70 hover:text-amber-400 transition-colors tracking-wide"
          >
            ↗ GitHub
          </a>
        </div>
      </div>

      <main className="max-w-screen-xl mx-auto px-6 py-8">
        {children}
      </main>
    </div>
  )
}
