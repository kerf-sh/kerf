import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  solarPosition,
  tToClockString,
  clockStringToT,
  lerpSolar,
  createClock,
} from './dayNightCycle.js';

// ── solarPosition ──────────────────────────────────────────────────────────────

describe('solarPosition — deterministic time→position', () => {
  it('T=0.25 gives elevation ≈ 90° (solar noon)', () => {
    const pos = solarPosition(0.25);
    expect(pos.elevation_deg).toBeCloseTo(90, 4);
  });

  it('T=0.75 gives elevation ≈ −45° (midnight nadir)', () => {
    const pos = solarPosition(0.75);
    expect(pos.elevation_deg).toBeCloseTo(-45, 4);
  });

  it('T=0.5 gives elevation midpoint (halfway between noon and midnight)', () => {
    // T=0.5 → angle=π/2 from noon → cos(π/2)=0 → elev = mid(-45, 90) = 22.5°
    const pos = solarPosition(0.5);
    expect(pos.elevation_deg).toBeCloseTo(22.5, 4);
  });

  it('T=0.0 gives elevation midpoint (same as T=0.5 by symmetry)', () => {
    const pos = solarPosition(0.0);
    expect(pos.elevation_deg).toBeCloseTo(22.5, 4);
  });

  it('returns t unchanged in the output', () => {
    const pos = solarPosition(0.33);
    expect(pos.t).toBeCloseTo(0.33, 6);
  });

  it('wraps T=1.0 back to T=0.0 result', () => {
    const pos0 = solarPosition(0.0);
    const pos1 = solarPosition(1.0);
    expect(pos1.elevation_deg).toBeCloseTo(pos0.elevation_deg, 6);
  });

  it('handles T > 1 by wrapping', () => {
    const posA = solarPosition(0.3);
    const posB = solarPosition(1.3);
    expect(posB.elevation_deg).toBeCloseTo(posA.elevation_deg, 5);
  });

  it('handles negative T by wrapping', () => {
    const posA = solarPosition(0.9);
    const posB = solarPosition(-0.1);
    expect(posB.elevation_deg).toBeCloseTo(posA.elevation_deg, 5);
  });

  it('azimuth is 0–360°', () => {
    for (const t of [0, 0.1, 0.25, 0.5, 0.75, 0.99]) {
      const { azimuth_deg } = solarPosition(t);
      expect(azimuth_deg).toBeGreaterThanOrEqual(0);
      expect(azimuth_deg).toBeLessThan(360);
    }
  });

  it('elevation is within [−45, 90]', () => {
    for (let i = 0; i <= 100; i++) {
      const { elevation_deg } = solarPosition(i / 100);
      expect(elevation_deg).toBeGreaterThanOrEqual(-45 - 1e-9);
      expect(elevation_deg).toBeLessThanOrEqual(90 + 1e-9);
    }
  });

  it('is_day is true when elevation > 0', () => {
    expect(solarPosition(0.25).is_day).toBe(true);
    expect(solarPosition(0.75).is_day).toBe(false);
  });
});

// ── color temperature ──────────────────────────────────────────────────────────

describe('color_temp_K', () => {
  it('noon color temp is ≈ 5500–6500 K', () => {
    const { color_temp_K } = solarPosition(0.25);
    expect(color_temp_K).toBeGreaterThanOrEqual(5500);
    expect(color_temp_K).toBeLessThanOrEqual(6500);
  });

  it('midnight color temp is near 1500 K', () => {
    const { color_temp_K } = solarPosition(0.75);
    expect(color_temp_K).toBeCloseTo(1500, -2);
  });

  it('color temp rises as sun rises toward noon', () => {
    const dawn = solarPosition(0.15).color_temp_K;
    const midMorning = solarPosition(0.20).color_temp_K;
    const noon = solarPosition(0.25).color_temp_K;
    expect(midMorning).toBeGreaterThan(dawn);
    expect(noon).toBeGreaterThan(midMorning);
  });

  it('color temp is an integer (rounded)', () => {
    const { color_temp_K } = solarPosition(0.3);
    expect(Number.isInteger(color_temp_K)).toBe(true);
  });
});

// ── turbidity ─────────────────────────────────────────────────────────────────

describe('turbidity', () => {
  it('turbidity at noon is lower than at night', () => {
    const noon = solarPosition(0.25).turbidity;
    const midnight = solarPosition(0.75).turbidity;
    expect(noon).toBeLessThan(midnight);
  });

  it('turbidity at midnight is ≈ 10', () => {
    const { turbidity } = solarPosition(0.75);
    expect(turbidity).toBeCloseTo(10, 1);
  });

  it('turbidity at noon is ≈ 2', () => {
    const { turbidity } = solarPosition(0.25);
    expect(turbidity).toBeCloseTo(2, 1);
  });
});

