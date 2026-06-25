import { execSync } from 'child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function gitVersion(): string {
  try {
    const sha = execSync('git rev-parse --short=8 HEAD', { encoding: 'utf8' }).trim()
    let tag = ''
    try { tag = execSync('git describe --tags --abbrev=0 2>/dev/null', { encoding: 'utf8', stdio: ['pipe','pipe','pipe'] }).trim() } catch {}
    const dirty = execSync('git status --porcelain -uno', { encoding: 'utf8' }).trim() !== ''
    const base = tag ? `${tag}-${sha}` : sha
    return dirty ? `${base}-dirty` : base
  } catch {
    return 'unknown'
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(gitVersion()),
  },
  server: {
    proxy: {
      '/api-proxy': {
        target: 'http://localhost:8765',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api-proxy/, ''),
      },
    },
  },
})
