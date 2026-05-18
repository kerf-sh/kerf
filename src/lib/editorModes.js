// editorModes.js — extension → Monaco language-ID mapping for the
// plain-highlight text/code editor (T-116).
//
// Rules:
//   - Keys are lowercase dot-prefixed extensions (e.g. '.py').
//   - Values are Monaco language IDs (the string accepted by the `language`
//     prop of @monaco-editor/react's <Editor>).
//   - 'plaintext' is the Monaco fallback that still gives an editable
//     textarea with no colouring. Anything in this table gets syntax
//     highlighting.
//
// No WASM, no LSP — Monaco bundles its own tokenizers for all of these.

/** @type {Record<string, string>} */
export const EXTENSION_TO_MODE = {
  // Markup / documentation
  '.md': 'markdown',
  '.markdown': 'markdown',
  '.txt': 'plaintext',
  '.rst': 'plaintext',

  // Web / scripting
  '.js': 'javascript',
  '.mjs': 'javascript',
  '.cjs': 'javascript',
  '.ts': 'typescript',
  '.mts': 'typescript',
  '.jsx': 'javascript',
  '.tsx': 'typescript',
  '.html': 'html',
  '.htm': 'html',
  '.css': 'css',
  '.scss': 'scss',
  '.less': 'less',

  // Python
  '.py': 'python',
  '.pyw': 'python',

  // C / C++ / embedded
  '.c': 'cpp',
  '.h': 'cpp',
  '.cpp': 'cpp',
  '.cxx': 'cpp',
  '.cc': 'cpp',
  '.hpp': 'cpp',
  '.hh': 'cpp',
  '.hxx': 'cpp',
  '.ino': 'cpp',   // Arduino sketch — C++ superset
  '.uno': 'cpp',   // ESP32/Uno variant

  // Linker scripts & hardware description
  '.ld': 'plaintext',   // GNU linker script (no dedicated Monaco grammar)
  '.v': 'plaintext',    // Verilog — Monaco ships verilog support in newer versions;
                        // falls back to plaintext if not available at runtime
  '.vhd': 'plaintext',  // VHDL
  '.vhdl': 'plaintext',

  // Data / config
  '.json': 'json',
  '.jsonc': 'json',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.toml': 'plaintext', // Monaco has no built-in TOML tokenizer
  '.ini': 'ini',
  '.cfg': 'ini',
  '.conf': 'ini',
  '.env': 'plaintext',

  // Shell
  '.sh': 'shell',
  '.bash': 'shell',
  '.zsh': 'shell',
  '.fish': 'shell',
  '.bat': 'bat',
  '.cmd': 'bat',
  '.ps1': 'powershell',

  // Build / make
  '.makefile': 'makefile',
  '.mk': 'makefile',

  // Ruby / Lua
  '.rb': 'ruby',
  '.lua': 'lua',

  // SQL
  '.sql': 'sql',

  // XML / SVG
  '.xml': 'xml',
  '.svg': 'xml',
  '.xsd': 'xml',

  // Rust / Go / Java / Kotlin / Swift / Dart
  '.rs': 'rust',
  '.go': 'go',
  '.java': 'java',
  '.kt': 'kotlin',
  '.kts': 'kotlin',
  '.swift': 'swift',
  '.dart': 'dart',

  // Other common text
  '.csv': 'plaintext',
  '.log': 'plaintext',
  '.diff': 'diff',
  '.patch': 'diff',
  '.dockerfile': 'dockerfile',
  '.graphql': 'graphql',
  '.gql': 'graphql',
  '.proto': 'protobuf',
}

// Extensions that are explicitly handled by their own dedicated editor component
// (not the plain-text fallback). Used to exclude them from TEXT_CODE_EXTENSIONS.
const DEDICATED_EXTENSIONS = new Set([
  '.jscad',
  '.assembly',
  '.drawing',
  '.sketch',
  '.feature',
  '.circuit.tsx', // matched differently (includes check) in Editor.jsx
  '.part',
  '.material',
  '.equations',
  '.script.ts',
  '.script.py',
  '.tolerance',
  '.topo',
  '.subd',
  '.mesh',
  '.graph',
  '.render',
  '.family.json',  // matched via includes
  '.schedule.json',
  '.view.json',
  '.sheet.json',
  '.duct.json',
  '.pipe.json',
  '.conduit.json',
  '.stair.json',
  '.railing.json',
  '.fem',
  '.section',
  '.plc.st',
  '.quadmesh',
  '.print',
  '.step',
  '.stp',
])

/**
 * Return the Monaco language ID for the given filename, or null if the file
 * has a dedicated editor component (not the plain-text path).
 *
 * @param {string} filename
 * @returns {string | null}  Monaco language ID, or null if not a text/code file
 */
export function getEditorMode(filename) {
  if (!filename) return null
  const lower = filename.toLowerCase()

  // Check dedicated extensions first — these must NOT resolve to the plain editor.
  for (const ext of DEDICATED_EXTENSIONS) {
    if (lower.endsWith(ext)) return null
  }

  // Walk candidate extensions from longest to shortest so multi-part names
  // like "Makefile" (no extension) are also caught via the name itself.
  // Start from the first dot.
  const dotIdx = lower.indexOf('.')
  if (dotIdx !== -1) {
    // Try progressively shorter tails: '.script.py', '.py', etc.
    let start = dotIdx
    while (start !== -1) {
      const candidate = lower.slice(start)
      if (EXTENSION_TO_MODE[candidate] !== undefined) {
        return EXTENSION_TO_MODE[candidate]
      }
      start = lower.indexOf('.', start + 1)
    }
  }

  // Basename checks for extension-less text files (Makefile, Dockerfile, etc.)
  const base = lower.split('/').pop()
  if (base === 'makefile') return 'makefile'
  if (base === 'dockerfile') return 'dockerfile'
  if (base === 'gemfile' || base === 'rakefile') return 'ruby'
  if (base === 'cmakelists.txt') return 'cmake'

  return null
}

/**
 * Return true iff the file should open in the plain-text/code editor (T-116).
 *
 * @param {{ name?: string, kind?: string } | null | undefined} file
 * @returns {boolean}
 */
export function isTextCodeFile(file) {
  if (!file) return false
  if (file.kind === 'text' || file.kind === 'code') return true
  return getEditorMode(file.name || '') !== null
}
