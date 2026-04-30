/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The hunter loop runs entirely client-side; no server data fetching.
  // For static export later (GH Pages / Vercel static), set output: 'export'.
  // Leave dynamic for now to keep dev simple.
  webpack: (config, { isServer }) => {
    config.experiments = { ...config.experiments, asyncWebAssembly: true };

    if (!isServer) {
      // WasmBoy's package.json has "browser": UMD which webpack picks over
      // "module": ESM. The UMD bundle fails to chunk-split. Force ESM.
      config.resolve.alias = {
        ...config.resolve.alias,
        wasmboy: require.resolve('wasmboy/dist/wasmboy.wasm.esm.js'),
      };
    }

    return config;
  },
};

module.exports = nextConfig;
