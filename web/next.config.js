/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The hunter loop runs entirely client-side; no server data fetching.
  // For static export later (GH Pages / Vercel static), set output: 'export'.
  // Leave dynamic for now to keep dev simple.
  webpack: (config) => {
    // WasmBoy ships .wasm via fetch(); Next 15 handles that out of the box.
    // We only need to make sure the module isn't statically bundled into SSR.
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    return config;
  },
};

module.exports = nextConfig;
