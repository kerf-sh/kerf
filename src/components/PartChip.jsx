import { X, Hash } from 'lucide-react'

export default function PartChip({ partId, fileName, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-kerf-300/15 border border-kerf-300/40 text-kerf-100 text-[11px] font-mono max-w-full">
      <Hash size={10} className="flex-shrink-0 text-kerf-300" />
      <span className="truncate">{partId}</span>
      {fileName && <span className="text-ink-400">@{fileName}</span>}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="ml-0.5 text-ink-300 hover:text-kerf-200 flex-shrink-0"
          title="Remove"
        >
          <X size={10} />
        </button>
      )}
    </span>
  )
}
