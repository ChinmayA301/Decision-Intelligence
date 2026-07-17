/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    // Briefs can take >30s when the LLM provider rate-limits and we retry;
    // the dev proxy's default 30s timeout would kill the request mid-pipeline.
    proxyTimeout: 180_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
