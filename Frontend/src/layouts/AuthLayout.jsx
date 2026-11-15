import { Outlet } from 'react-router-dom'

export default function AuthLayout() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <Outlet />
    </main>
  )
}