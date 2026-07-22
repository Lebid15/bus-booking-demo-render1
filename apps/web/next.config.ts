import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    // Keep Production builds stable on high-core CI hosts instead of spawning
    // one page-data worker per visible CPU.
    cpus: 4,
  },
};

export default nextConfig;
