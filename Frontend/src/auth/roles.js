// Must match app.models.user.Role on the backend.
export const ROLES = {
  SYSTEM_ADMIN: 'system_admin',
  SNED_COORDINATOR: 'sned_coordinator',
  TEACHER: 'teacher',
  SCHOOL_HEAD: 'school_head',
}

export const ALL_ROLES = Object.values(ROLES)

export const ROLE_LABELS = {
  [ROLES.SYSTEM_ADMIN]: 'System Administrator',
  [ROLES.SNED_COORDINATOR]: 'SNED Coordinator',
  [ROLES.TEACHER]: 'Teacher',
  [ROLES.SCHOOL_HEAD]: 'School Head / SNED Focal',
}
