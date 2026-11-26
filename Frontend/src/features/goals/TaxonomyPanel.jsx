import { useState } from 'react'

import { createDomain, createSkill, updateDomain, updateSkill } from '../../api/goalsApi'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

const toCode = (name) => name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 's_$1').slice(0, 32)

function InlineName({ value, onSave }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(value)
  if (!editing) {
    return <button className="text-left hover:underline" onClick={() => { setText(value); setEditing(true) }} title="Rename" type="button">{value}</button>
  }
  return (
    <span className="inline-flex gap-1">
      <input aria-label="New name" className={`${inputClass} mt-0 py-0.5 text-sm`} maxLength={120} onChange={(e) => setText(e.target.value)} value={text} />
      <button className={`${secondaryButtonClass} px-2 py-0.5 text-xs`} disabled={!text.trim()} onClick={async () => { try { await onSave(text.trim()); setEditing(false) } catch { /* error shown by the panel */ } }} type="button">Save</button>
      <button className="px-1 text-xs text-slate-500" onClick={() => setEditing(false)} type="button">Cancel</button>
    </span>
  )
}

function AddRow({ placeholder, onAdd }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onAdd(name.trim())
      setName('')
    } catch {
      // error shown by the panel
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="flex gap-2" onSubmit={submit}>
      <input aria-label={placeholder} className={`${inputClass} mt-0 py-1 text-sm`} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder={placeholder} value={name} />
      <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || toCode(name).length < 2} type="submit">Add</button>
    </form>
  )
}

/** Coordinator-only: manage domains and skills. Nothing is ever deleted, only deactivated. */
export default function TaxonomyPanel({ taxonomy, onChanged }) {
  const [error, setError] = useState(null)

  const run = async (fn) => {
    setError(null)
    try {
      await fn()
      onChanged()
    } catch (err) {
      setError(getErrorMessage(err))
      throw err
    }
  }
  const quiet = (fn) => run(fn).catch(() => {})

  return (
    <div className="space-y-4 py-4">
      <Alert tone="info">
        The domains and skills below are a proposed draft and must be agreed with the SNED Coordinator. Items are never
        deleted; deactivate them instead. Domain codes are fixed because extraction findings use them.
      </Alert>
      {error && <Alert>{error}</Alert>}
      <div className="grid gap-4 md:grid-cols-2">
        {taxonomy.map((d) => (
          <section className={`rounded-lg border p-4 ${d.is_active ? 'border-slate-200' : 'border-dashed border-slate-300 opacity-70'}`} key={d.id}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold text-slate-900">
                <InlineName onSave={(name) => run(() => updateDomain(d.id, { name }))} value={d.name} />
                <span className="ml-2 font-mono text-xs font-normal text-slate-400">{d.code}</span>
              </h3>
              <button className={`${secondaryButtonClass} px-2 py-0.5 text-xs`} onClick={() => quiet(() => updateDomain(d.id, { is_active: !d.is_active }))} type="button">
                {d.is_active ? 'Deactivate' : 'Activate'}
              </button>
            </div>
            <ul className="mt-2 space-y-1 text-sm">
              {d.skills.map((s) => (
                <li className={`flex items-center justify-between gap-2 ${s.is_active ? '' : 'text-slate-400 line-through'}`} key={s.id}>
                  <InlineName onSave={(name) => run(() => updateSkill(s.id, { name }))} value={s.name} />
                  <button className="text-xs text-indigo-600 hover:underline" onClick={() => quiet(() => updateSkill(s.id, { is_active: !s.is_active }))} type="button">
                    {s.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-3">
              <AddRow onAdd={(name) => run(() => createSkill({ domain_id: d.id, code: toCode(name), name }))} placeholder="New skill name" />
            </div>
          </section>
        ))}
      </div>
      <section className="rounded-lg border border-dashed border-slate-300 p-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Add a domain</h3>
        <AddRow onAdd={(name) => run(() => createDomain({ code: toCode(name), name, sort_order: taxonomy.length + 1 }))} placeholder="New domain name" />
      </section>
    </div>
  )
}
