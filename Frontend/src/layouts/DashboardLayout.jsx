import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { getHealth } from '../api/authApi'

export default function DashboardLayout() {
  const [apiStatus, setApiStatus] = useState('checking')

  useEffect(() => {
    let active = true
    getHealth()
      .then(({ data }) => {
        if (active) setApiStatus(data.status === 'ok' ? 'connected' : 'degraded')
      })
      .catch(() => {
        if (active) setApiStatus('unavailable')
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="w-64 bg-slate-900 p-6 text-white">
        <div className="text-2xl font-bold">GABAY</div>
        <nav className="mt-8 space-y-2">
          <NavLink className="block rounded-lg px-3 py-2 hover:bg-slate-700" to="/dashboard">
            Dashboard
          </NavLink>
        </nav>
      </aside>
      <div className="flex-1">
        <header className="border-b border-slate-200 bg-white px-8 py-4">
          <div className="flex items-center justify-between">
            <span className="font-medium">Workspace</span>
            <span className="text-sm text-slate-500">API: {apiStatus}</span>
          </div>
        </header>
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}