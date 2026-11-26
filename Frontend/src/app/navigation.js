import { ALL_ROLES, ROLES } from '../auth/roles'
import { GOAL_READER_ROLES } from '../features/goals/constants'
import { LEARNER_READER_ROLES } from '../features/learners/constants'

/**
 * Sidebar entries. Each later stage adds its module here with the roles that
 * may use it; items the current user's role cannot access are hidden.
 */
export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', roles: ALL_ROLES },
  { to: '/learners', label: 'Learners', roles: LEARNER_READER_ROLES },
  { to: '/goals', label: 'Goal bank', roles: GOAL_READER_ROLES },
  { to: '/admin/users', label: 'Users', roles: [ROLES.SYSTEM_ADMIN] },
]
