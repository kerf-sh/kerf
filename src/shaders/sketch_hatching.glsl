// sketch_hatching.glsl — Screen-space cross-hatching for the Sketch render style.
//
// Derives hatch density from scene luminance: dark areas get heavy cross-hatch,
// bright areas are left clean. Combine with cel_outline.glsl to produce a
// pencil-on-paper silhouette+hatching look.

uniform sampler2D tDiffuse;  // colour buffer (post cel_outline or raw scene)
uniform vec2      texelSize; // vec2(1/width, 1/height)
uniform float     hatchScale;   // pixel spacing between hatch lines  (default 6.0)
uniform float     hatchWeight;  // line darkness weight               (default 0.7)

varying vec2 vUv;

// ── Helpers ───────────────────────────────────────────────────────────────────

// Return 1.0 if pixel falls on a diagonal hatch line at given angle.
float hatchLine(vec2 fragCoord, float angle, float scale) {
  float s = sin(angle);
  float c = cos(angle);
  // Project pixel onto the line's perpendicular axis.
  float proj = fragCoord.x * c + fragCoord.y * s;
  return step(scale - 1.0, mod(proj, scale));
}

void main() {
  vec4  scene      = texture2D(tDiffuse, vUv);
  float luminance  = dot(scene.rgb, vec3(0.2126, 0.7152, 0.0722));

  // Convert UV to pixel coordinates for crisp integer-aligned hatch lines.
  vec2 fragCoord = vUv / texelSize;

  float hatching = 0.0;

  // Layer 1: 45° lines appear when luminance < 0.7.
  if (luminance < 0.7)
    hatching += hatchLine(fragCoord, radians(45.0), hatchScale);

  // Layer 2: 135° lines (cross-hatch) appear in darker regions < 0.4.
  if (luminance < 0.4)
    hatching += hatchLine(fragCoord, radians(135.0), hatchScale);

  // Layer 3: horizontal lines for very dark < 0.2.
  if (luminance < 0.2)
    hatching += hatchLine(fragCoord, radians(0.0), hatchScale);

  hatching = clamp(hatching, 0.0, 1.0);

  // Blend hatch lines (dark) into the scene.
  vec3 col = mix(scene.rgb, vec3(0.1), hatching * hatchWeight);
  gl_FragColor = vec4(col, scene.a);
}
