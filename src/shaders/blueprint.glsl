// blueprint.glsl — Blueprint render style: white-on-blue with edge detection.
//
// Converts scene colour to white-on-blue: the background becomes blueprint blue,
// geometry edges (detected via constant-weight Sobel) are drawn in white.
// Non-edge pixels are tinted with the blueprint blue to wash out colour.

uniform sampler2D tDiffuse;  // colour buffer from the previous pass
uniform sampler2D tDepth;    // depth buffer
uniform vec2      texelSize; // vec2(1/width, 1/height)
uniform float     edgeWeight; // Sobel edge blend weight (default 1.0)

varying vec2 vUv;

// ── Blueprint palette ─────────────────────────────────────────────────────────
const vec3 BLUEPRINT_BG    = vec3(0.055, 0.141, 0.420); // Prussian blue
const vec3 BLUEPRINT_EDGE  = vec3(0.95,  0.97,  1.0);   // near-white
const float EDGE_THRESHOLD = 0.0008;

// ── Helpers ───────────────────────────────────────────────────────────────────

float readDepth(vec2 uv) {
  return texture2D(tDepth, uv).r;
}

void main() {
  // Sobel on depth to detect edges.
  float d00 = readDepth(vUv + texelSize * vec2(-1.0, -1.0));
  float d10 = readDepth(vUv + texelSize * vec2( 0.0, -1.0));
  float d20 = readDepth(vUv + texelSize * vec2( 1.0, -1.0));
  float d01 = readDepth(vUv + texelSize * vec2(-1.0,  0.0));
  float d21 = readDepth(vUv + texelSize * vec2( 1.0,  0.0));
  float d02 = readDepth(vUv + texelSize * vec2(-1.0,  1.0));
  float d12 = readDepth(vUv + texelSize * vec2( 0.0,  1.0));
  float d22 = readDepth(vUv + texelSize * vec2( 1.0,  1.0));

  float gx = -d00 + d20 - 2.0*d01 + 2.0*d21 - d02 + d22;
  float gy = -d00 - 2.0*d10 - d20 + d02 + 2.0*d12 + d22;
  float edge = sqrt(gx*gx + gy*gy);
  float isEdge = step(EDGE_THRESHOLD, edge) * edgeWeight;

  // Background pixels (depth == 1.0 in most projections) stay pure blueprint.
  float depth = readDepth(vUv);
  float isBackground = step(0.9999, depth);

  // Tint non-background pixels with a blue wash, edges become white.
  vec3 col = mix(BLUEPRINT_BG, BLUEPRINT_EDGE, isEdge);
  col = mix(col, BLUEPRINT_BG, isBackground * (1.0 - isEdge));

  gl_FragColor = vec4(col, 1.0);
}
