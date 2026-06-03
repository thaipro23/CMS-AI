/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required by the production Dockerfile. Without this, `.next/standalone` is
  // not generated and the runner stage cannot copy server.js.
  output: 'standalone',
}

module.exports = nextConfig
