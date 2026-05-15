/**
 * SEO metadata for the Electronics domain page.
 *
 * title      ≤60 chars
 * description ≤155 chars
 * JSON-LD     WebPage + ItemList
 * OG image    hosted at kerf.sh/og/electronics.png
 */

export const meta = {
  title: 'PCB design with chat-driven schematics — Kerf',
  description:
    'Design PCBs end-to-end: ERC, hierarchical schematics, diff pairs, autoroute, copper pour, SPICE sim, Gerber/IPC-2581 fab packs — all from a chat interface.',
  og: {
    title: 'PCB design with chat-driven schematics — Kerf',
    description:
      'ERC · buses · diff pairs · autoroute · pour · SPICE sim · Gerbers — full KiCad-comprehensive electronics in one chat-native workspace.',
    image: 'https://kerf.sh/og/electronics.png',
    url: 'https://kerf.sh/domains/electronics',
    type: 'website',
  },
}

export const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'WebPage',
  name: meta.title,
  description: meta.description,
  url: meta.og.url,
  mainEntity: {
    '@type': 'ItemList',
    name: 'Kerf Electronics Capabilities',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'ERC — electrical rules check with extended depth' },
      { '@type': 'ListItem', position: 2, name: 'Buses and net classes' },
      { '@type': 'ListItem', position: 3, name: 'Length tuning and via stitching' },
      { '@type': 'ListItem', position: 4, name: 'Shove router' },
      { '@type': 'ListItem', position: 5, name: 'Hierarchical schematic' },
      { '@type': 'ListItem', position: 6, name: 'RF analysis via scikit-rf' },
      { '@type': 'ListItem', position: 7, name: 'Autoroute via FreeRouting' },
      { '@type': 'ListItem', position: 8, name: 'Copper pour' },
      { '@type': 'ListItem', position: 9, name: 'DRC with IPC-2221B presets' },
      { '@type': 'ListItem', position: 10, name: 'SPICE simulation via ngspice + model library' },
      { '@type': 'ListItem', position: 11, name: 'Differential pairs + impedance' },
      { '@type': 'ListItem', position: 12, name: 'Panelize' },
      { '@type': 'ListItem', position: 13, name: 'Testpoint + bed-of-nails fixture' },
      { '@type': 'ListItem', position: 14, name: 'Variants — DNP + per-refdes overrides' },
      { '@type': 'ListItem', position: 15, name: 'Gerber / Excellon / P&P / IPC-2581 fab pack' },
      { '@type': 'ListItem', position: 16, name: 'KiCad / OrCAD PADS / CSV netlist export' },
      { '@type': 'ListItem', position: 17, name: 'IPC-D-356A netlist' },
      { '@type': 'ListItem', position: 18, name: '3D STEP export' },
      { '@type': 'ListItem', position: 19, name: 'IDF 3.0 MCAD exchange' },
      { '@type': 'ListItem', position: 20, name: 'Symbol and footprint library management' },
    ],
  },
}
