/**
 * dayNightCycle.js — Pure-JS time-to-sun-position mapping for the day/night
 * cycle UI.
 *
 * T ∈ [0, 1) covers one 24-hour solar cycle:
 *   T = 0.00 → 00:00 midnight (start)
 *   T = 0.25 → 06:00 sunrise
 *   T = 0.50 → 12:00 solar noon (elevation = 90°)
 *   T = 0.75 → 18:00 sunset
 *   T = 1.00 → 24:00 = next midnight
 *
 * Wait — the spec says T=0.25 → noon (elev=90) and T=0.75 → midnight
 * (elev=−45). That maps T through a full cycle where:
 *   T = 0.00 → pre-dawn (elev ≈ −45)
 *   T = 0.25 → solar noon (elev = 90)
 *   T = 0.50 → post-dusk (elev ≈ −45)
 *   T = 0.75 → midnight   (elev = −45)
 *
 * We treat T as a normalised clock angle where T=0.25 aligns with the
 * peak (90°). Elevation oscillates as a cosine centred on T=0.25 for the
 * day lobe, so:
 *
 *   angle = 2π(T − 0.25)
 *   elevation_rad = −π/4 + (π/2 + π/4) * (1 + cos(angle)) / 2
 *                 = −π/4 + (3π/4) * (1 + cos(angle)) / 2
 *
 * This yields:
 *   T=0.25 → cos(0)=1   → elev = −π/4 + 3π/4 = π/2 = 90°  ✓
 *   T=0.75 → cos(π)=−1  → elev = −π/4 + 0    = −45°       ✓
 *   T=0.00 → cos(−π/2)=0 → elev = −π/4 + 3π/8 ≈ 22.5°
 *
 * Azimuth sweeps 0°→360° linearly (east→south→west→north):
 *   azimuth = (T * 360) % 360
 *
 * Color temperature:
 *   Night   (elev < −10°) → 1500 K  (deep orange-red, tungsten)
 *   Horizon (elev ≈ 0°)   → 2200 K  (golden sunrise/set)
 *   Day     (elev = 90°)  → 6500 K  (overcast daylight)
 *   Smooth spline between the three control points.
 *
 * Turbidity:
 *   Night → 10 (thick atmosphere/scattering)
 *   Horizon → 4
 *   Zenith → 2 (clean sky)
 *
 * No DOM, no browser, no imports — suitable for workers and unit tests.
 */

// ── Constants ──────────────────────────────────────────────────────────────────

const TWO_PI = 2 * Math.PI;
const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;

// Minimum elevation (°) for the deepest night point (T=0.75).
const MIN_ELEV_DEG = -45;
// Maximum elevation (°) at noon (T=0.25).
const MAX_ELEV_DEG = 90;

// Color temperature key-frames: [elevation_deg, kelvin]
const CT_KEYFRAMES = [
  [-45, 1500],
  [-10, 1800],
  [  0, 2200],
  [ 15, 4000],
  [ 30, 5000],
  [ 60, 5800],
  [ 90, 6500],
];

// Turbidity key-frames: [elevation_deg, turbidity]
const TURBIDITY_KEYFRAMES = [
  [-45, 10],
  [  0,  4],
  [ 90,  2],
];

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Clamp a value between lo and hi.
 * @param {number} v
 * @param {number} lo
 * @param {number} hi
 * @returns {number}
 */
function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

/**
 * Linear interpolation between two [x, y] key-frames at position x.
 * Assumes keyframes is sorted ascending by keyframes[i][0].
 * @param {Array<[number,number]>} keyframes
 * @param {number} x
 * @returns {number}
 */
function lerp1D(keyframes, x) {
  if (x <= keyframes[0][0]) return keyframes[0][1];
  if (x >= keyframes[keyframes.length - 1][0]) return keyframes[keyframes.length - 1][1];
  for (let i = 0; i < keyframes.length - 1; i++) {
    const [x0, y0] = keyframes[i];
    const [x1, y1] = keyframes[i + 1];
    if (x >= x0 && x <= x1) {
      const t = (x - x0) / (x1 - x0);
      return y0 + t * (y1 - y0);
    }
  }
  return keyframes[keyframes.length - 1][1];
}

// ── Core mapping ───────────────────────────────────────────────────────────────

/**
 * Convert a normalised time T ∈ [0, 1) into solar position and sky parameters.
 *
 * @param {number} t  Normalised time, 0 ≤ t < 1.
 *                    t=0.25 → solar noon; t=0.75 → midnight.
 * @returns {{
 *   t: number,
 *   elevation_deg: number,    Sun elevation above horizon (°). 90 at noon.
 *   azimuth_deg: number,      Sun azimuth, 0=N, 90=E, 180=S, 270=W (°).
 *   color_temp_K: number,     Correlated color temperature (K).
 *   turbidity: number,        Atmospheric turbidity (dimensionless).
 *   is_day: boolean,          True when sun is above the horizon.
 * }}
 */
