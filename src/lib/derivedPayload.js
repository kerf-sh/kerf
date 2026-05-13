import * as THREE from 'three'

export function encodePayload(kind, parts) {
  if (!Array.isArray(parts) || parts.length === 0) return null
  try {
    const data = parts.map(serializePart)
    const json = JSON.stringify(data)
    return textEncoder.encode(json)
  } catch {
    return null
  }
}

export async function decodePayload(kind, payload) {
  if (!(payload instanceof Uint8Array) || payload.length === 0) return []
  try {
    const json = textDecoder.decode(payload)
    const data = JSON.parse(json)
    if (!Array.isArray(data)) return []
    return data.map(deserializePart)
  } catch {
    return []
  }
}

const textEncoder = new TextEncoder()
const textDecoder = new TextDecoder()

function serializePart(part) {
  if (!part || typeof part !== 'object') return null
  const out = { id: part.id }
  if (part.color != null) out.color = part.color
  if (part.geom) {
    out.geom = serializeGeom(part.geom)
  }
  return out
}

function deserializePart(data) {
  if (!data || typeof data !== 'object') return null
  const out = { id: data.id }
  if (data.color != null) out.color = data.color
  if (data.geom) {
    out.geom = deserializeGeom(data.geom)
  }
  return out
}

function serializeGeom(geom) {
  if (!geom) return null
  if (geom.isBufferGeometry) {
    return serializeBufferGeometry(geom)
  }
  if (Array.isArray(geom.polygons)) {
    return { _kind: 'geom3', data: geom }
  }
  if (Array.isArray(geom.sides)) {
    return { _kind: 'geom2', data: geom }
  }
  return null
}

function deserializeGeom(obj) {
  if (!obj || typeof obj !== 'object') return null
  if (obj._kind === 'geom3') {
    return obj.data
  }
  if (obj._kind === 'geom2') {
    return obj.data
  }
  if (obj._kind === 'buffergeometry') {
    return deserializeBufferGeometry(obj.data)
  }
  return null
}

function serializeBufferGeometry(bg) {
  const out = { _kind: 'buffergeometry' }
  const pos = bg.getAttribute('position')
  if (pos) {
    out.position = { array: Array.from(pos.array), itemSize: pos.itemSize }
  }
  const norm = bg.getAttribute('normal')
  if (norm) {
    out.normal = { array: Array.from(norm.array), itemSize: norm.itemSize }
  }
  const idx = bg.getIndex()
  if (idx) {
    out.index = { array: Array.from(idx.array), itemSize: idx.itemSize }
  }
  return out
}

function deserializeBufferGeometry(data) {
  const bg = new THREE.BufferGeometry()
  if (data.position) {
    bg.setAttribute('position', new THREE.Float32BufferAttribute(data.position.array, data.position.itemSize))
  }
  if (data.normal) {
    bg.setAttribute('normal', new THREE.Float32BufferAttribute(data.normal.array, data.normal.itemSize))
  }
  if (data.index) {
    bg.setIndex(new THREE.Uint32BufferAttribute(data.index.array, data.index.itemSize))
  }
  bg.computeBoundingBox()
  bg.computeBoundingSphere()
  return bg
}
