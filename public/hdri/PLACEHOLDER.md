# HDRI Sky Files

This directory is where the operator places the actual HDRI environment map files
(`.hdr`) that back the presets defined in `src/lib/hdriPresets.js`.

**The files are not included in this repository** because they are large binary
assets (typically 10–100 MB each at 2K–8K resolution). The git repository only
ships the registry metadata and the UI component.

---

## Required files

Drop the following files into this directory:

| File | Preset | Approx. size (2K) |
|------|--------|-------------------|
| `clear-noon.hdr` | Clear Noon | ~15 MB |
| `overcast.hdr` | Overcast | ~12 MB |
| `sunset.hdr` | Sunset | ~18 MB |
| `studio-soft.hdr` | Studio Soft | ~10 MB |
| `night-stars.hdr` | Night Stars | ~8 MB |

Optional thumbnail previews (small JPEG, ~20–60 KB each):

| File | Used by |
|------|---------|
| `clear-noon.thumb.jpg` | HdriPicker card |
| `overcast.thumb.jpg` | HdriPicker card |
| `sunset.thumb.jpg` | HdriPicker card |
| `studio-soft.thumb.jpg` | HdriPicker card |
| `night-stars.thumb.jpg` | HdriPicker card |

If thumbnail files are absent, the picker falls back to a colour-gradient
placeholder — the renderer still works correctly.

---

## CC0 sources

All presets reference CC0-1.0 licensed HDRIs. Recommended download sources:

### Poly Haven (polyhaven.com)
Free, CC0. Download the `.hdr` format at 2K or 4K.

| Preset | Poly Haven asset |
|--------|-----------------|
| Clear Noon | https://polyhaven.com/a/clear_2k |
| Overcast | https://polyhaven.com/a/kloppenheim_06_puresky |
| Sunset | https://polyhaven.com/a/sunset_jhbcentral |
| Studio Soft | https://polyhaven.com/a/studio_small_08 |
| Night Stars | https://polyhaven.com/a/starry_night |

### HDRIHaven (legacy, now part of Poly Haven)
The same CC0 library is mirrored at https://hdri-haven.com and accessible via
the Poly Haven API: `https://api.polyhaven.com/files/<asset-name>`.

### HDRMAPS (hdrmaps.com)
Free-tier CC0 HDRIs are available at https://hdrmaps.com/freebies — suitable
substitutes if the Poly Haven originals are unavailable.

---

## Hosting in production

For cloud deployments, serve these files from a CDN (e.g. bunny.net or
Cloudflare R2) and update the `file_url` entries in `src/lib/hdriPresets.js`
to point to the CDN origin instead of `/hdri/<slug>.hdr`.

For local installs, dropping the files here and running `npm run build` is
sufficient — Vite copies all `public/` assets verbatim into `dist/`.
