// DayNightSlider.test.jsx — vitest smoke tests for the day/night cycle panel.
//
// No @testing-library/react. We render to static markup via react-dom/server
// (already a project dep) and assert structural / ARIA properties. The clock
// loop (requestAnimationFrame) is not exercised here — that's covered in
// dayNightCycle.test.js.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DayNightSlider from './DayNightSlider.jsx'

// ── Render helper ──────────────────────────────────────────────────────────────

function render(props = {}) {
  return renderToStaticMarkup(<DayNightSlider {...props} />)
}

// ── Root structure ─────────────────────────────────────────────────────────────

describe('DayNightSlider — root structure', () => {
  it('renders a root container with data-testid="day-night-slider"', () => {
    const html = render()
    expect(html).toMatch(/data-testid="day-night-slider"/)
  })

  it('renders the time slider input', () => {
    const html = render()
    expect(html).toMatch(/data-testid="time-slider"/)
    expect(html).toMatch(/type="range"/)
  })

  it('renders the play/pause button', () => {
    const html = render()
    expect(html).toMatch(/data-testid="play-pause-btn"/)
  })

  it('renders the clock display', () => {
    const html = render()
    expect(html).toMatch(/data-testid="clock-display"/)
  })

  it('renders the stats readout', () => {
    const html = render()
    expect(html).toMatch(/data-testid="stats-readout"/)
  })
})

// ── Noon defaults ──────────────────────────────────────────────────────────────

describe('DayNightSlider — noon defaults (T=0.25)', () => {
  it('defaults to initialT=0.25 and shows 06:00', () => {
    const html = render({ initialT: 0.25 })
    expect(html).toContain('06:00')
  })

  it('shows "90.0°" elevation at noon', () => {
    const html = render({ initialT: 0.25 })
    expect(html).toMatch(/90\.0°/)
  })

  it('shows a color temperature near 6500 K at noon', () => {
    const html = render({ initialT: 0.25 })
    // Should contain something between 5500 and 6500 K
    expect(html).toMatch(/\b(5[5-9]\d{2}|6[0-5]\d{2})\s*K\b/)
  })

  it('shows the sun icon (not moon) when T=0.25', () => {
    // At noon the sun is above the horizon; SunIcon renders a circle
    const html = render({ initialT: 0.25 })
    expect(html).toMatch(/<circle/)
  })
})

// ── Midnight ───────────────────────────────────────────────────────────────────

describe('DayNightSlider — midnight (T=0.75)', () => {
  it('shows 18:00 at T=0.75', () => {
    const html = render({ initialT: 0.75 })
    expect(html).toContain('18:00')
  })

  it('shows "−45.0°" elevation (or close) at midnight', () => {
    const html = render({ initialT: 0.75 })
    expect(html).toMatch(/-45\.0°/)
  })

  it('shows color temp near 1500 K at midnight', () => {
    const html = render({ initialT: 0.75 })
    // Should contain 1500 K
    expect(html).toMatch(/1500\s*K/)
  })

  it('shows the moon icon (path element) when T=0.75', () => {
    const html = render({ initialT: 0.75 })
    expect(html).toMatch(/<path/)
  })
})

// ── Play/Pause aria ────────────────────────────────────────────────────────────

describe('DayNightSlider — play/pause button', () => {
  it('aria-label is "Play" in the default (paused) state', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Play"/)
  })

  it('time slider has aria-label="Time of day"', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Time of day"/)
  })
})

// ── Speed picker ───────────────────────────────────────────────────────────────

describe('DayNightSlider — speed picker', () => {
  it('renders all 5 speed option buttons', () => {
    const html = render()
    const matches = html.match(/data-testid="speed-btn-\d+"/g) || []
    expect(matches.length).toBe(5)
  })

  it('renders the "1×" option', () => {
    const html = render()
    expect(html).toContain('1×')
  })

  it('renders the "4×" option', () => {
    const html = render()
    expect(html).toContain('4×')
  })
})

// ── Slider range ───────────────────────────────────────────────────────────────

describe('DayNightSlider — slider attributes', () => {
  it('slider min=0, max=1, step=0.001', () => {
    const html = render()
    expect(html).toMatch(/min="0"/)
    expect(html).toMatch(/max="1"/)
    expect(html).toMatch(/step="0\.001"/)
  })

  it('slider value reflects initialT', () => {
    const html = render({ initialT: 0.5 })
    expect(html).toMatch(/value="0\.5"/)
  })
})

// ── Stats labels ───────────────────────────────────────────────────────────────

describe('DayNightSlider — stats readout labels', () => {
  it('contains "Elevation" label', () => {
    const html = render()
    expect(html).toContain('Elevation')
  })

  it('contains "Azimuth" label', () => {
    const html = render()
    expect(html).toContain('Azimuth')
  })

  it('contains "Color temp" label', () => {
    const html = render()
    expect(html).toContain('Color temp')
  })

  it('contains "Turbidity" label', () => {
    const html = render()
    expect(html).toContain('Turbidity')
  })
})

// ── Custom className ───────────────────────────────────────────────────────────

describe('DayNightSlider — className prop', () => {
  it('merges a custom className onto the root element', () => {
    const html = render({ className: 'my-custom-panel' })
    expect(html).toMatch(/my-custom-panel/)
  })
})
