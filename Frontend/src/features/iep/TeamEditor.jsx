import { inputClass, secondaryButtonClass } from '../../shared/forms/styles'

/** Edit [{name, role}] team members; printed in the IEP signature block. */
export default function TeamEditor({ value, onChange, disabled }) {
  const members = value ?? []
  const set = (index, key, text) => onChange(members.map((m, i) => (i === index ? { ...m, [key]: text } : m)))

  return (
    <div className="space-y-2">
      {members.length === 0 && <p className="text-sm text-slate-500">No team members yet.</p>}
      {members.map((m, i) => (
        <div className="flex flex-wrap gap-2" key={i}>
          <input aria-label={`Team member ${i + 1} name`} className={`${inputClass} mt-0 min-w-40 flex-1 py-1 text-sm`} disabled={disabled} maxLength={150} onChange={(e) => set(i, 'name', e.target.value)} placeholder="Name" value={m.name} />
          <input aria-label={`Team member ${i + 1} role`} className={`${inputClass} mt-0 min-w-40 flex-1 py-1 text-sm`} disabled={disabled} maxLength={100} onChange={(e) => set(i, 'role', e.target.value)} placeholder="Role (e.g. Adviser, Parent)" value={m.role} />
          {!disabled && (
            <button aria-label={`Remove team member ${i + 1}`} className="px-2 text-sm text-red-600 hover:underline" onClick={() => onChange(members.filter((_, j) => j !== i))} type="button">Remove</button>
          )}
        </div>
      ))}
      {!disabled && members.length < 20 && (
        <button className={`${secondaryButtonClass} px-3 py-1 text-xs`} onClick={() => onChange([...members, { name: '', role: '' }])} type="button">+ Add member</button>
      )}
    </div>
  )
}
