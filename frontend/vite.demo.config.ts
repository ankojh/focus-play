import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// Builds a standalone copy that opens from index.html over file://: relative paths and one classic script.
export default defineConfig({
  plugins: [react()], base: './', define: { 'import.meta.env.VITE_DEMO': JSON.stringify('1') },
  build: { outDir: 'dist-demo', emptyOutDir: true, modulePreload: false, cssCodeSplit: false,
    rollupOptions: { input: 'demo.html', output: { format: 'iife', entryFileNames: 'app.js', assetFileNames: 'app[extname]' } } },
});
