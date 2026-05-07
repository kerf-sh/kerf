// scripts/step-tessellate.mjs — Node sidecar for the server-side STEP
// pre-tessellation pipeline (Performance Phase 3).
//
// Protocol (JSON-over-stdio, one shot per process invocation):
//
//   stdin  : {"step_b64": "<base64 STEP bytes>"}
//   stdout : {"glb_b64":  "<base64 GLB bytes>"}      on success
//   stdout : {"error":    "<human-readable message>"} on failure
//
// The Go worker spawns one of these per job. occt-import-js parses the
// STEP into a list of meshes; this script then assembles a minimal glTF
// 2.0 binary (.glb) containing those meshes so the browser can use a
// cheap GLTFLoader instead of re-running the heavy WASM parser.
//
// Why hand-roll the glTF emitter rather than depend on a npm package:
// the OSS install footprint is "node + node_modules from this repo",
// nothing more. occt-import-js is already a project dep; pulling in
// gltf-transform / @gltf-transform/core would balloon the image. The
// glTF 2.0 binary container is ~150 lines of structured JSON + a single
// binary chunk — well within "write once, never touch again" scope.

import { Buffer } from 'node:buffer'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve as resolvePath } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const requireCJS = createRequire(import.meta.url)

// Minimal stderr logger. Stdout is reserved for the JSON response — anything
// non-JSON the Go side may flag as a protocol violation.
const log = (...args) => { process.stderr.write(args.join(' ') + '\n') }

async function readAllStdin() {
  return new Promise((resolve, reject) => {
    const chunks = []
    process.stdin.on('data', (c) => chunks.push(c))
    process.stdin.on('end', () => resolve(Buffer.concat(chunks)))
    process.stdin.on('error', reject)
  })
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n')
}

// Resolve the occt-import-js module relative to the repo root.
// In production we expect node_modules/ alongside the script's parent.
function loadOcctModule() {
  // Try the standard CJS resolution first.
  try {
    return requireCJS('occt-import-js')
  } catch (e1) {
    // Fall back to a path-based resolve from the script's directory and
    // a few common deploy layouts.
    const candidates = [
      resolvePath(__dirname, '..', 'node_modules', 'occt-import-js'),
      resolvePath(__dirname, 'node_modules', 'occt-import-js'),
      resolvePath(process.cwd(), 'node_modules', 'occt-import-js'),
    ]
    for (const dir of candidates) {
      try {
        return requireCJS(dir)
      } catch { /* continue */ }
    }
    throw new Error(`occt-import-js not found (tried require() and ${candidates.join(', ')}): ${e1?.message || e1}`)
  }
}

// occt-import-js ships its .wasm next to the JS bundle. The Emscripten
// Node loader handles this automatically when `__filename` is correct;
// we provide an explicit locateFile in case the user's working directory
// differs.
function instantiateOcct(occtModule) {
  const factory = occtModule.default || occtModule
  return factory({
    locateFile: (path, scriptDir) => {
      if (path.endsWith('.wasm')) {
        // First try sibling-of-script (the normal case).
        const candidates = [
          scriptDir ? resolvePath(scriptDir, path) : null,
          resolvePath(__dirname, '..', 'node_modules', 'occt-import-js', 'dist', path),
          resolvePath(process.cwd(), 'node_modules', 'occt-import-js', 'dist', path),
        ].filter(Boolean)
        for (const c of candidates) {
          try {
            // Just probe — the loader will read it itself.
            readFileSync(c)
            return c
          } catch { /* keep looking */ }
        }
      }
      return path
    },
  })
}

// --- glTF 2.0 emitter ------------------------------------------------------
//
// One mesh per OCCT solid. Each mesh has POSITION + NORMAL accessors and
// a primitive in TRIANGLES mode. We pack everything into a single binary
// buffer + write a .glb container. Indices are uint32; positions/normals
// are float32; per-mesh material color (RGB) becomes a baseColorFactor
// when the OCCT mesh exposes one.
//
// glb layout (little-endian throughout):
//   header:       magic 0x46546c67 'glTF', version=2, length=total
//   chunk 0 JSON: length, type=0x4e4f534a 'JSON', payload (padded to 4)
//   chunk 1 BIN:  length, type=0x004e4942 'BIN\0', payload (padded to 4)

