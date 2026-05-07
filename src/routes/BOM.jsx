// /projects/:projectId/bom — full-page Bill of Materials view.
//
// Thin route wrapper around <BOMPanel/>. Reads the project id from the URL
// and provides a back-link to the editor. We deliberately keep this dumb so
// the underlying BOMPanel stays embeddable from inside AssemblyEditor as a
// collapsible drawer (see TODO in AssemblyEditor for the inline mount).

import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Package } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import BOMPanel from '../components/BOMPanel.jsx'

export default function BOMPage() {
  const { projectId } = useParams()
  const navigate = useNavigate()

  return (
    <div className="h-screen flex flex-col bg-ink-950 text-ink-100 overflow-hidden">
      <header className="flex items-center gap-3 h-12 px-3 border-b border-ink-800 bg-ink-900 flex-shrink-0">
        <button
          type="button"
          onClick={() => navigate(`/projects/${projectId}`)}
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
          title="Back to editor"
        >
          <ArrowLeft size={15} />
        </button>
        <LogoWordmark />
        <span className="text-ink-700">/</span>
        <div className="flex items-center gap-1.5 text-sm text-ink-200">
          <Package size={13} className="text-kerf-300" />
          Bill of Materials
        </div>
      </header>
      <main className="flex-1 min-h-0 overflow-hidden">
        <BOMPanel projectId={projectId} />
      </main>
    </div>
  )
}
