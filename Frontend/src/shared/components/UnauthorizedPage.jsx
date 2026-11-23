import { Link } from 'react-router-dom'

export default function UnauthorizedPage() {
  return (
    <section className="mx-auto max-w-lg rounded-xl bg-white p-8 text-center shadow">
      <h1 className="text-2xl font-bold text-slate-900">Access restricted</h1>
      <p className="mt-2 text-slate-600">
        Your role does not have access to this page. Contact your System Administrator if you
        believe this is a mistake.
      </p>
      <Link className="mt-6 inline-block font-medium text-indigo-600 hover:underline" to="/dashboard">
        Back to dashboard
      </Link>
    </section>
  )
}
