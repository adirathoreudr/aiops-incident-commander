/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The browser talks only to this origin; Next proxies through to the
  // services. Keeping the hop server-side means service URLs (and, once the
  // executor is authenticated, its token) never reach the client.
  async rewrites() {
    const collector = process.env.COLLECTOR_URL || 'http://localhost:8000'
    const executor = process.env.EXECUTOR_URL || 'http://localhost:8002'
    return [
      {
        source: '/api/collector/:path*',
        destination: `${collector}/:path*`,
      },
      {
        // Approvals and the audit trail live on the executor. Without this
        // rule the approve button and the audit tab resolved to nothing.
        source: '/api/executor/:path*',
        destination: `${executor}/:path*`,
      },
    ]
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
        ],
      },
    ]
  },
}

module.exports = nextConfig