function alignTo4(n) { return (n + 3) & ~3 }

function colorToRgba(c) {
  // OCCT colors come through as [r,g,b] floats in 0..1, sometimes with
  // a 4th alpha element. Return [r,g,b,a] suitable for baseColorFactor.
  if (!Array.isArray(c) || c.length < 3) return [0.7, 0.7, 0.75, 1.0]
  const r = clamp01(c[0])
  const g = clamp01(c[1])
  const b = clamp01(c[2])
  const a = c.length >= 4 ? clamp01(c[3]) : 1.0
  return [r, g, b, a]
}

function clamp01(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0
  if (v < 0) return 0
  if (v > 1) return 1
  return v
}

function buildGLB(meshes) {
  // Collect binary payload chunks first; we'll know offsets/lengths by
  // the time we serialize the JSON.
  const binChunks = []
  let binLength = 0

  const accessors = []
  const bufferViews = []
  const materials = []
  const meshDefs = []
  const nodes = []

  // Helper: append bytes to the bin payload, return [bufferViewIndex,
  // byteOffset, byteLength]. The bufferView always references buffer 0.
  function pushBufferView(bytes, target) {
    const padded = alignTo4(bytes.byteLength)
    const buf = padded === bytes.byteLength ? bytes : (() => {
      const padBuf = Buffer.alloc(padded)
      bytes.copy(padBuf, 0)
      return padBuf
    })()
    binChunks.push(buf)
    const bv = {
      buffer: 0,
      byteOffset: binLength,
      byteLength: bytes.byteLength,
    }
    if (target !== undefined) bv.target = target
    binLength += padded
    bufferViews.push(bv)
    return bufferViews.length - 1
  }

  // glTF accessor componentType: 5126 = FLOAT, 5125 = UNSIGNED_INT
  // target: 34962 = ARRAY_BUFFER (vertex attribs), 34963 = ELEMENT_ARRAY_BUFFER (indices)
  const COMP_FLOAT = 5126
  const COMP_UINT = 5125
  const TARGET_VBO = 34962
  const TARGET_IBO = 34963

  for (let i = 0; i < meshes.length; i++) {
    const mesh = meshes[i]
    const positions = mesh?.attributes?.position?.array
    const normals = mesh?.attributes?.normal?.array
    const indices = mesh?.index?.array
    if (!positions || !positions.length) continue

    const posF32 = positions instanceof Float32Array ? positions : new Float32Array(positions)
    let normF32 = null
    if (normals && normals.length === positions.length) {
      normF32 = normals instanceof Float32Array ? normals : new Float32Array(normals)
    } else {
      normF32 = computeFlatNormals(posF32, indices)
    }
    const idxU32 = indices && indices.length
      ? (indices instanceof Uint32Array ? indices : new Uint32Array(indices))
      : null

    // Pack position into a Buffer.
    const posBytes = Buffer.from(posF32.buffer, posF32.byteOffset, posF32.byteLength).slice()
    const posBV = pushBufferView(posBytes, TARGET_VBO)
    const posMin = [posF32[0], posF32[1], posF32[2]]
    const posMax = [posF32[0], posF32[1], posF32[2]]
    for (let p = 0; p < posF32.length; p += 3) {
      for (let c = 0; c < 3; c++) {
        const v = posF32[p + c]
        if (v < posMin[c]) posMin[c] = v
        if (v > posMax[c]) posMax[c] = v
      }
    }
    accessors.push({
      bufferView: posBV,
      componentType: COMP_FLOAT,
      count: posF32.length / 3,
      type: 'VEC3',
      min: posMin,
      max: posMax,
    })
    const posAcc = accessors.length - 1

    const normBytes = Buffer.from(normF32.buffer, normF32.byteOffset, normF32.byteLength).slice()
    const normBV = pushBufferView(normBytes, TARGET_VBO)
    accessors.push({
      bufferView: normBV,
      componentType: COMP_FLOAT,
      count: normF32.length / 3,
      type: 'VEC3',
    })
    const normAcc = accessors.length - 1

    let idxAcc = -1
    if (idxU32) {
      const idxBytes = Buffer.from(idxU32.buffer, idxU32.byteOffset, idxU32.byteLength).slice()
      const idxBV = pushBufferView(idxBytes, TARGET_IBO)
      accessors.push({
        bufferView: idxBV,
        componentType: COMP_UINT,
        count: idxU32.length,
        type: 'SCALAR',
      })
      idxAcc = accessors.length - 1
    }

    materials.push({
      pbrMetallicRoughness: {
        baseColorFactor: colorToRgba(mesh.color),
        metallicFactor: 0.1,
        roughnessFactor: 0.8,
      },
      doubleSided: true,
      name: `mat_${i}`,
    })
    const matIdx = materials.length - 1

    const prim = {
      attributes: { POSITION: posAcc, NORMAL: normAcc },
      mode: 4, // TRIANGLES
      material: matIdx,
    }
    if (idxAcc >= 0) prim.indices = idxAcc

    meshDefs.push({ primitives: [prim], name: mesh.name || `step_${i}` })
    nodes.push({ mesh: meshDefs.length - 1, name: mesh.name || `step_${i}` })
  }

  if (meshDefs.length === 0) {
    throw new Error('STEP parsed but produced no meshes')
  }

  const sceneNodes = nodes.map((_, i) => i)
  const gltf = {
    asset: { version: '2.0', generator: 'kerf-step-tessellate' },
    scene: 0,
    scenes: [{ nodes: sceneNodes }],
    nodes,
    meshes: meshDefs,
    materials,
    accessors,
    bufferViews,
    buffers: [{ byteLength: binLength }],
  }

  // Concat binary payload. Buffer.concat handles the padding we already
  // baked into each chunk via alignTo4.
  const binPayload = Buffer.concat(binChunks, binLength)

  // Build JSON chunk.
  const jsonStr = JSON.stringify(gltf)
  const jsonBuf = Buffer.from(jsonStr, 'utf-8')
  const jsonPadded = alignTo4(jsonBuf.byteLength)
  const jsonPayload = Buffer.alloc(jsonPadded, 0x20) // pad with spaces per spec
  jsonBuf.copy(jsonPayload, 0)

  // Header (12 bytes) + chunk0 header (8 bytes) + chunk0 payload + chunk1 header (8 bytes) + chunk1 payload
  const totalLen = 12 + 8 + jsonPayload.byteLength + 8 + binPayload.byteLength
  const out = Buffer.alloc(totalLen)
  let o = 0
  // GLB header
  out.writeUInt32LE(0x46546c67, o); o += 4 // 'glTF'
  out.writeUInt32LE(2, o); o += 4
  out.writeUInt32LE(totalLen, o); o += 4
  // JSON chunk
  out.writeUInt32LE(jsonPayload.byteLength, o); o += 4
  out.writeUInt32LE(0x4e4f534a, o); o += 4 // 'JSON'
  jsonPayload.copy(out, o); o += jsonPayload.byteLength
  // BIN chunk
  out.writeUInt32LE(binPayload.byteLength, o); o += 4
  out.writeUInt32LE(0x004e4942, o); o += 4 // 'BIN\0'
  binPayload.copy(out, o); o += binPayload.byteLength
  return out
}

