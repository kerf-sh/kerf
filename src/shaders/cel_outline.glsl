// cel_outline.glsl — Sobel edge-detection pass for Cel and Sketch render styles.
//
// Samples the depth buffer with a 3×3 Sobel kernel to find silhouette edges,
// then composites a dark outline over the scene colour. Used by:
//   - Cel    style: draws hard outlines around objects (black lines).
//   - Sketch style: combined with sketch_hatching.glsl for pencil-on-paper look.

uniform sampler2D tDiffuse;   // colour buffer from the previous pass
uniform sampler2D tDepth;     // depth buffer
uniform vec2      texelSize;  // vec2(1/width, 1/height)
uniform float     outlineThreshold; // depth-difference threshold (default 0.001)
uniform vec3      outlineColor;     // outline colour (default vec3(0.0))

varying vec2 vUv;

// ── Helpers ───────────────────────────────────────────────────────────────────

float readDepth(vec2 uv) {
  return texture2D(tDepth, uv).r;
}

void main() {
  // Sample 3×3 depth neighbourhood for Sobel.
  float d00 = readDepth(vUv + texelSize * vec2(-1.0, -1.0));
  float d10 = readDepth(vUv + texelSize * vec2( 0.0, -1.0));
  float d20 = readDepth(vUv + texelSize * vec2( 1.0, -1.0));
  float d01 = readDepth(vUv + texelSize * vec2(-1.0,  0.0));
  float d21 = readDepth(vUv + texelSize * vec2( 1.0,  0.0));
  float d02 = readDepth(vUv + texelSize * vec2(-1.0,  1.0));
  float d12 = readDepth(vUv + texelSize * vec2( 0.0,  1.0));
  float d22 = readDepth(vUv + texelSize * vec2( 1.0,  1.0));

  // Sobel X and Y kernels.
  float gx = -d00 + d20 - 2.0*d01 + 2.0*d21 - d02 + d22;
  float gy = -d00 - 2.0*d10 - d20 + d02 + 2.0*d12 + d22;

  float edge = sqrt(gx*gx + gy*gy);
  float isEdge = step(outlineThreshold, edge);

  vec4 scene = texture2D(tDiffuse, vUv);
  vec3 col   = mix(scene.rgb, outlineColor, isEdge);
  gl_FragColor = vec4(col, scene.a);
}
