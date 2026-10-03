/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  ...(process.env.NODE_ENV === "development" ? {
    async rewrites() {
      const api = process.env.ANCHOR_DEV_API_URL || "http://127.0.0.1:8000";
      return [{ source: "/chat-api/:path*", destination: `${api}/chat-api/:path*` }];
    },
  } : {}),
};

export default nextConfig;
