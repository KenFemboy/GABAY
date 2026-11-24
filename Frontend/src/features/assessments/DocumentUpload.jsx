import { useRef, useState } from 'react'

import { uploadDocument } from '../../api/assessmentApi'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { ACCEPT_ATTRIBUTE, ACCEPTED_EXTENSIONS, formatFileSize, MAX_UPLOAD_MB } from './constants'

function precheck(file) {
  const ext = file.name.includes('.') ? file.name.split('.').pop().toLowerCase() : ''
  if (!ACCEPTED_EXTENSIONS.includes(ext)) return 'Only PDF, JPG or PNG files can be uploaded.'
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The file is larger than the ${MAX_UPLOAD_MB} MB limit.`
  return null
}

export default function DocumentUpload({ assessmentId, onUploaded }) {
  const inputRef = useRef(null)
  const [file, setFile] = useState(null)
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState(null)

  const choose = (event) => {
    const selected = event.target.files?.[0] ?? null
    setError(selected ? precheck(selected) : null)
    setFile(selected)
    setProgress(null)
  }

  const reset = () => {
    setFile(null)
    setError(null)
    setProgress(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleUpload = async () => {
    if (!file || error) return
    setProgress(0)
    try {
      const { data } = await uploadDocument(assessmentId, file, setProgress)
      reset()
      onUploaded(data)
    } catch (err) {
      setProgress(null)
      setError(getErrorMessage(err))
    }
  }

  const uploading = progress !== null

  return (
    <div className="space-y-3 rounded-lg border border-dashed border-slate-300 p-4">
      <div>
        <label className="block text-sm font-medium text-slate-700" htmlFor={`upload-${assessmentId}`}>
          Upload assessment document
        </label>
        <p className="text-xs text-slate-500">PDF, JPG or PNG, up to {MAX_UPLOAD_MB} MB.</p>
      </div>
      <input
        accept={ACCEPT_ATTRIBUTE}
        className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:font-medium file:text-indigo-700 hover:file:bg-indigo-100"
        disabled={uploading}
        id={`upload-${assessmentId}`}
        onChange={choose}
        ref={inputRef}
        type="file"
      />
      {file && !error && !uploading && (
        <p className="text-sm text-slate-600">{file.name} · {formatFileSize(file.size)}</p>
      )}
      {error && <Alert>{error}</Alert>}
      {uploading && (
        <div aria-label="Upload progress" aria-valuemax={100} aria-valuemin={0} aria-valuenow={progress} role="progressbar">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-indigo-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {progress < 100 ? `Uploading… ${progress}%` : 'Checking and saving the file…'}
          </p>
        </div>
      )}
      <div className="flex gap-2">
        <button className={primaryButtonClass} disabled={!file || Boolean(error) || uploading} onClick={handleUpload} type="button">
          Upload
        </button>
        {file && !uploading && (
          <button className={secondaryButtonClass} onClick={reset} type="button">
            Clear
          </button>
        )}
      </div>
    </div>
  )
}
