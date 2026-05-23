/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export for GitHub Pages. `next build` will emit ./out
  output: "export",
  // GitHub Pages serves the repo as <user>.github.io/<repo>/ -- set the
  // path prefix via env so local dev (`npm run dev`) still works without it.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  assetPrefix: process.env.NEXT_PUBLIC_BASE_PATH || "",
  images: { unoptimized: true },
  trailingSlash: true,
  reactStrictMode: true,
};
module.exports = nextConfig;
