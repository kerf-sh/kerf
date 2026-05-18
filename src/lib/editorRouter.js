// editorRouter.js — maps a filename / extension to the editor component
// that should render it, and holds canonical new-file templates.

// Map extension → component-name string.
// Callers import routeByExtension and switch on the returned string to
// lazy-load the correct editor.
export function routeByExtension(filename) {
  if (!filename || typeof filename !== 'string') return 'MonacoEditor'
  const base = filename.split('/').pop()
  const dot = base.lastIndexOf('.')
  if (dot === -1) return 'MonacoEditor'
  const ext = base.slice(dot).toLowerCase()
  switch (ext) {
    case '.ato':  return 'AtopileEditor'
    case '.tsx':  return 'TscircuitEditor'
    case '.py':
    case '.md':
    case '.json':
    case '.txt':
      return 'MonacoEditor'
    default:
      return 'MonacoEditor'
  }
}

// Initial content inserted into a newly-created .ato file.
// Follows the atopile v0.3 module syntax: `module <Name>: ... end <Name>;`
export const ATO_TEMPLATE = `module Foo:
  # Module-level signals
  signal gnd
  signal vcc

  # Add components below, e.g.:
  # resistor R1:
  #   value = 10kohm
  #   package = "0402"
  # end R1
end Foo;
`