// computeFlatNormals: when occt-import-js doesn't supply per-vertex
// normals (rare but defensive), compute one normal per triangle and
// duplicate to its three vertices. Indexed and non-indexed meshes are
// both handled.
function computeFlatNormals(positions, indices) {
  const out = new Float32Array(positions.length)
  if (indices && indices.length) {
    for (let i = 0; i < indices.length; i += 3) {
      const ia = indices[i] * 3
      const ib = indices[i + 1] * 3
      const ic = indices[i + 2] * 3
      const ax = positions[ia], ay = positions[ia + 1], az = positions[ia + 2]
      const bx = positions[ib], by = positions[ib + 1], bz = positions[ib + 2]
      const cx = positions[ic], cy = positions[ic + 1], cz = positions[ic + 2]
      const ux = bx - ax, uy = by - ay, uz = bz - az
      const vx = cx - ax, vy = cy - ay, vz = cz - az
      let nx = uy * vz - uz * vy
      let ny = uz * vx - ux * vz
      let nz = ux * vy - uy * vx
      const len = Math.hypot(nx, ny, nz) || 1
      nx /= len; ny /= len; nz /= len
      for (const idx of [ia, ib, ic]) {
        out[idx] += nx; out[idx + 1] += ny; out[idx + 2] += nz
      }
    }
  } else {
    for (let i = 0; i < positions.length; i += 9) {
      const ax = positions[i], ay = positions[i + 1], az = positions[i + 2]
      const bx = positions[i + 3], by = positions[i + 4], bz = positions[i + 5]
      const cx = positions[i + 6], cy = positions[i + 7], cz = positions[i + 8]
      const ux = bx - ax, uy = by - ay, uz = bz - az
      const vx = cx - ax, vy = cy - ay, vz = cz - az
      let nx = uy * vz - uz * vy
      let ny = uz * vx - ux * vz
      let nz = ux * vy - uy * vx
      const len = Math.hypot(nx, ny, nz) || 1
      nx /= len; ny /= len; nz /= len
      for (let k = 0; k < 9; k += 3) {
        out[i + k] = nx; out[i + k + 1] = ny; out[i + k + 2] = nz
      }
    }
  }
  // Re-normalize accumulated indexed normals.
  if (indices && indices.length) {
    for (let i = 0; i < out.length; i += 3) {
      const len = Math.hypot(out[i], out[i + 1], out[i + 2]) || 1
      out[i] /= len; out[i + 1] /= len; out[i + 2] /= len
    }
  }
  return out
}

