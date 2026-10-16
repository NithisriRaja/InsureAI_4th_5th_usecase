import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A stray lockfile higher up (e.g. in the home dir) would otherwise be picked as the root.
  outputFileTracingRoot: path.join(__dirname),
  turbopack: { root: path.join(__dirname) },
  devIndicators: false, // no floating Next.js badge in `npm run dev`
};

export default nextConfig;
