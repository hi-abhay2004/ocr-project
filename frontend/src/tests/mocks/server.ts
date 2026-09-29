import { setupServer } from 'msw/node'
import { handlers } from './handlers'

/** Node-side MSW for Vitest. Individual tests override with server.use(...). */
export const server = setupServer(...handlers)
