import { useCallback, useEffect, useState } from 'react'

import { createGoal, getIndexStatus, getTaxonomy, listGoals, reindexGoals, searchGoals } from '../../api/goalsApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { formatTarget, GOAL_MANAGER_ROLES, GOAL_STATUS, GRADE_BAND_LABELS, GRADE_BANDS, MEASUREMENT_METHODS, METHOD_LABELS } from './constants'
import GoalDetail, { GoalStatusBadge } from './GoalDetail'
import GoalForm from './GoalForm'
import TaxonomyPanel from './TaxonomyPanel'

const PAGE_SIZE = 25
const EMPTY_FILTERS = { q: '', domain: '', skill: '', status: '', grade_band: '', method: '' }

function GoalRow({ goal, onOpen, score }) {
  const v = goal.current_version
  return (
    <li>
      <button className="w-full rounded-lg border border-slate-200 bg-white p-3 text-left hover:border-indigo-300 hover:bg-indigo-50/30" onClick={() => onOpen(goal.id)} type="button">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-mono font-semibold text-slate-700">{goal.code}</span>
          <GoalStatusBadge status={goal.status} />
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{v.domain.name} → {v.skill.name}</span>
          <span className="text-slate-500">{METHOD_LABELS[v.measurement_method]} · target {formatTarget(v)} · {GRADE_BAND_LABELS[v.grade_band]}</span>
          {v.version_number > 1 && <span className="text-slate-500">v{v.version_number}</span>}
          {goal.in_use && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">In use</span>}
          {score != null && <span className="ml-auto rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700">{Math.round(score * 100)}% similar</span>}
        </div>
        <p className="mt-1 text-sm text-slate-900">{v.statement}</p>
      </button>
    </li>
  )
}

export default function GoalBankPage() {
  const { user } = useAuth()
  const canManage = GOAL_MANAGER_ROLES.includes(user.role)

  const [tab, setTab] = useState('goals')
  const [taxonomy, setTaxonomy] = useState([])
  const [taxonomyKey, setTaxonomyKey] = useState(0)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState({ items: [], total: 0 })
  const [loadState, setLoadState] = useState({ loading: true, error: null })
  const [reloadKey, setReloadKey] = useState(0)
  const [openId, setOpenId] = useState(null)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState(null)
  const [indexStatus, setIndexStatus] = useState(null)
  const [indexBusy, setIndexBusy] = useState(false)
  const [indexError, setIndexError] = useState(null)
  const [similar, setSimilar] = useState({ query: '', results: null, busy: false, error: null })

  useEffect(() => {
    let active = true
    getTaxonomy()
      .then(({ data: t }) => { if (active) setTaxonomy(t.domains) })
      .catch(() => {})
    return () => { active = false }
  }, [taxonomyKey])

  useEffect(() => {
    let active = true
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => String(v).trim()))
    const timer = setTimeout(() => {
      listGoals({ ...params, offset, limit: PAGE_SIZE })
        .then(({ data: result }) => {
          if (!active) return
          setData(result)
          setLoadState({ loading: false, error: null })
        })
        .catch((err) => { if (active) setLoadState({ loading: false, error: getErrorMessage(err) }) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [filters, offset, reloadKey])

  const loadIndexStatus = useCallback(() => {
    if (!canManage) return
    getIndexStatus().then(({ data: s }) => setIndexStatus(s)).catch(() => {})
  }, [canManage])

  useEffect(() => {
    if (!canManage) return undefined
    let active = true
    getIndexStatus().then(({ data: s }) => { if (active) setIndexStatus(s) }).catch(() => {})
    return () => { active = false }
  }, [canManage, reloadKey])

  const refresh = useCallback(() => setReloadKey((k) => k + 1), [])

  const setFilter = (key) => (e) => {
    const value = e.target.value
    setOffset(0)
    setFilters((f) => ({ ...f, [key]: value, ...(key === 'domain' ? { skill: '' } : {}) }))
  }

  const handleCreate = async (payload) => {
    const { data: goal } = await createGoal(payload)
    setCreating(false)
    setMessage(`Draft goal ${goal.code} created. Activate it when it has been reviewed.`)
    refresh()
    setOpenId(goal.id)
  }

  const handleReindex = async () => {
    setIndexBusy(true)
    setIndexError(null)
    try {
      const { data: r } = await reindexGoals()
      setIndexStatus(r.status)
      setMessage(`Index updated: ${r.created} added, ${r.updated} refreshed, ${r.unchanged} unchanged, ${r.removed} removed.`)
    } catch (err) {
      setIndexError(getErrorMessage(err))
    } finally {
      setIndexBusy(false)
    }
  }

  const handleSimilar = async (e) => {
    e.preventDefault()
    setSimilar((s) => ({ ...s, busy: true, error: null }))
    try {
      const { data: r } = await searchGoals(similar.query.trim(), 10)
      setSimilar((s) => ({ ...s, busy: false, results: r.items }))
    } catch (err) {
      setSimilar((s) => ({ ...s, busy: false, error: getErrorMessage(err), results: null }))
    }
  }

  const domain = taxonomy.find((d) => String(d.id) === filters.domain)
  const pageEnd = Math.min(offset + PAGE_SIZE, data.total)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Goal bank</h1>
          <p className="text-sm text-slate-600">Measurable goals by domain and skill, used to suggest IEP goals from approved assessment findings.</p>
        </div>
        {canManage && tab === 'goals' && !creating && (
          <button className={primaryButtonClass} onClick={() => { setMessage(null); setCreating(true) }} type="button">New goal</button>
        )}
      </div>

      {canManage && (
        <div className="flex gap-1 border-b border-slate-200" role="tablist">
          {[['goals', 'Goals'], ['taxonomy', 'Domains & skills']].map(([key, label]) => (
            <button
              aria-selected={tab === key}
              className={`border-b-2 px-4 py-2 text-sm font-medium ${tab === key ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
              key={key}
              onClick={() => setTab(key)}
              role="tab"
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {message && <Alert tone="success">{message}</Alert>}

      {tab === 'taxonomy' && canManage ? (
        <TaxonomyPanel onChanged={() => { setTaxonomyKey((k) => k + 1); refresh() }} taxonomy={taxonomy} />
      ) : (
        <>
          {canManage && indexStatus && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm">
              <span>
                <strong>{indexStatus.indexed}</strong> of {indexStatus.active_goals} active goals indexed for matching
                {indexStatus.missing_or_stale > 0 && <span className="text-amber-700"> · {indexStatus.missing_or_stale} need indexing</span>}
              </span>
              <span className="text-xs text-slate-500">({indexStatus.model.split('/').pop()})</span>
              <button className={`${secondaryButtonClass} ml-auto px-3 py-1 text-sm`} disabled={indexBusy} onClick={handleReindex} type="button">
                {indexBusy ? 'Indexing… (the first run downloads the model)' : 'Reindex'}
              </button>
              {indexError && <div className="w-full"><Alert>{indexError}</Alert></div>}
            </div>
          )}

          {creating && (
            <div className="rounded-lg border border-slate-200 p-4">
              <h2 className="mb-3 font-semibold text-slate-900">New goal (saved as draft)</h2>
              <GoalForm onCancel={() => setCreating(false)} onSubmit={handleCreate} taxonomy={taxonomy} />
            </div>
          )}

          <form className="flex flex-wrap gap-2 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3" onSubmit={handleSimilar}>
            <label className="sr-only" htmlFor="similar">Find similar goals</label>
            <input
              className={`${inputClass} mt-0 min-w-64 flex-1`}
              id="similar"
              onChange={(e) => setSimilar((s) => ({ ...s, query: e.target.value }))}
              placeholder="Find similar goals, e.g. “has difficulty with subtraction”"
              value={similar.query}
            />
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={similar.busy || similar.query.trim().length < 3} type="submit">
              {similar.busy ? 'Searching…' : 'Find similar'}
            </button>
            {similar.results && (
              <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => setSimilar({ query: '', results: null, busy: false, error: null })} type="button">Clear</button>
            )}
          </form>
          {similar.error && <Alert>{similar.error}</Alert>}

          {similar.results ? (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-700">Most similar active goals</h2>
              {similar.results.length === 0 && <p className="text-sm text-slate-500">No indexed active goals yet.</p>}
              <ul className="space-y-2">
                {similar.results.map((h) => <GoalRow goal={h.goal} key={h.goal.id} onOpen={setOpenId} score={h.score} />)}
              </ul>
            </section>
          ) : (
            <>
              <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
                <input aria-label="Search goals" className={`${inputClass} mt-0 lg:col-span-2`} onChange={setFilter('q')} placeholder="Search text or code" value={filters.q} />
                <select aria-label="Domain" className={`${inputClass} mt-0`} onChange={setFilter('domain')} value={filters.domain}>
                  <option value="">All domains</option>
                  {taxonomy.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <select aria-label="Skill" className={`${inputClass} mt-0`} disabled={!domain} onChange={setFilter('skill')} value={filters.skill}>
                  <option value="">All skills</option>
                  {(domain?.skills ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <select aria-label="Grade band" className={`${inputClass} mt-0`} onChange={setFilter('grade_band')} value={filters.grade_band}>
                  <option value="">All grades</option>
                  {GRADE_BANDS.filter((g) => g.value !== 'any').map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
                </select>
                <select aria-label="Measurement method" className={`${inputClass} mt-0`} onChange={setFilter('method')} value={filters.method}>
                  <option value="">All methods</option>
                  {MEASUREMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
                {canManage && (
                  <select aria-label="Status" className={`${inputClass} mt-0`} onChange={setFilter('status')} value={filters.status}>
                    <option value="">All statuses</option>
                    {Object.entries(GOAL_STATUS).map(([value, info]) => <option key={value} value={value}>{info.label}</option>)}
                  </select>
                )}
              </div>

              {loadState.error && <Alert>{loadState.error}</Alert>}
              {loadState.loading ? (
                <p className="text-slate-500">Loading goals…</p>
              ) : data.items.length === 0 ? (
                <p className="py-10 text-center text-slate-500">
                  {canManage ? 'No goals match. Load the starter set with python -m app.scripts.seed_goal_bank, or create one.' : 'No active goals match.'}
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.items.map((g) => <GoalRow goal={g} key={g.id} onOpen={setOpenId} />)}
                </ul>
              )}

              {data.total > PAGE_SIZE && (
                <div className="flex items-center justify-between text-sm text-slate-600">
                  <span>{offset + 1}–{pageEnd} of {data.total}</span>
                  <div className="flex gap-2">
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} type="button">Previous</button>
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={pageEnd >= data.total} onClick={() => setOffset((o) => o + PAGE_SIZE)} type="button">Next</button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      {openId != null && (
        <GoalDetail
          canManage={canManage}
          goalId={openId}
          key={openId}
          onChanged={() => { refresh(); loadIndexStatus() }}
          onClose={() => setOpenId(null)}
          taxonomy={taxonomy}
        />
      )}
    </div>
  )
}
