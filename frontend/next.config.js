/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required by the production Dockerfile. Without this, `.next/standalone` is
  // not generated and the runner stage cannot copy server.js.
  output: 'standalone',
  // ESLint is a separate required CI step; avoid running the same full scan twice during Docker/Next build.
  eslint: { ignoreDuringBuilds: true },
  // TypeScript is a separate required CI/Docker step; avoid duplicating a costly full-program check in Next build.
  typescript: { ignoreBuildErrors: true },
  experimental: {
    // Keep static-generation workers bounded on hosts that expose a very high CPU count.
    cpus: 2,
    // Trace only this frontend workspace; do not scan sibling artifacts under /mnt/data.
    outputFileTracingRoot: __dirname,
  },
}

module.exports = nextConfig
