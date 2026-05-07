import { useCallback } from 'react'
import Editor from '@monaco-editor/react'
import { AlertTriangle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'

const OPTIONS = {
  minimap: { enabled: false },
  fontFamily: 'JetBrains Mono, Geist Mono, ui-monospace, SF Mono, Menlo, monospace',
  fontSize: 13,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorBlinking: 'smooth',
  renderLineHighlight: 'line',
  tabSize: 2,
  wordWrap: 'off',
  padding: { top: 12, bottom: 12 },
  automaticLayout: true,
}

// Minimal ambient typedef for `@jscad/modeling` so:
//   1. Monaco's JS service stops complaining "Cannot resolve module".
//   2. Users get autocomplete on `primitives.`, `transforms.`, etc.
// Not exhaustive — the runtime is the source of truth. Easy to extend later.
const JSCAD_AMBIENT = `declare module '@jscad/modeling' {
  // Geometry types are opaque to the editor.
  export type Geom3 = unknown
  export type Geom2 = unknown
  export type Path2 = unknown

  type Vec2 = [number, number]
  type Vec3 = [number, number, number]

  export const primitives: {
    cuboid(opts?: { size?: Vec3; center?: Vec3 }): Geom3
    cube(opts?: { size?: number; center?: Vec3 }): Geom3
    sphere(opts?: { radius?: number; segments?: number; center?: Vec3 }): Geom3
    cylinder(opts?: { radius?: number; height?: number; segments?: number; center?: Vec3 }): Geom3
    cylinderElliptic(opts?: { startRadius?: Vec2; endRadius?: Vec2; height?: number; segments?: number }): Geom3
    torus(opts?: { innerRadius?: number; outerRadius?: number; innerSegments?: number; outerSegments?: number }): Geom3
    polyhedron(opts: { points: Vec3[]; faces: number[][] }): Geom3
    rectangle(opts?: { size?: Vec2; center?: Vec2 }): Geom2
    circle(opts?: { radius?: number; segments?: number; center?: Vec2 }): Geom2
    ellipse(opts?: { radius?: Vec2; segments?: number }): Geom2
    polygon(opts: { points: Vec2[] | Vec2[][] }): Geom2
    star(opts?: { vertices?: number; outerRadius?: number; innerRadius?: number }): Geom2
  }

  export const transforms: {
    translate<T>(v: Vec3, geom: T): T
    translateX<T>(d: number, geom: T): T
    translateY<T>(d: number, geom: T): T
    translateZ<T>(d: number, geom: T): T
    rotate<T>(angles: Vec3, geom: T): T
    rotateX<T>(rad: number, geom: T): T
    rotateY<T>(rad: number, geom: T): T
    rotateZ<T>(rad: number, geom: T): T
    scale<T>(factors: Vec3 | number, geom: T): T
    mirror<T>(opts: { normal?: Vec3; origin?: Vec3 }, geom: T): T
    center<T>(opts: { axes?: [boolean, boolean, boolean]; relativeTo?: Vec3 }, geom: T): T
  }

  export const booleans: {
    union<T>(...geoms: T[]): T
    subtract<T>(...geoms: T[]): T
    intersect<T>(...geoms: T[]): T
  }

  export const extrusions: {
    extrudeLinear(opts: { height: number; twistAngle?: number; twistSteps?: number }, geom: Geom2): Geom3
    extrudeRotate(opts: { angle?: number; segments?: number; startAngle?: number }, geom: Geom2): Geom3
    extrudeFromSlices(opts: any, slices: any): Geom3
  }

  export const expansions: {
    expand(opts: { delta: number; corners?: 'edge'|'chamfer'|'round'; segments?: number }, geom: Geom3 | Geom2): Geom3 | Geom2
    offset(opts: { delta: number; corners?: 'edge'|'chamfer'|'round'; segments?: number }, geom: Geom2): Geom2
  }

  export const measurements: {
    measureBoundingBox(geom: Geom3 | Geom2): [Vec3, Vec3]
    measureVolume(geom: Geom3): number
    measureArea(geom: Geom3 | Geom2): number
    measureCenter(geom: Geom3 | Geom2): Vec3
  }

  export const colors: {
    colorize<T>(rgba: [number, number, number] | [number, number, number, number], geom: T): T
    hexToRgb(hex: string): [number, number, number]
    cssColors: Record<string, [number, number, number]>
  }

  export const utils: any
  export const maths: any
  export const curves: any
  export const geometries: any
  export const hulls: { hull<T>(...geoms: T[]): T; hullChain<T>(...geoms: T[]): T }
  export const text: { vectorText(opts: any): any; vectorChar(opts: any): any }
}
`

export default function CodeEditor({ value, onChange, errors, readOnly = false, readOnlyReason = null }) {
  const errs = (errors || []).filter(Boolean)

  // Configure Monaco once when the editor first mounts. The handler runs in the
  // shared monaco namespace, so subsequent editors inherit the settings.
  const handleBeforeMount = useCallback((monaco) => {
    const ts = monaco.languages.typescript
    const js = ts.javascriptDefaults

    // Treat .jscad files as JavaScript and don't drown the user in "module
    // not found" errors — the runner handles imports specially.
    js.setDiagnosticsOptions({
      noSemanticValidation: true,    // turns off "Cannot find module '@jscad/modeling'"
      noSyntaxValidation: false,     // keep real syntax errors
      diagnosticCodesToIgnore: [2304, 2307, 2580, 7026], // module / global / require noise
    })

    js.setCompilerOptions({
      target: ts.ScriptTarget.ES2022,
      allowNonTsExtensions: true,
      moduleResolution: ts.ModuleResolutionKind.NodeJs,
      module: ts.ModuleKind.ESNext,
      noEmit: true,
      esModuleInterop: true,
      jsx: ts.JsxEmit.None,
      allowJs: true,
      typeRoots: ['node_modules/@types'],
    })

    // Resolve `import ... from '@jscad/modeling'` cleanly + power autocomplete.
    js.addExtraLib(JSCAD_AMBIENT, 'file:///node_modules/@jscad/modeling/index.d.ts')
  }, [])

  // Track Monaco focus on the workspace store so the global Cmd+Z handler
  // can yield to Monaco's buffer-undo while the editor has focus and use
  // its own revision-undo otherwise. Workspace store is read via getState
  // here to avoid retriggering the editor on focus state changes.
  const handleMount = useCallback((editor) => {
    const set = (focused) => useWorkspace.getState().setEditorFocused(focused)
    editor.onDidFocusEditorText(() => set(true))
    editor.onDidBlurEditorText(() => set(false))
  }, [])

  return (
    <div className="flex flex-col h-full bg-ink-900">
      {errs.length > 0 && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-950/60 border-b border-red-900/60 text-red-200 text-xs font-mono">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1 whitespace-pre-wrap break-words">
            {errs.join('\n')}
          </div>
        </div>
      )}
      {readOnly && readOnlyReason && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-950/40 border-b border-amber-900/40 text-amber-200 text-[11px]">
          <AlertTriangle size={12} className="flex-shrink-0" />
          <span>{readOnlyReason}</span>
        </div>
      )}
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          theme="vs-dark"
          language="javascript"
          value={value ?? ''}
          onChange={(v) => onChange?.(v ?? '')}
          options={{ ...OPTIONS, readOnly }}
          beforeMount={handleBeforeMount}
          onMount={handleMount}
        />
      </div>
    </div>
  )
}
