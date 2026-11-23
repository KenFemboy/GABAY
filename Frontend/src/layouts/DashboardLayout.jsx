import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { getHealth } from '../api/systemApi'
import { NAV_ITEMS } from '../app/navigation'
import { ROLE_LABELS } from '../auth/roles'
import useAuth from '../auth/useAuth'

const navLinkClass = ({ isActive }) =>
  `block rounded-lg px-3 py-2 ${isActive ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`

export default function DashboardLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
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

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const items = NAV_ITEMS.filter((item) => item.roles.includes(user.role))

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="flex w-64 flex-col bg-slate-900 p-6 text-white">
        <div className="text-2xl font-bold">GABAY</div>
        <nav className="mt-8 space-y-1">
          {items.map((item) => (
            <NavLink className={navLinkClass} key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto pt-6 text-xs text-slate-400">API: {apiStatus}</div>
      </aside>
      <div className="flex-1">
        <header className="border-b border-slate-200 bg-white px-8 py-4">
          <div className="flex items-center justify-end gap-6">
            <div className="text-right">
              <div className="font-medium">{user.name}</div>
              <div className="text-xs text-slate-500">{ROLE_LABELS[user.role] ?? user.role}</div>
            </div>
            <NavLink className="text-sm text-slate-600 hover:text-indigo-600" to="/account/password">
              Change password
            </NavLink>
            <button className="text-sm font-medium text-slate-600 hover:text-red-600" onClick={handleLogout} type="button">
              Sign out
            </button>
          </div>
        </header>
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
