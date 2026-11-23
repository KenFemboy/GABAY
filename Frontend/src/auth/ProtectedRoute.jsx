import { Navigate, Outlet, useLocation } from 'react-router-dom'

import UnauthorizedPage from '../shared/components/UnauthorizedPage'
import useAuth from './useAuth'

/**
 * Usability layer only: hides pages the user cannot use. The backend still
 * enforces every permission.
 *
 * <ProtectedRoute />                     – any signed-in user
 * <ProtectedRoute roles={[ROLES.X]} />   – only the listed roles
 */
export default function ProtectedRoute({ roles }) {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        Checking your session…
      </div>
    )
  }

  if (!user) {
    return <Navigate replace state={{ from: location }} to="/login" />
  }

  if (roles && !roles.includes(user.role)) {
    return <UnauthorizedPage />
  }

  return <Outlet />
}