export function solarPosition(t) {
  // Wrap t into [0, 1)
  t = ((t % 1) + 1) % 1;

  // Elevation: cosine centred on T=0.25 (noon)
  const angle = TWO_PI * (t - 0.25);
  const cosAngle = Math.cos(angle);
  // Map cos ∈ [−1, 1] → elevation ∈ [MIN_ELEV_DEG, MAX_ELEV_DEG]
  const elevation_deg =
    MIN_ELEV_DEG + ((MAX_ELEV_DEG - MIN_ELEV_DEG) * (1 + cosAngle)) / 2;

  // Azimuth: linear sweep over 24 h (0°→360°)
  const azimuth_deg = ((t * 360) + 180) % 360;

  // Color temperature and turbidity from elevation
  const color_temp_K = Math.round(lerp1D(CT_KEYFRAMES, elevation_deg));
  const turbidity = lerp1D(TURBIDITY_KEYFRAMES, elevation_deg);

  const is_day = elevation_deg > 0;

  return { t, elevation_deg, azimuth_deg, color_temp_K, turbidity, is_day };
}

/**
 * Return a human-readable clock string for normalised time t.
 * t=0 → "00:00", t=0.5 → "12:00", t=0.25 → "06:00".
 *
 * @param {number} t
 * @returns {string}  e.g. "06:30"
 */
export function tToClockString(t) {
  t = ((t % 1) + 1) % 1;
  const totalMinutes = Math.round(t * 24 * 60) % (24 * 60);
  const h = Math.floor(totalMinutes / 60);
  const m = totalMinutes % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Convert a clock string "HH:MM" to normalised time t ∈ [0, 1).
 *
 * @param {string} clockStr  e.g. "12:00"
 * @returns {number}
 */
export function clockStringToT(clockStr) {
  const [h, m] = clockStr.split(':').map(Number);
  return (h * 60 + (m || 0)) / (24 * 60);
}

/**
 * Linear-interpolate between two solar position snapshots.
 * Useful for smooth animation frames.
 *
 * @param {number} t0  Start time (normalised)
 * @param {number} t1  End time (normalised)
 * @param {number} alpha  Blend factor 0..1
 * @returns {ReturnType<solarPosition>}
 */
export function lerpSolar(t0, t1, alpha) {
  const a = solarPosition(t0);
  const b = solarPosition(t1);
  const blend = (va, vb) => va + (vb - va) * alpha;
  return {
    t: blend(a.t, b.t),
    elevation_deg: blend(a.elevation_deg, b.elevation_deg),
    azimuth_deg: blend(a.azimuth_deg, b.azimuth_deg),
    color_temp_K: Math.round(blend(a.color_temp_K, b.color_temp_K)),
    turbidity: blend(a.turbidity, b.turbidity),
    is_day: alpha < 0.5 ? a.is_day : b.is_day,
  };
}

// ── Animation clock ────────────────────────────────────────────────────────────

/**
 * Create a self-contained animation clock for the day/night cycle.
 *
 * The clock drives t from 0 to 1 cyclically.  Playback speed is expressed
 * as "real seconds per simulated day".  A speed of 60 means one full day
 * completes in 60 real seconds.
 *
 * @param {{
 *   initialT?: number,
 *   speed?: number,      Seconds of real time per simulated day (default 60).
 *   onTick?: (pos: ReturnType<solarPosition>) => void,
 * }} options
 * @returns {{
 *   play: () => void,
 *   pause: () => void,
 *   setT: (t: number) => void,
 *   setSpeed: (s: number) => void,
 *   getState: () => { t: number, playing: boolean, speed: number },
 *   destroy: () => void,
 * }}
 */
export function createClock({ initialT = 0, speed = 60, onTick } = {}) {
  let t = clamp(initialT, 0, 1);
  let _speed = speed;
  let playing = false;
  let _raf = null;
  let _lastTs = null;

  function tick(now) {
    if (!playing) return;
    if (_lastTs !== null) {
      const dt = (now - _lastTs) / 1000; // seconds
      t = (t + dt / _speed) % 1;
      if (t < 0) t += 1;
      if (onTick) onTick(solarPosition(t));
    }
    _lastTs = now;
    if (typeof requestAnimationFrame !== 'undefined') {
      _raf = requestAnimationFrame(tick);
    }
  }

  return {
    play() {
      if (playing) return;
      playing = true;
      _lastTs = null;
      if (typeof requestAnimationFrame !== 'undefined') {
        _raf = requestAnimationFrame(tick);
      }
    },
    pause() {
      playing = false;
      _lastTs = null;
      if (_raf !== null && typeof cancelAnimationFrame !== 'undefined') {
        cancelAnimationFrame(_raf);
        _raf = null;
      }
    },
    setT(newT) {
      t = ((newT % 1) + 1) % 1;
      if (onTick) onTick(solarPosition(t));
    },
    setSpeed(s) {
      _speed = s > 0 ? s : 1;
    },
    getState() {
      return { t, playing, speed: _speed };
    },
    destroy() {
      this.pause();
    },
  };
}
