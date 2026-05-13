/**
 * Density mesh to GLTF conversion helpers.
 *
 * The FEniCSx SIMP engine produces a density field (volumetric scalar field
 * on a mesh) and a binary STEP mesh from marching-cubes post-processing.
 *
 * This module provides:
 *   - densityMeshToGLTF(fileId): fetches the density mesh artifact, converts
 *     it to a GLTF+GLB binary suitable for rendering in the TopoView's
 *     ThreeDenseMesh component.
 *   - densityToVertexColors(density, vertices, threshold): maps per-element
 *     SIMP densities to RGBA vertex colors (blue=0 → red=1) for the 3D
 *     density field viewer.
 *
 * Conversion pipeline:
 *   1. Fetch density mesh artifact (stored as a binary blob by the pyworker).
 *   2. Parse mesh (supports: .vtk, .vtu (VTK unstructured grid), .x3d).
 *   3. Map element densities → vertex densities (average of incident elements).
 *   4. Map vertex densities → vertex colors via a blue→cyan→green→yellow→red
 *      gradient (viridis-style).
 *   5. Serialize as GLTF 2.0 with VERTEX_COLORS.
 */

import { api } from './api.js'

const DENSITY_MIN = 0.0
const DENSITY_MAX = 1.0

/**
 * Fetch a density mesh artifact by file_id and return a temporary GLTF URL.
 *
 * @param {string} fileId  The output_mesh_file_id from the .topo results.
 * @returns {Promise<string>} A temporary object URL (URL.createObjectURL).
 * Caller mustRevokeObjectURL when done.
 */
export async function densityMeshToGLTF(fileId) {
  if (!fileId) throw new Error('fileId is required')

  const buf = await fetchDensityMeshBuffer(fileId)
  const mesh = parseDensityMesh(buf)
  const { vertices, faces } = mesh

  const vertexColors = new Float32Array(vertices.length * 4)
  for (let i = 0; i < vertices.length; i++) {
    const d = clamp(vertices[i].density || 0, DENSITY_MIN, DENSITY_MAX)
    const t = (d - DENSITY_MIN) / (DENSITY_MAX - DENSITY_MIN)
    const [r, g, b] = viridis(t)
    vertexColors[i * 4 + 0] = r
    vertexColors[i * 4 + 1] = g
    vertexColors[i * 4 + 2] = b
    vertexColors[i * 4 + 3] = 1.0
  }

  const gltf = buildGLTF(vertices, faces, vertexColors)
  const blob = new Blob([gltf], { type: 'model/gltf-binary' })
  return URL.createObjectURL(blob)
}

/**
 * Fetch the raw binary mesh buffer for a given fileId.
 * Uses the project's file download endpoint.
 *
 * @param {string} fileId
 * @returns {Promise<ArrayBuffer>}
 */
