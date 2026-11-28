import { ROLE_LABELS } from '../../auth/roles'
import useAuth from '../../auth/useAuth'
import AttentionList from '../progress/AttentionList'
import { ATTENTION_VIEWER_ROLES } from '../progress/constants'

export default function DashboardPage() {
  const { user } = useAuth()
  return (
    <div>
      <h1 className="text-3xl font-bold text-slate-900">Welcome, {user.name}</h1>
      <p className="mt-2 text-slate-600">
        Signed in as {ROLE_LABELS[user.role] ?? user.role}. Modules for your role will appear in
        the sidebar as they become available.
      </p>
      {ATTENTION_VIEWER_ROLES.includes(user.role) && (
        <div className="mt-8">
          <AttentionList compact />
        </div>
      )}
    </div>
  )
}
