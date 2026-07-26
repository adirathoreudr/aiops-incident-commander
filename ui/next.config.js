/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No rewrites: both services are proxied by API routes under
  // src/pages/api/, because each needs an Authorization header attached
  // server-side and a rewrite cannot add request headers. Keeping the tokens
  // out of the bundle is the whole point — anything shipped to the browser is
  // readable by whoever holds it.
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