// --- main ------------------------------------------------------------------

async function main() {
  let payload
  try {
    const stdinBuf = await readAllStdin()
    if (!stdinBuf.length) {
      emit({ error: 'empty stdin' })
      process.exit(1)
    }
    payload = JSON.parse(stdinBuf.toString('utf-8'))
  } catch (err) {
    emit({ error: 'invalid request: ' + (err?.message || err) })
    process.exit(1)
    return
  }
  if (!payload?.step_b64 || typeof payload.step_b64 !== 'string') {
    emit({ error: 'request missing step_b64' })
    process.exit(1)
    return
  }

  let stepBytes
  try {
    stepBytes = Buffer.from(payload.step_b64, 'base64')
  } catch (err) {
    emit({ error: 'invalid base64: ' + (err?.message || err) })
    process.exit(1)
    return
  }
  if (!stepBytes.length) {
    emit({ error: 'empty step bytes' })
    process.exit(1)
    return
  }

  let occt
  try {
    const mod = loadOcctModule()
    occt = await instantiateOcct(mod)
  } catch (err) {
    emit({ error: 'load occt: ' + (err?.message || err) })
    process.exit(1)
    return
  }

  let result
  try {
    result = occt.ReadStepFile(new Uint8Array(stepBytes), null)
  } catch (err) {
    emit({ error: 'occt parse threw: ' + (err?.message || err) })
    process.exit(1)
    return
  }
  if (!result || !result.success) {
    emit({ error: 'occt parse failed' })
    process.exit(1)
    return
  }
  const meshes = result.meshes || []
  if (!meshes.length) {
    emit({ error: 'STEP contained no meshes' })
    process.exit(1)
    return
  }

  let glb
  try {
    glb = buildGLB(meshes)
  } catch (err) {
    emit({ error: 'build glb: ' + (err?.message || err) })
    process.exit(1)
    return
  }

  emit({ glb_b64: glb.toString('base64') })
}

main().catch((err) => {
  log('sidecar fatal:', err?.stack || err)
  emit({ error: 'fatal: ' + (err?.message || err) })
  process.exit(1)
})
