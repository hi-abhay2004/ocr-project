import { Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { HOME_FOR_ROLE } from './AuthContext'
import { useAuth } from './useAuth'
import type { Role } from '@/types/api'

/**
 * Route guard — FRONTEND_PLAN §5.
 *
 * This is UX, NOT security. It mirrors the DRF permission classes so the user
 * never sees a screen they'd only get a 403 from, but the guard runs in the
 * user's own browser and is therefore trivially bypassed. Every endpoint must
 * enforce the same boundary server-side. Never move a check here from there.
 */
export function ProtectedRoute({
  requiredRole,
  children,
}: {
  requiredRole?: Role
  children: React.ReactNode
}) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  // Must not redirect while the session restore is still in flight, or every
  // hard refresh bounces a logged-in user to /login.
  if (isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    )
  }

  if (!user) {
    // `state.from` lets Login send them back where they were aiming.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  if (requiredRole && user.role !== requiredRole) {
    return <Navigate to={HOME_FOR_ROLE[user.role]} replace />
  }

  return <>{children}</>
}
