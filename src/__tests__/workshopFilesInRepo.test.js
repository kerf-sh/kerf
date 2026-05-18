// Slice 6 (frontend): Workshop media is files-in-repo. The gallery
// comes from the listing payload's `images` (no /workshop-images
// fetch), the retired uploader is gone, and a designated model file
// links into the editor's 3D view.

import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, it, expect } from 'vitest'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(root, p), 'utf8')

describe('Workshop files-in-repo (frontend)', () => {
  it('listing uses payload images, not the retired gallery endpoint', () => {
    const wl = read('cloud/WorkshopListing.jsx')
    expect(wl).not.toContain('api.workshopImages')
    expect(wl).toContain('setGalleryImages(Array.isArray(resp?.images) ? resp.images : [])')
  })

  it('listing links a designated 3D model into the editor', () => {
    const wl = read('cloud/WorkshopListing.jsx')
    expect(wl).toContain('listing?.model_file_id && listing?.project_id')
    expect(wl).toContain('/projects/${listing.project_id}/files/${listing.model_file_id}')
  })

  it('the DB-gallery client + uploader component are retired', () => {
    expect(read('lib/api.js')).not.toContain('workshopImages:')
    expect(existsSync(join(root, 'components/WorkshopImageGallery.jsx'))).toBe(false)
    expect(read('cloud/PublishButton.jsx')).not.toContain('WorkshopImageGallery')
  })
})
