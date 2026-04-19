/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Core CRT amber palette
        amber: {
          50:  '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
        },
        // Surface tokens
        surface: {
          base:    '#070709',
          raised:  '#0d0d10',
          overlay: '#121218',
          border:  '#1e1e28',
          muted:   '#2a2a35',
        },
        // Signal colors
        signal: {
          critical: '#ff3b3b',
          high:     '#ff6b35',
          warning:  '#f59e0b',
          info:     '#38bdf8',
          ok:       '#22c55e',
          resolved: '#64748b',
        },
        // Text
        ink: {
          primary:  '#e8e4d9',
          secondary:'#9b9585',
          muted:    '#5c5850',
          accent:   '#f59e0b',
        },
      },
      fontFamily: {
        mono:    ['\'Berkeley Mono\'', '\'TX-02\'', '\'Fira Code\'', '\'JetBrains Mono\'', 'monospace'],
        display: ['\'Instrument Serif\'', '\'Playfair Display\'', 'serif'],
        sans:    ['\'DM Sans\'', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      spacing: {
        px: '1px',
        '0.5': '2px',
      },
      backgroundImage: {
        'scanline': 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.08) 2px, rgba(0,0,0,0.08) 4px)',
        'grid-dark': 'linear-gradient(rgba(30,30,40,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(30,30,40,0.6) 1px, transparent 1px)',
        'amber-glow': 'radial-gradient(ellipse at 50% 0%, rgba(245,158,11,0.12) 0%, transparent 60%)',
      },
      backgroundSize: {
        'grid': '32px 32px',
      },
      animation: {
        'pulse-slow':   'pulse 3s cubic-bezier(0.4,0,0.6,1) infinite',
        'blink':        'blink 1.2s step-end infinite',
        'slide-in':     'slideIn 0.3s ease-out',
        'fade-up':      'fadeUp 0.4s ease-out',
        'scanline-move':'scanlineMove 8s linear infinite',
        'flicker':      'flicker 0.15s infinite',
      },
      keyframes: {
        blink:    { '0%,100%': { opacity: 1 }, '50%': { opacity: 0 } },
        slideIn:  { from: { transform: 'translateX(-8px)', opacity: 0 }, to: { transform: 'translateX(0)', opacity: 1 } },
        fadeUp:   { from: { transform: 'translateY(8px)', opacity: 0 }, to: { transform: 'translateY(0)', opacity: 1 } },
        scanlineMove: { from: { backgroundPosition: '0 0' }, to: { backgroundPosition: '0 100%' } },
        flicker: { '0%,100%': { opacity: 1 }, '33%': { opacity: 0.97 }, '66%': { opacity: 0.99 } },
      },
      boxShadow: {
        'amber': '0 0 20px rgba(245,158,11,0.15)',
        'amber-sm': '0 0 8px rgba(245,158,11,0.2)',
        'critical': '0 0 12px rgba(255,59,59,0.25)',
        'inset-border': 'inset 0 0 0 1px rgba(245,158,11,0.15)',
      },
    },
  },
  plugins: [],
}
