/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required by the production Dockerfile. Without this, `.next/standalone` is
  // not generated and the runner stage cannot copy server.js.
  output: 'standalone',
  experimental: {
    // Keep static-generation workers bounded on hosts that expose a very high CPU count.
    cpus: 2,
    // Trace only this frontend workspace; do not scan sibling artifacts under /mnt/data.
    outputFileTracingRoot: __dirname,
  },
}

module.exports = nextConfig
