// pcbThemes.js — PCB colour themes.
//
// Each theme maps layer-type → default color.  The LayersPanel / PCBView
// can use these to apply a consistent palette across all layers.
//
// Usage:
//   import { THEMES, applyThemeToPCBView } from '../styles/pcbThemes.js'

export const THEMES = Object.freeze({

  // KiCad default — matches KiCad 6/7 default colour scheme.
  kicad: Object.freeze({
    copper:     '#ef4444',   // F.Cu red (top); B.Cu overridden per-layer below
    silkscreen: '#f8fafc',
    soldermask: '#22c55e',
    paste:      '#94a3b8',
    drill:      '#fbbf24',
    mechanical: '#64748b',
    // Per-layer overrides
    layers: Object.freeze({
      top_copper:      '#ef4444',
      bottom_copper:   '#3b82f6',
      top_silk:        '#f8fafc',
      bottom_silk:     '#cbd5e1',
      top_mask:        '#22c55e',
      bottom_mask:     '#16a34a',
      top_paste:       '#94a3b8',
      bottom_paste:    '#64748b',
      drill_plated:    '#fbbf24',
      drill_nonplated: '#f97316',
      edge_cuts:       '#f59e0b',
      courtyard:       '#818cf8',
      fab_notes:       '#6b7280',
    }),
  }),

  // Dark — muted, high readability on dark backgrounds.
  dark: Object.freeze({
    copper:     '#f87171',
    silkscreen: '#e2e8f0',
    soldermask: '#4ade80',
    paste:      '#94a3b8',
    drill:      '#fcd34d',
    mechanical: '#9ca3af',
    layers: Object.freeze({
      top_copper:      '#f87171',
      bottom_copper:   '#60a5fa',
      top_silk:        '#e2e8f0',
      bottom_silk:     '#94a3b8',
      top_mask:        '#4ade80',
      bottom_mask:     '#86efac',
      top_paste:       '#94a3b8',
      bottom_paste:    '#475569',
      drill_plated:    '#fcd34d',
      drill_nonplated: '#fb923c',
      edge_cuts:       '#fde68a',
      courtyard:       '#a5b4fc',
      fab_notes:       '#9ca3af',
    }),
  }),

  // Oscilloscope — high-contrast phosphor green on black.
  oscilloscope: Object.freeze({
    copper:     '#00ff41',
    silkscreen: '#ffffff',
    soldermask: '#00cc33',
    paste:      '#aaaaaa',
    drill:      '#ffff00',
    mechanical: '#00aaff',
    layers: Object.freeze({
      top_copper:      '#00ff41',
      bottom_copper:   '#00aaff',
      top_silk:        '#ffffff',
      bottom_silk:     '#cccccc',
      top_mask:        '#00cc33',
      bottom_mask:     '#009922',
      top_paste:       '#aaaaaa',
      bottom_paste:    '#888888',
      drill_plated:    '#ffff00',
      drill_nonplated: '#ff8800',
      edge_cuts:       '#ffaa00',
      courtyard:       '#ff00ff',
      fab_notes:       '#00aaff',
    }),
  }),

})

/**
 * getLayerColor — resolve the color for a named layer in a theme.
 *
 * @param {string} themeName  one of 'kicad' | 'dark' | 'oscilloscope'
 * @param {string} layerName  e.g. 'top_copper'
 * @param {string} layerType  e.g. 'copper' (fallback if layerName not in theme)
 * @returns {string}  hex color
 */
export function getLayerColor(themeName, layerName, layerType) {
  const theme = THEMES[themeName] ?? THEMES.kicad
  return theme.layers?.[layerName] ?? theme[layerType] ?? '#64748b'
}

/**
 * applyThemeToStack — return a new layer stack array with colors from the theme.
 *
 * @param {Array}  layerStack  Array<{ name, type, color, ... }>
 * @param {string} themeName
 * @returns {Array}
 */
export function applyThemeToStack(layerStack, themeName) {
  return layerStack.map((l) => ({
    ...l,
    color: getLayerColor(themeName, l.name, l.type),
  }))
}
