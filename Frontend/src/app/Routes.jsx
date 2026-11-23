import { Navigate, Route, Routes as ReactRoutes } from 'react-router-dom'

import ProtectedRoute from '../auth/ProtectedRoute'
import { ROLES } from '../auth/roles'
import ChangePasswordPage from '../features/auth/ChangePasswordPage'
import LoginPage from '../features/auth/LoginPage'
import DashboardPage from '../features/dashboard/DashboardPage'
import UsersPage from '../features/users/UsersPage'
import AuthLayout from '../layouts/AuthLayout'
import DashboardLayout from '../layouts/DashboardLayout'
import NotFoundPage from '../shared/components/NotFoundPage'

export default function Routes() {
  return (
    <ReactRoutes>
      <Route element={<AuthLayout />} path="/login">
        <Route element={<LoginPage />} index />
      </Route>

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route element={<DashboardPage />} path="/dashboard" />
          <Route element={<ChangePasswordPage />} path="/account/password" />

          <Route element={<ProtectedRoute roles={[ROLES.SYSTEM_ADMIN]} />}>
            <Route element={<UsersPage />} path="/admin/users" />
          </Route>
        </Route>
      </Route>

      <Route element={<Navigate replace to="/dashboard" />} path="/" />
      <Route element={<NotFoundPage />} path="*" />
    </ReactRoutes>
  )
}