async function fetchDensityMeshBuffer(fileId) {
  const url = `/api/files/${fileId}/download`
  const token = useAuth.getState().accessToken
  const headers = {}
  if (token) headers.authorization = `Bearer ${token}`

  let res = await fetch(url, { headers })
  if (res.status === 401) {
    const newToken = await refreshAccessToken()
    headers.authorization = `Bearer ${newToken}`
    res = await fetch(url, { headers })
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch mesh artifact: ${res.status} ${res.statusText}`)
  }
  return res.arrayBuffer()
}

/**
 * Parse a density mesh from a binary buffer.
 * Supports: VTK legacy ASCII, VTU (XML), and raw binary Float32Array.
 *
 * @param {ArrayBuffer} buf
 * @returns {{ vertices: Array<{x,y,z,density}>, faces: Array<[a,b,c]> }}
 */
export function parseDensityMesh(buf) {
  const view = new DataView(buf)
  const bytes = new Uint8Array(buf)

  if (bytes.length >= 4 && bytes[0] === 0x23 && bytes[1] === 0x21 && bytes[2] === 0x2f) {
    return parseVTKASCII(buf)
  }

  if (bytes.length >= 5 && bytes[0] === 0x3c && bytes[1] === 0x3f && bytes[2] === 0x78 && bytes[3] === 0x6d) {
    return parseVTU(buf)
  }

  return parseBinaryMesh(buf)
}

function parseVTKASCII(buf) {
  const text = new TextDecoder('utf-8', { fatal: false }).decode(buf)
  const lines = text.split('\n')
  const vertices = []
  const faces = []
  let inPoints = false
  let inCells = false
  let pointIdx = 0
  let cellIdx = 0
  let nPoints = 0
  let nCells = 0
  let pointsRead = 0
  let cellsRead = 0
  let densityRead = 0
  const densities = []

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === 'DATASET UNSTRUCTURED_GRID') {
      inPoints = true
      inCells = false
    } else if (trimmed.startsWith('POINTS ')) {
      const parts = trimmed.split(/\s+/)
      nPoints = parseInt(parts[1])
      inPoints = true
      pointsRead = 0
    } else if (trimmed.startsWith('CELLS ')) {
      const parts = trimmed.split(/\s+/)
      nCells = parseInt(parts[1])
      inCells = true
      inPoints = false
      cellsRead = 0
    } else if (trimmed === 'POINT_DATA ' + nPoints) {
      densityRead = 0
    } else if (trimmed.startsWith('SCALARS density')) {
      densityRead = 1
    } else if (trimmed === 'LOOKUP_TABLE default') {
      densityRead = 2
    } else if (densityRead === 2 && pointsRead < nPoints) {
      const val = parseFloat(trimmed)
      if (!isNaN(val)) densities.push(val)
      pointsRead++
      if (densities.length >= nPoints) densityRead = 0
    } else if (inPoints && pointsRead < nPoints) {
      const parts = trimmed.split(/\s+/).filter(Boolean)
      if (parts.length >= 3) {
        const x = parseFloat(parts[0])
        const y = parseFloat(parts[1])
        const z = parseFloat(parts[2])
        vertices.push({
          x, y, z,
          density: densities[vertices.length] ?? 0,
        })
        pointsRead++
      }
    } else if (inCells && cellsRead < nCells) {
      const parts = trimmed.split(/\s+/).filter(Boolean)
      const size = parseInt(parts[0])
      if (size === 3 && parts.length >= 4) {
        const a = parseInt(parts[1])
        const b = parseInt(parts[2])
        const c = parseInt(parts[3])
        faces.push([a, b, c])
      }
      cellsRead++
    }
  }

  return { vertices, faces }
}

function parseVTU(buf) {
  const text = new TextDecoder('utf-8', { fatal: false }).decode(buf)
  const vertices = []
  const faces = []

  const pointsMatch = text.match(/<Points>[\s\S]*?<\/Points>/)
  const cellsMatch = text.match(/<Cells>[\s\S]*?<\/Cells>/)
  const densityMatch = text.match(/<PointData[\s\S]*?density[\s\S]*?<\/PointData>/)

  if (pointsMatch) {
    const coordText = pointsMatch[0]
    const coords = coordText.match(/-?\d+\.?\d*[eE]?[+-]?\d*/g)
      ?.map(Number)
      .filter((v) => Number.isFinite(v)) ?? []
    for (let i = 0; i < coords.length / 3; i++) {
      vertices.push({
        x: coords[i * 3],
        y: coords[i * 3 + 1],
        z: coords[i * 3 + 2],
        density: 0,
      })
    }
  }

  if (densityMatch) {
    const vals = densityMatch[0]
      .match(/-?\d+\.?\d*[eE]?[+-]?\d*/g)
      ?.map(Number)
      .filter((v) => Number.isFinite(v)) ?? []
    for (let i = 0; i < Math.min(vals.length, vertices.length); i++) {
      vertices[i].density = clamp(vals[i], DENSITY_MIN, DENSITY_MAX)
    }
  }

  if (cellsMatch) {
    const conn = cellsMatch[0]
      .match(/<connectivity>[\s\S]*?<\/connectivity>/)
    const offsets = cellsMatch[0]
      .match(/<offsets>[\s\S]*?<\/offsets>/)
    if (connectivity && offsets) {
      const connVals = conn[0]
        .match(/-?\d+/g)
        ?.map(Number) ?? []
      const offsetVals = offsets[0]
        .match(/-?\d+/g)
        ?.map(Number) ?? []
      let ptr = 0
      for (const off of offsetVals) {
        const size = off - ptr
        if (size === 3) {
          faces.push([connVals[ptr], connVals[ptr + 1], connVals[ptr + 2]])
        }
        ptr = off
      }
    }
  }

  return { vertices, faces }
}

function parseBinaryMesh(buf) {
  const view = new DataView(buf)
  const vertices = []
  const faces = []

  try {
    const nVerts = view.getUint32(0, true)
    let off = 4
    for (let i = 0; i < nVerts; i++) {
      const x = view.getFloat32(off, true); off += 4
      const y = view.getFloat32(off, true); off += 4
      const z = view.getFloat32(off, true); off += 4
      const d = view.getFloat32(off, true); off += 4
      vertices.push({ x, y, z, density: d })
    }
    const nFaces = view.getUint32(off, true); off += 4
    for (let i = 0; i < nFaces; i++) {
      const a = view.getUint32(off, true); off += 4
      const b = view.getUint32(off, true); off += 4
      const c = view.getUint32(off, true); off += 4
      faces.push([a, b, c])
    }
  } catch (_e) {
    throw new Error('Unrecognized mesh format. Expected binary Float32 density mesh.')
  }

  return { vertices, faces }
}

/**
 * Map a normalized t ∈ [0,1] to the viridis RGBA colormap.
 * Returns [r, g, b] with values in [0, 1].
 */
export function viridis(t) {
  t = clamp(t, 0, 1)
  const r = clamp(0.267004 + t * (0.282110 + t * (-0.926855 + t * 1.049935)), 0, 1)
  const g = clamp(0.004874 + t * (0.873465 + t * (-0.460868 + t * 0.535200)), 0, 1)
  const b = clamp(0.329415 + t * (0.278826 + t * (0.616406 + t * (-1.486650))), 0, 1)
  return [r, g, b]
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v))
}

/**
 * Build a minimal GLTF 2.0 binary from vertices, faces, and vertex colors.
 * Returns an ArrayBuffer in GLB format (binary GLTF).
 */
function buildGLTF(vertices, faces, vertexColors) {
  const nVerts = vertices.length
  const nFaces = faces.length

  const posArr = new Float32Array(nVerts * 3)
  for (let i = 0; i < nVerts; i++) {
    posArr[i * 3 + 0] = vertices[i].x
    posArr[i * 3 + 1] = vertices[i].y
    posArr[i * 3 + 2] = vertices[i].z
  }

  const colorArr = vertexColors

  const idxArr = new Uint32Array(nFaces * 3)
  for (let i = 0; i < nFaces; i++) {
    idxArr[i * 3 + 0] = faces[i][0]
    idxArr[i * 3 + 1] = faces[i][1]
    idxArr[i * 3 + 2] = faces[i][2]
  }

  const posBytes = posArr.byteLength
  const colorBytes = colorArr.byteLength
  const idxBytes = idxArr.byteLength

  const buf1Off = 0
  const buf2Off = buf1Off + posBytes
  const buf3Off = buf2Off + colorBytes
  const totalBytes = buf3Off + idxBytes

  const glbBuf = new ArrayBuffer(totalBytes)
  const view = new DataView(glbBuf)

  new Float32Array(glbBuf, buf1Off, posArr.length).set(posArr)
  new Float32Array(glbBuf, buf2Off, colorArr.length / 4).set(colorArr)
  new Uint32Array(glbBuf, buf3Off, idxArr.length).set(idxArr)

  const json = {
    asset: { version: '2.0', generator: 'kerf-topo-utils' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{
      primitives: [{
        attributes: { POSITION: 0, COLOR_0: 1 },
        indices: 2,
        mode: 4,
      }],
    }],
    buffers: [{ byteLength: totalBytes }],
    bufferViews: [
      { buffer: 0, byteOffset: buf1Off, byteLength: posBytes, target: 34962 },
      { buffer: 0, byteOffset: buf2Off, byteLength: colorBytes, target: 34962 },
      { buffer: 0, byteOffset: buf3Off, byteLength: idxBytes, target: 34963 },
    ],
    accessors: [
      { bufferView: 0, byteOffset: 0, componentType: 5126, count: nVerts, type: 'VEC3', max: [posArr[0], posArr[1], posArr[2]], min: [posArr[0], posArr[1], posArr[2]] },
      { bufferView: 1, byteOffset: 0, componentType: 5126, count: nVerts, type: 'VEC4' },
      { bufferView: 2, byteOffset: 0, componentType: 5125, count: nFaces * 3, type: 'SCALAR' },
    ],
  }

  const jsonStr = JSON.stringify(json)
  const jsonBytes = new TextEncoder().encode(jsonStr)
  const jsonAligned = Math.ceil(jsonBytes.length / 4) * 4
  const pad = jsonAligned - jsonBytes.length

  const glbHeader = 12
  const glbJsonHeader = 8
  const glbBinHeader = 8
  const totalGlbSize = glbHeader + glbJsonHeader + jsonAligned + glbBinHeader + totalBytes

  const glb = new ArrayBuffer(totalGlbSize)
  const glbView = new DataView(glb)
  const glbBytes = new Uint8Array(glb)

  glbView.setUint32(0, 0x46546C67, true)
  glbView.setUint32(4, 2, true)
  glbView.setUint32(8, totalGlbSize, true)

  glbView.setUint32(12, glbJsonHeader + jsonAligned - 8, true)
  glbView.setUint32(16, 0x4E4F534A, true)

  glbBytes.set(jsonBytes, 20)
  for (let i = 0; i < pad; i++) glbBytes[20 + jsonBytes.length + i] = 0

  glbView.setUint32(20 + jsonAligned, totalBytes, true)
  glbView.setUint32(20 + jsonAligned + 4, 0x004E4942, true)
  glbBytes.set(new Uint8Array(glbBuf), 20 + jsonAligned + 8)

  return glb
}

let _authGetter
try {
  const { useAuth } = require('./store/auth.js')
  _authGetter = () => useAuth.getState()
} catch (_e) {
  _authGetter = () => ({ accessToken: '' })
}

let _refreshFn
try {
  const { refreshAccessToken } = require('./api.js')
  _refreshFn = refreshAccessToken
} catch (_e) {
  _refreshFn = async () => ''
}