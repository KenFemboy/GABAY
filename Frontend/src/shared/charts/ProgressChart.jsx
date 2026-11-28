import { useId, useMemo, useState } from 'react'

/*
 * Per-goal progress chart (hand-built SVG).
 *
 * Follows the dataviz method: one y-axis, 2px line + 8px markers with a 2px
 * surface ring, recessive solid hairline grid, legend always present (3 keys),
 * selective direct labels (target + latest only), crosshair tooltip that snaps
 * to the nearest data date, a table view, and text in text inks (never in the
 * series colour). Series colour = reference palette categorical slot 1
 * (#257de0), validated with validate_palette.js; the aim and target lines are
 * neutral inks distinguished by dash pattern AND direct labels.
 */

const W = 640
const H = 260
const M = { top: 16, right: 92, bottom: 30, left: 44 }
const COLORS = {
  series: '#257de0',
  surface: '#ffffff',
  grid: '#e7e7e7',
  axis: '#c2c2c2',
  ink: '#191919',
  inkSecondary: '#666666',
  review: '#efefef',
}
const UNIT_SUFFIX = { percent: '%', trials: ' trials', count: '', minutes: ' min', wpm: ' wpm', level: '' }

const toTime = (iso) => new Date(`${iso}T00:00:00Z`).getTime()
const fmtDate = (iso) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' })
const fmtValue = (v, unit) => (v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${UNIT_SUFFIX[unit] ?? ''}`)

function niceMax(value) {
  if (value <= 0) return 10
  const pow = 10 ** Math.floor(Math.log10(value))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= value) return m * pow
  return 10 * pow
}

export default function ProgressChart({ data, evidenceLabels = {} }) {
  const id = useId()
  const [hover, setHover] = useState(null) // index into points
  const [showTable, setShowTable] = useState(false)
  const unit = data.goal.target_unit
  const points = data.points
  const start = data.start_date
  const end = data.target_date

  const model = useMemo(() => {
    if (!start || !end) return null
    const t0 = toTime(start)
    const t1 = Math.max(toTime(end), t0 + 86400000)
    const values = [data.target_value, data.baseline_value, ...points.map((p) => p.value)].filter((v) => v != null)
    const yMax = unit === 'percent' ? 100 : niceMax(Math.max(...values, 1) * 1.1)
    const x = (iso) => M.left + ((Math.min(Math.max(toTime(iso), t0), t1) - t0) / (t1 - t0)) * (W - M.left - M.right)
    const y = (v) => M.top + (1 - v / yMax) * (H - M.top - M.bottom)
    const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMax * f * 100) / 100)
    const monthTicks = []
    const d = new Date(t0)
    d.setUTCDate(1)
    d.setUTCMonth(d.getUTCMonth() + 1)
    while (d.getTime() <= t1) {
      monthTicks.push(d.toISOString().slice(0, 10))
      d.setUTCMonth(d.getUTCMonth() + 2)
    }
    return { x, y, ticks, monthTicks, yMax }
  }, [start, end, points, unit, data.target_value, data.baseline_value])

  const status = data.status
  const latest = points.at(-1)
  const summary = latest
    ? `Latest ${fmtValue(latest.value, unit)} on ${fmtDate(latest.recorded_on)}` +
      (status.expected != null ? `, aim line ${fmtValue(status.expected, unit)}` : '') +
      (data.target_value != null ? `, target ${fmtValue(data.target_value, unit)}` : '')
    : 'No data points yet.'

  if (!model) {
    return <p className="text-sm text-slate-500">Set the goal's start and target dates in the IEP to show a chart.</p>
  }
  const { x, y, ticks, monthTicks } = model
  const linePath = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.recorded_on).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const hovered = hover != null ? points[hover] : null

  const onMove = (event) => {
    if (!points.length) return
    const rect = event.currentTarget.getBoundingClientRect()
    const px = ((event.clientX - rect.left) / rect.width) * W
    let best = 0
    points.forEach((p, i) => { if (Math.abs(x(p.recorded_on) - px) < Math.abs(x(points[best].recorded_on) - px)) best = i })
    setHover(best)
  }

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
        <span className="flex flex-wrap items-center gap-4" aria-hidden="true">
          <span className="inline-flex items-center gap-1.5">
            <svg height="10" width="22"><line stroke={COLORS.series} strokeLinecap="round" strokeWidth="2" x1="1" x2="21" y1="5" y2="5" /><circle cx="11" cy="5" fill={COLORS.series} r="4" /></svg>
            Data
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg height="10" width="22"><line stroke={COLORS.ink} strokeDasharray="5 4" strokeWidth="1.5" x1="1" x2="21" y1="5" y2="5" /></svg>
            Aim line
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg height="10" width="22"><line stroke={COLORS.inkSecondary} strokeWidth="1" x1="1" x2="21" y1="5" y2="5" /></svg>
            Target
          </span>
        </span>
        <button className="text-indigo-600 hover:underline" onClick={() => setShowTable((v) => !v)} type="button">
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </figcaption>

      {showTable ? (
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full text-left text-sm tabular-nums">
            <caption className="sr-only">{summary}</caption>
            <thead className="bg-slate-50 text-xs text-slate-600">
              <tr><th className="px-3 py-1.5">Date</th><th className="px-3 py-1.5">Value</th><th className="px-3 py-1.5">Evidence</th><th className="px-3 py-1.5">Note</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.baseline_value != null && (
                <tr className="text-slate-500"><td className="px-3 py-1">{fmtDate(start)}</td><td className="px-3 py-1">{fmtValue(data.baseline_value, unit)}</td><td className="px-3 py-1">Baseline</td><td className="px-3 py-1" /></tr>
              )}
              {points.map((p) => (
                <tr key={p.id}><td className="px-3 py-1">{fmtDate(p.recorded_on)}</td><td className="px-3 py-1">{fmtValue(p.value, unit)}{p.out_of ? ` of ${p.out_of}` : ''}</td><td className="px-3 py-1">{evidenceLabels[p.evidence_type] ?? p.evidence_type}</td><td className="px-3 py-1 text-slate-600">{p.note}</td></tr>
              ))}
              {data.target_value != null && (
                <tr className="text-slate-500"><td className="px-3 py-1">{fmtDate(end)}</td><td className="px-3 py-1">{fmtValue(data.target_value, unit)}</td><td className="px-3 py-1">Target</td><td className="px-3 py-1" /></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg
            aria-describedby={`${id}-summary`}
            className="h-auto w-full touch-none select-none"
            onPointerLeave={() => setHover(null)}
            onPointerMove={onMove}
            role="img"
            viewBox={`0 0 ${W} ${H}`}
          >
            <title>{`Progress for goal ${data.goal.number}`}</title>
            {/* Review-date bands (very faint) */}
            {data.review_dates.map((d) => (
              <line key={d} stroke={COLORS.review} strokeWidth="6" x1={x(d)} x2={x(d)} y1={M.top} y2={H - M.bottom} />
            ))}
            {/* Grid + y ticks */}
            {ticks.map((t) => (
              <g key={t}>
                <line stroke={t === 0 ? COLORS.axis : COLORS.grid} strokeWidth="1" x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} />
                <text className="tabular-nums" dominantBaseline="middle" fill={COLORS.inkSecondary} fontSize="11" textAnchor="end" x={M.left - 6} y={y(t)}>{fmtValue(t, unit)}</text>
              </g>
            ))}
            {monthTicks.map((d) => (
              <text fill={COLORS.inkSecondary} fontSize="11" key={d} textAnchor="middle" x={x(d)} y={H - 10}>
                {new Date(`${d}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', timeZone: 'UTC' })}
              </text>
            ))}
            {/* Target reference line + direct label */}
            {data.target_value != null && (
              <g>
                <line stroke={COLORS.inkSecondary} strokeWidth="1" x1={M.left} x2={W - M.right} y1={y(data.target_value)} y2={y(data.target_value)} />
                <text dominantBaseline="middle" fill={COLORS.inkSecondary} fontSize="11" x={W - M.right + 6} y={y(data.target_value)}>
                  Target {fmtValue(data.target_value, unit)}
                </text>
              </g>
            )}
            {/* Aim line: baseline at start -> target at target date */}
            {data.aim_start && data.aim_end && (
              <g>
                <line stroke={COLORS.ink} strokeDasharray="5 4" strokeWidth="1.5" x1={x(data.aim_start.date)} x2={x(data.aim_end.date)} y1={y(data.aim_start.value)} y2={y(data.aim_end.value)} />
                <circle cx={x(data.aim_start.date)} cy={y(data.aim_start.value)} fill={COLORS.surface} r="4" stroke={COLORS.ink} strokeWidth="1.5" />
              </g>
            )}
            {/* Crosshair */}
            {hovered && (
              <line stroke={COLORS.axis} strokeWidth="1" x1={x(hovered.recorded_on)} x2={x(hovered.recorded_on)} y1={M.top} y2={H - M.bottom} />
            )}
            {/* Data line + markers (2px surface ring), hit targets >= 24px */}
            {points.length > 1 && <path d={linePath} fill="none" stroke={COLORS.series} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />}
            {points.map((p, i) => (
              <g key={p.id}>
                <circle cx={x(p.recorded_on)} cy={y(p.value)} fill={COLORS.series} r={hover === i ? 5.5 : 4} stroke={COLORS.surface} strokeWidth="2" />
                <circle
                  aria-label={`${fmtDate(p.recorded_on)}: ${fmtValue(p.value, unit)}`}
                  cx={x(p.recorded_on)}
                  cy={y(p.value)}
                  fill="transparent"
                  onBlur={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  r="12"
                  role="button"
                  tabIndex={0}
                />
              </g>
            ))}
            {/* Direct label on the latest value only */}
            {latest && hover == null && (
              <text dominantBaseline="middle" fill={COLORS.ink} fontSize="11" fontWeight="600" x={x(latest.recorded_on) + 9} y={y(latest.value) - 10}>
                {fmtValue(latest.value, unit)}
              </text>
            )}
          </svg>
          {hovered && (
            <div
              className="pointer-events-none absolute z-10 min-w-36 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"
              style={{
                left: `${(x(hovered.recorded_on) / W) * 100}%`,
                top: `${(y(hovered.value) / H) * 100}%`,
                transform: `translate(${x(hovered.recorded_on) > W * 0.6 ? 'calc(-100% - 12px)' : '12px'}, -50%)`,
              }}
            >
              <div className="text-sm font-semibold tabular-nums text-slate-900">
                {fmtValue(hovered.value, unit)}{hovered.out_of ? ` of ${hovered.out_of}` : ''}
              </div>
              <div className="text-slate-600">{fmtDate(hovered.recorded_on)} · {evidenceLabels[hovered.evidence_type] ?? hovered.evidence_type}</div>
              {hovered.note && <div className="mt-1 max-w-52 text-slate-600">{hovered.note}</div>}
            </div>
          )}
          <p className="sr-only" id={`${id}-summary`}>{summary}</p>
        </div>
      )}
    </figure>
  )
}
