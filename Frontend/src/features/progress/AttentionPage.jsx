import AttentionList from './AttentionList'

export default function AttentionPage() {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold text-slate-900">Progress alerts</h1>
      <p className="text-sm text-slate-600">
        Goals of finalized IEPs whose recent data falls behind the aim line (baseline → target), or that have no recent data.
      </p>
      <AttentionList />
    </div>
  )
}
