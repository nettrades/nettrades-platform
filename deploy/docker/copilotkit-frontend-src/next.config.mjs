/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_COPILOTKIT_URL: process.env.NEXT_PUBLIC_COPILOTKIT_URL,
    NEXT_PUBLIC_AUTH_ENABLED: process.env.NEXT_PUBLIC_AUTH_ENABLED || 'false',
  },
};

export default nextConfig;