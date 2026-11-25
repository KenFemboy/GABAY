import { Navigate, Route, Routes as ReactRoutes } from 'react-router-dom'

import ProtectedRoute from '../auth/ProtectedRoute'
import { ROLES } from '../auth/roles'
import ChangePasswordPage from '../features/auth/ChangePasswordPage'
import LoginPage from '../features/auth/LoginPage'
import OcrReviewPage from '../features/assessments/OcrReviewPage'
import DashboardPage from '../features/dashboard/DashboardPage'
import { LEARNER_READER_ROLES } from '../features/learners/constants'
import LearnerProfilePage from '../features/learners/LearnerProfilePage'
import LearnersPage from '../features/learners/LearnersPage'
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

          <Route element={<ProtectedRoute roles={LEARNER_READER_ROLES} />}>
            <Route element={<LearnersPage />} path="/learners" />
            <Route element={<LearnerProfilePage />} path="/learners/:learnerId" />
            <Route element={<OcrReviewPage />} path="/learners/:learnerId/assessments/:assessmentId/review" />
          </Route>

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
