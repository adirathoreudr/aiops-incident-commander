// src/components/Layout.tsx
import Link from 'next/link'
import { useRouter } from 'next/router'
import { clsx } from 'clsx'

const NAV = [
  { href: '/',          label: 'OVERVIEW' },
  { href: '/dashboard', label: 'INCIDENTS' },
  { href: '/audit',     label: 'AUDIT LOG' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useRouter()

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

          {/* Right: live indicator */}
          <div className="ml-auto flex items-center gap-2">
            <span className="pulse-dot text-emerald-400" style={{ background: '#22c55e' }} />
            <span className="font-mono text-2xs text-ink-muted tracking-widest">LIVE</span>
            <span className="font-mono text-2xs text-ink-muted ml-4 hidden sm:block">
              {new Date().toUTCString().slice(0, 25)}Z
            </span>
          </div>
        </div>
      </header>

      {/* Demo banner */}
      <div className="border-b" style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)' }}>
        <div className="max-w-screen-xl mx-auto px-6 py-1.5 flex items-center gap-3">
          <span className="font-mono text-2xs text-amber-500 tracking-widest">◈ DEMO MODE</span>
          <span className="font-mono text-2xs text-ink-muted">Simulated incident data — no live cluster required</span>
          <a
            href="https://github.com/your-org/aiops-incident-commander"
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
