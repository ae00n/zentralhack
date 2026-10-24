import type { NextConfig } from "next";

// No API routes and no next/image optimisation: all data and images come from the FastAPI backend
// (or public/fixtures in mock mode), and the demo must work offline.
const nextConfig: NextConfig = {
  images: { unoptimized: true },
};

export default nextConfig;
