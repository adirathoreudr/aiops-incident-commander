// src/pages/api/collector/[...path].ts
//
// Server-side proxy to the collector.
//
// Mirrors the executor proxy. This was a next.config.js rewrite until the
// collector's read endpoints gained a token: rewrites cannot add request
// headers, and incident bodies carry captured log lines and root-cause text, so
// they should not be readable by anyone who can reach the port.
//
// COLLECTOR_API_TOKEN has no NEXT_PUBLIC_ prefix, so Next will not inline it
// into client code. A token in the bundle would authenticate every visitor,
// which relocates the exposure rather than removing it.
import type { NextApiRequest, NextApiResponse } from 'next'

const COLLECTOR_URL = process.env.COLLECTOR_URL || 'http://localhost:8000'
const COLLECTOR_API_TOKEN = process.env.COLLECTOR_API_TOKEN || ''

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path ?? '']
  const search = req.url?.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''
  const target = `${COLLECTOR_URL}/${segments.join('/')}${search}`

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (COLLECTOR_API_TOKEN) {
    headers.Authorization = `Bearer ${COLLECTOR_API_TOKEN}`
  }

  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : JSON.stringify(req.body),
    })

    const text = await upstream.text()
    res.status(upstream.status)
    res.setHeader('Content-Type', upstream.headers.get('content-type') ?? 'application/json')
    res.send(text)
  } catch (e) {
    // Distinct status so the dashboard can report "collector unreachable"
    // rather than implying the request was refused.
    res.status(502).json({
      detail: `Cannot reach collector at ${COLLECTOR_URL}`,
    })
  }
}
