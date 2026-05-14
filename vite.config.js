import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Build outputs into `dist/` (Vite default). kerf-api serves it via
// StaticFiles at runtime. In dev, Vite serves :5173 directly (HMR) and
// proxies /api + /auth to kerf-server on VITE_API_URL.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8080'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: apiUrl, changeOrigin: true },
        '/auth': { target: apiUrl, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          // Split the heaviest deps into their own chunks so first paint
          // doesn't drag in Monaco / three.js / JSCAD up-front. occt-import-js,
          // jspdf, and svg2pdf are already dynamically imported and chunk
          // automatically — listing them here would force them eager.
          //
          // Rolldown (Vite 8) requires the function form; the legacy object
          // form throws "manualChunks is not a function".
          manualChunks(id) {
            if (id.includes('node_modules/@monaco-editor/react')) return 'monaco'
            if (id.includes('node_modules/monaco-editor')) return 'monaco'
            if (id.includes('node_modules/occt-import-js')) return 'occt'
            // opencascade.js is the heavyweight Phase 2 OCCT B-rep kernel
            // (~15MB compressed gzipped wasm + glue). Keep it in its own
            // chunk so first paint of non-feature files doesn't drag it in.
            if (id.includes('node_modules/opencascade.js')) return 'opencascade'
            if (id.includes('node_modules/jspdf')) return 'pdf'
            if (id.includes('node_modules/svg2pdf.js')) return 'pdf'
            if (id.includes('node_modules/html2canvas')) return 'pdf'
            // three.js + JSCAD + BVH share a chunk: they're always loaded
            // together by Renderer/jscadRunner.
            if (id.includes('node_modules/three/')) return 'three'
            if (id.includes('node_modules/three-mesh-bvh')) return 'three'
            if (id.includes('node_modules/@jscad/modeling')) return 'three'
            if (id.includes('node_modules/react-markdown')) return 'markdown'
            if (id.includes('node_modules/remark-gfm')) return 'markdown'
            if (id.includes('node_modules/rehype-highlight')) return 'markdown'
            if (id.includes('node_modules/highlight.js')) return 'markdown'
            // tscircuit and its support packages are large (4MB+ uncompressed)
            // and ONLY needed for `.circuit.tsx` files. Both circuit-to-svg
            // (used by SchematicView/PCBView) and the worker's tscircuit
            // import live in this chunk so opening a non-circuit file never
            // drags in the electronics stack. The chunk is lazy-loaded via
            // the worker boundary; SchematicView/PCBView import the much
            // smaller circuit-to-svg directly, so we let it ride along here.
            if (id.includes('node_modules/tscircuit')) return 'tscircuit'
            if (id.includes('node_modules/@tscircuit/')) return 'tscircuit'
            if (id.includes('node_modules/circuit-json')) return 'tscircuit'
            if (id.includes('node_modules/circuit-to-svg')) return 'tscircuit'
            if (id.includes('node_modules/sucrase')) return 'tscircuit'
            return null
          },
        },
      },
    },
    optimizeDeps: {
      include: ['three', '@jscad/modeling'],
      // opencascade.js ships a .wasm asset alongside its JS shim. Vite/Rolldown
      // tries to introspect the package's exports during pre-bundle, follows
      // the binary, and chokes ("Could not load …/opencascade.wasm.wasm").
      // Excluding it from optimizeDeps + treating the .wasm as a static asset
      // (assetsInclude below) lets the worker import the URL via `?url` and
      // hand it to OCCT's `locateFile` hook at runtime.
      //
      // @salusoft89/planegcs has the same shape: emscripten glue + a sibling
      // .wasm. We pass the asset URL through `?url` in sketchSolver.js; mark
      // it excluded from pre-bundling so the dev server doesn't try to evaluate
      // the wasm itself as ESM.
      exclude: ['opencascade.js', '@salusoft89/planegcs'],
    },
    assetsInclude: ['**/*.wasm'],
  }
})
