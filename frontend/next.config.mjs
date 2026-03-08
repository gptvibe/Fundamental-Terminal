/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/backend/:path*",
        destination: `${backend}/:path*`
      }
    ];
  }
};

export default nextConfig;
