import type { AppProps } from 'next/app'
import Head from 'next/head'
import '../styles/globals.css'

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>AIOps Incident Commander</title>
        <meta name="description" content="Autonomous AI incident detection, root-cause analysis, and safe remediation for Kubernetes" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta property="og:title" content="AIOps Incident Commander" />
        <meta property="og:description" content="AI-powered Kubernetes incident response — detect, triage, remediate." />
        <meta property="og:type" content="website" />
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%23070709'/><circle cx='16' cy='16' r='10' fill='none' stroke='%23f59e0b' stroke-width='2'/><circle cx='16' cy='16' r='4' fill='%23f59e0b'/></svg>" />
      </Head>
      <Component {...pageProps} />
    </>
  )
}
