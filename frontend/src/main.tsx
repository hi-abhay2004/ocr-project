import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

/**
 * With VITE_USE_MSW=true the whole app runs against in-browser mock handlers
 * (src/tests/mocks/handlers.ts) — no Django, no Postgres, no NIM key. This is
 * what lets the frontend track build ahead of Phase 4 (FRONTEND_PLAN §12).
 */
async function start() {
  if (import.meta.env.VITE_USE_MSW === 'true') {
    const { worker } = await import('./tests/mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void start()