// ── tToClockString ─────────────────────────────────────────────────────────────

describe('tToClockString', () => {
  it('T=0 → "00:00"', () => {
    expect(tToClockString(0)).toBe('00:00');
  });

  it('T=0.5 → "12:00"', () => {
    expect(tToClockString(0.5)).toBe('12:00');
  });

  it('T=0.25 → "06:00"', () => {
    expect(tToClockString(0.25)).toBe('06:00');
  });

  it('T=0.75 → "18:00"', () => {
    expect(tToClockString(0.75)).toBe('18:00');
  });

  it('wraps T=1.0 back to "00:00"', () => {
    expect(tToClockString(1.0)).toBe('00:00');
  });

  it('formats with leading zeros', () => {
    // T ≈ 1/24 ≈ 0.04167 → 01:00
    expect(tToClockString(1 / 24)).toBe('01:00');
  });
});

// ── clockStringToT ─────────────────────────────────────────────────────────────

describe('clockStringToT', () => {
  it('"00:00" → 0', () => {
    expect(clockStringToT('00:00')).toBe(0);
  });

  it('"12:00" → 0.5', () => {
    expect(clockStringToT('12:00')).toBe(0.5);
  });

  it('"06:00" → 0.25', () => {
    expect(clockStringToT('06:00')).toBeCloseTo(0.25, 6);
  });

  it('round-trips through tToClockString', () => {
    for (const t of [0.1, 0.33, 0.66, 0.9]) {
      const s = tToClockString(t);
      const recovered = clockStringToT(s);
      // Clock string has 1-minute resolution, so allow ≈ 1 min tolerance
      expect(Math.abs(recovered - t)).toBeLessThan(1 / (24 * 60) + 1e-9);
    }
  });
});

// ── lerpSolar ─────────────────────────────────────────────────────────────────

describe('lerpSolar', () => {
  it('alpha=0 returns position at t0', () => {
    const a = solarPosition(0.2);
    const result = lerpSolar(0.2, 0.3, 0);
    expect(result.elevation_deg).toBeCloseTo(a.elevation_deg, 6);
  });

  it('alpha=1 returns position at t1', () => {
    const b = solarPosition(0.3);
    const result = lerpSolar(0.2, 0.3, 1);
    expect(result.elevation_deg).toBeCloseTo(b.elevation_deg, 6);
  });

  it('alpha=0.5 returns midpoint elevation', () => {
    const a = solarPosition(0.2);
    const b = solarPosition(0.3);
    const result = lerpSolar(0.2, 0.3, 0.5);
    const mid = (a.elevation_deg + b.elevation_deg) / 2;
    expect(result.elevation_deg).toBeCloseTo(mid, 6);
  });
});

// ── createClock ────────────────────────────────────────────────────────────────

describe('createClock', () => {
  it('initialises with provided t', () => {
    const clock = createClock({ initialT: 0.3 });
    expect(clock.getState().t).toBeCloseTo(0.3, 6);
    clock.destroy();
  });

  it('defaults to not playing', () => {
    const clock = createClock();
    expect(clock.getState().playing).toBe(false);
    clock.destroy();
  });

  it('setT updates the clock position', () => {
    const clock = createClock({ initialT: 0 });
    clock.setT(0.6);
    expect(clock.getState().t).toBeCloseTo(0.6, 6);
    clock.destroy();
  });

  it('setT calls onTick', () => {
    const ticked = [];
    const clock = createClock({ initialT: 0, onTick: (pos) => ticked.push(pos.t) });
    clock.setT(0.5);
    expect(ticked.length).toBe(1);
    expect(ticked[0]).toBeCloseTo(0.5, 6);
    clock.destroy();
  });

  it('setSpeed updates speed', () => {
    const clock = createClock({ speed: 60 });
    clock.setSpeed(120);
    expect(clock.getState().speed).toBe(120);
    clock.destroy();
  });

  it('setSpeed clamps to minimum 1', () => {
    const clock = createClock();
    clock.setSpeed(-5);
    expect(clock.getState().speed).toBeGreaterThanOrEqual(1);
    clock.destroy();
  });

  it('play sets playing to true', () => {
    const clock = createClock();
    clock.play();
    expect(clock.getState().playing).toBe(true);
    clock.pause();
    clock.destroy();
  });

  it('pause sets playing to false', () => {
    const clock = createClock();
    clock.play();
    clock.pause();
    expect(clock.getState().playing).toBe(false);
    clock.destroy();
  });

  it('destroy pauses the clock', () => {
    const clock = createClock();
    clock.play();
    clock.destroy();
    expect(clock.getState().playing).toBe(false);
  });
});
