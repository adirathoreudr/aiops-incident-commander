// src/pages/api/executor/[...path].ts
//
// Server-side proxy to the executor.
//
// This is an API route rather than a next.config.js rewrite because rewrites
// cannot add request headers, and the executor's bearer token must never reach
// the browser. Anything shipped to the client is readable by the person holding
// it, so a token embedded in the bundle would authenticate every visitor to a
// cluster-mutation endpoint — which is the hole this proxy exists to close, not
// to relocate.
//
// The token is read from EXECUTOR_API_TOKEN, which is a server-only variable
// (no NEXT_PUBLIC_ prefix), so Next will refuse to inline it into client code.
import type { NextApiRequest, NextApiResponse } from 'next'

const EXECUTOR_URL = process.env.EXECUTOR_URL || 'http://localhost:8002'
const EXECUTOR_API_TOKEN = process.env.EXECUTOR_API_TOKEN || ''

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const segments = Array.isArray(req.query.path) ? req.query.path : [req.query.path ?? '']
  const search = req.url?.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''
  const target = `${EXECUTOR_URL}/${segments.join('/')}${search}`

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (EXECUTOR_API_TOKEN) {
    headers.Authorization = `Bearer ${EXECUTOR_API_TOKEN}`
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
    // Surface this as a distinct status so the dashboard can say "the executor
    // is unreachable" rather than implying the request was refused.
    res.status(502).json({
      detail: `Cannot reach executor at ${EXECUTOR_URL}`,
    })
  }
}
