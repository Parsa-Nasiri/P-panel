/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  transpilePackages: ["@proxy/core", "@proxy/database", "@proxy/shared"],
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
