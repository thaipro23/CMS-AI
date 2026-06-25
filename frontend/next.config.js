/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required by the production Dockerfile. Without this, `.next/standalone` is
  // generated and the runner stage can copy server.js.
  output: 'standalone',
  // The project intentionally does not ship a Next ESLint config yet. Keep
  // production builds non-interactive; run `npm run typecheck` as the hard gate.
  eslint: {
    ignoreDuringBuilds: true,
  },
}

module.exports = nextConfig
