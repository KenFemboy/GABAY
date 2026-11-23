import { useCallback, useEffect, useState } from 'react'

import { createUser, listUsers, updateUser } from '../../api/usersApi'
import { ALL_ROLES, ROLE_LABELS } from '../../auth/roles'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import UserForm from './UserForm'

export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const [filters, setFilters] = useState({ search: '', role: '', status: '' })
  const [data, setData] = useState({ items: [], total: 0 })
  const [loadState, setLoadState] = useState({ loading: true, error: null })
  const [editing, setEditing] = useState(null) // null | 'new' | user object
  const [message, setMessage] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    const timer = setTimeout(() => {
      listUsers(params)
        .then(({ data: result }) => {
          if (!active) return
          setData(result)
          setLoadState({ loading: false, error: null })
        })
        .catch((err) => {
          if (active) setLoadState({ loading: false, error: getErrorMessage(err) })
        })
    }, 250)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [filters, reloadKey])

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])
  const setFilter = (field) => (e) => setFilters((f) => ({ ...f, [field]: e.target.value }))

  const handleCreate = async (payload) => {
    const { data: created } = await createUser(payload)
    setEditing(null)
    setMessage(`Created ${created.name}.`)
    reload()
  }

  const handleUpdate = async (payload) => {
    const { data: updated } = await updateUser(editing.id, payload)
    setEditing(null)
    setMessage(`Saved changes to ${updated.name}.`)
    reload()
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Users</h1>
          <p className="mt-1 text-slate-600">Manage staff accounts and roles.</p>
        </div>
        {editing === null && (
          <button className={primaryButtonClass} onClick={() => { setMessage(null); setEditing('new') }} type="button">
            Add user
          </button>
        )}
      </div>

      {message && <Alert tone="success">{message}</Alert>}

      {editing !== null && (
        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">
            {editing === 'new' ? 'New user' : `Edit ${editing.name}`}
          </h2>
          <UserForm
            isSelf={editing !== 'new' && editing.id === currentUser.id}
            key={editing === 'new' ? 'new' : editing.id}
            onCancel={() => setEditing(null)}
            onSubmit={editing === 'new' ? handleCreate : handleUpdate}
            user={editing === 'new' ? undefined : editing}
          />
        </section>
      )}

      <section className="rounded-xl bg-white shadow">
        <div className="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-3">
          <input aria-label="Search users" className={inputClass} onChange={setFilter('search')} placeholder="Search name or email" value={filters.search} />
          <select aria-label="Filter by role" className={inputClass} onChange={setFilter('role')} value={filters.role}>
            <option value="">All roles</option>
            {ALL_ROLES.map((role) => (
              <option key={role} value={role}>{ROLE_LABELS[role]}</option>
            ))}
          </select>
          <select aria-label="Filter by status" className={inputClass} onChange={setFilter('status')} value={filters.status}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>

        {loadState.error && <div className="p-4"><Alert>{loadState.error}</Alert></div>}

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Last sign-in</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loadState.loading && data.items.length === 0 && (
                <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={6}>Loading users…</td></tr>
              )}
              {!loadState.loading && !loadState.error && data.items.length === 0 && (
                <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={6}>No users match these filters.</td></tr>
              )}
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {u.name}
                    {u.id === currentUser.id && <span className="ml-2 text-xs text-slate-500">(you)</span>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{u.email}</td>
                  <td className="px-4 py-3 text-slate-600">{ROLE_LABELS[u.role] ?? u.role}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${u.status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-600'}`}>
                      {u.status === 'active' ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => { setMessage(null); setEditing(u) }} type="button">
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
          {data.total} user{data.total === 1 ? '' : 's'}
        </div>
      </section>
    </div>
  )
}
