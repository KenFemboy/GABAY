import { Navigate, Route, Routes as ReactRoutes } from 'react-router-dom'

import AuthLayout from '../layouts/AuthLayout'
import DashboardLayout from '../layouts/DashboardLayout'

function Login() {
  return (
    <section className="mx-auto max-w-md rounded-xl bg-white p-8 shadow">
      <h1 className="text-2xl font-bold text-slate-900">Sign in to GABAY</h1>
      <p className="mt-2 text-slate-600">Authentication will be connected in a later stage.</p>
      <button className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white" type="button">
        Continue as placeholder
      </button>
    </section>
  )
}

function Dashboard() {
  return (
    <div>
      <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
      <p className="mt-2 text-slate-600">Your GABAY workspace is ready.</p>
    </div>
  )
}

function NotFound() {
  return <p className="text-center text-slate-600">The page you requested was not found.</p>
}

export default function Routes() {
  return (
    <ReactRoutes>
      <Route element={<AuthLayout />} path="/login">
        <Route index element={<Login />} />
      </Route>
      <Route element={<DashboardLayout />} path="/dashboard">
        <Route index element={<Dashboard />} />
      </Route>
      <Route element={<Navigate replace to="/dashboard" />} path="/" />
      <Route element={<NotFound />} path="*" />
    </ReactRoutes>
  )
}