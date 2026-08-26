/** @type {import('next').NextConfig} */

// Where the FastAPI backend lives. The browser never talks to it directly:
// every call goes to /api/* on this Next server, which proxies it onward.
// That keeps the app working behind any reverse proxy / remote preview host
// (the browser is not always on the same machine as the backend).
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN || 'http://127.0.0.1:8000'

const nextConfig = {
  // Cross-origin dev requests (remote preview hosts, RDP over hostname, ...)
  allowedDevOrigins: ['*.e2b.app', '*.local', '*.localhost'],

  images: {
    unoptimized: true,
  },

  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_ORIGIN}/:path*`,
      },
    ]
  },
}

export default nextConfig
