package scenarios

// CircuitEdit — round-trips a `.circuit.tsx` file's content through the
// files API after a synthetic drag-to-move edit (i.e. the same shape the
// frontend's SchematicView / PCBView produces when the user drops a
// component at a new position).
//
// Why this matters: the interactive editing feature on the frontend
// rewrites `pcb_x` / `pcb_y` (and `schematic_x` / `schematic_y`) JSX
// attributes on the source TSX in place and then PATCHes the file via
// the same `PATCH /files/:id` endpoint that hand edits use. We exercise
// that contract here so we'd notice if the API ever started rejecting
// the kinds of attribute-only diffs the drag handler produces.
//
// We don't need a tscircuit runtime here — the JSX edit is performed in
// Go via the same string-splice strategy the frontend uses (matching the
// `<elname name="R1" ... />` opener and replacing or inserting a numeric
// attribute). Coverage of the regex/edit logic lives in the JS vitest
// suite; this scenario just verifies round-trip + persistence at the
// HTTP layer.

import (
	"context"
	"regexp"
	"strings"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Same shape as src/lib/circuitTSX.js setPositionAttr — find the JSX
// opener whose name="<refdes>" attribute matches, replace OR insert
// `pcb_x={value}` / `pcb_y={value}` style attribute. Used to simulate
// what the frontend drag handler produces; not exported.
func setCircuitNumericAttr(source, refdes, attr string, value string) string {
	if source == "" || refdes == "" {
		return source
	}
	// Match the opener: <Word ... name="refdes" ... />  or  >
	// We anchor on the literal `name="<refdes>"` (also single quotes).
	nameLit := regexp.QuoteMeta(refdes)
	opener := regexp.MustCompile(`<[A-Za-z][A-Za-z0-9_]*\b[^<>]*?name=(?:"` + nameLit + `"|'` + nameLit + `')[^<]*?/?>`)
	loc := opener.FindStringIndex(source)
	if loc == nil {
		return source
	}
	openerStr := source[loc[0]:loc[1]]
	// Replace existing JSX-expression attr or insert before `/>` / `>`.
	exprRe := regexp.MustCompile(`\b` + regexp.QuoteMeta(attr) + `\s*=\s*\{[^}]*\}`)
	if exprRe.MatchString(openerStr) {
		openerStr = exprRe.ReplaceAllString(openerStr, attr+"={"+value+"}")
	} else {
		strRe := regexp.MustCompile(`\b` + regexp.QuoteMeta(attr) + `\s*=\s*(?:"[^"]*"|'[^']*')`)
		if strRe.MatchString(openerStr) {
			openerStr = strRe.ReplaceAllString(openerStr, attr+"={"+value+"}")
		} else {
			// Insert just before trailing `/>` or `>`.
			tail := "/>"
			idx := strings.LastIndex(openerStr, tail)
			if idx < 0 {
				tail = ">"
				idx = strings.LastIndex(openerStr, tail)
			}
			if idx < 0 {
				return source
			}
			head := openerStr[:idx]
			sep := " "
			if strings.HasSuffix(head, " ") || strings.HasSuffix(head, "\n") || strings.HasSuffix(head, "\t") {
				sep = ""
			}
			openerStr = head + sep + attr + "={" + value + "}" + tail
		}
	}
	return source[:loc[0]] + openerStr + source[loc[1]:]
}

// CircuitEdit drives the round-trip scenario.
func CircuitEdit(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "circuit-edit-owner@example.com", "circedit1", "Circuit Edit Owner")
	if !s.Status("register circuit-edit owner", status, 201, raw) {
		return
	}
	if !s.True("circuit-edit owner default_workspace present", owner.DefaultWorkspace != nil) {
		return
	}
	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{
			"name":         "Circuit edit project",
			"workspace_id": owner.DefaultWorkspace.ID,
		}, owner.AccessToken, &proj)
	if !s.Status("create circuit-edit project", status, 201, raw) {
		return
	}
	pid := proj.ID
	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// Scaffold a `.circuit.tsx` file via the existing tool. We then
	// PATCH it with a hand-crafted body that contains a known refdes
	// so we can exercise the attribute splice deterministically.
	co := runTool(s, ctx, pc, "create_circuit", map[string]any{
		"path":      "/electronics/edit-board",
		"width_mm":  25,
		"height_mm": 25,
	})
	circuitID, _ := co["id"].(string)
	circuitPath, _ := co["path"].(string)
	if !s.NotEmpty("create_circuit id", circuitID) {
		return
	}

	// Seed the file with a minimal tscircuit module containing two
	// resistors (R1 already positioned, R2 with no position). The drag
	// handler should be able to (a) update R1's pcb_x and (b) insert a
	// brand new pcb_x on R2.
	const initial = `import { Circuit } from "tscircuit"

export default () => (
  <board width="25mm" height="25mm">
    <resistor name="R1" resistance="1k" pcb_x={1} pcb_y={2} />
    <resistor name="R2" resistance="2.2k" />
  </board>
)
`
	wf := runTool(s, ctx, pc, "write_file", map[string]any{
		"path":    circuitPath,
		"content": initial,
	})
	if _, isErr := wf["code"]; isErr {
		s.Fail("seed initial circuit content",
			"expected success, got code="+asString(wf["code"])+
				" error="+asString(wf["error"]))
		return
	}

	// Perform the synthetic drag edits in Go (same logic the frontend
	// runs after a drag completes).
	edited := initial
	edited = setCircuitNumericAttr(edited, "R1", "pcb_x", "4.5")
	edited = setCircuitNumericAttr(edited, "R1", "pcb_y", "3")
	edited = setCircuitNumericAttr(edited, "R2", "pcb_x", "10")
	edited = setCircuitNumericAttr(edited, "R2", "pcb_y", "0")

	// Sanity check the local edit before sending it to the server.
	s.True("R1 pcb_x replaced", strings.Contains(edited, `pcb_x={4.5}`))
	s.True("R1 pcb_y replaced", strings.Contains(edited, `pcb_y={3}`))
	s.True("R2 pcb_x inserted", strings.Contains(edited, `name="R2"`) && strings.Contains(edited, `pcb_x={10}`))
	s.False("old R1 pcb_x removed", strings.Contains(edited, `pcb_x={1}`))

	// Round-trip via the same PATCH /files/:id endpoint the frontend
	// editor uses for autosave. write_file is the LLM tool flavour;
	// hitting the API directly mirrors the saveFile() path.
	var updated struct {
		ID      string `json:"id"`
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("PATCH", "/api/projects/"+pid+"/files/"+circuitID,
		map[string]any{"content": edited},
		owner.AccessToken, &updated)
	if !s.Status("PATCH updated circuit content", status, 200, raw) {
		return
	}
	s.Equal("PATCH echoes new content", updated.Content, edited)

	// Read back from the DB to verify the edit persisted.
	var stored string
	if err := env.Pool.QueryRow(ctx,
		`select content from files where id = $1`, circuitID).Scan(&stored); s.NoError("read stored content", err) {
		s.Equal("stored content matches sent content", stored, edited)
		s.Contains("stored R1 pcb_x", stored, `pcb_x={4.5}`)
		s.Contains("stored R2 pcb_x", stored, `pcb_x={10}`)
	}

	// And via the API GET path used by the editor on file open.
	var fetched struct {
		Content string `json:"content"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+circuitID,
		nil, owner.AccessToken, &fetched)
	if s.Status("GET updated circuit content", status, 200, raw) {
		s.Equal("GET round-trip matches edit", fetched.Content, edited)
	}

	// Schematic-axis variant — drag in the schematic view writes
	// schematic_x / schematic_y. Sanity-check the same splice path.
	schEdited := setCircuitNumericAttr(edited, "R1", "schematic_x", "0.4")
	schEdited = setCircuitNumericAttr(schEdited, "R1", "schematic_y", "-0.2")
	s.True("schematic_x inserted", strings.Contains(schEdited, "schematic_x={0.4}"))
	s.True("schematic_y inserted (negative)", strings.Contains(schEdited, "schematic_y={-0.2}"))
	status, raw, _ = c.DoJSON("PATCH", "/api/projects/"+pid+"/files/"+circuitID,
		map[string]any{"content": schEdited},
		owner.AccessToken, &updated)
	if s.Status("PATCH schematic-axis edit", status, 200, raw) {
		s.Equal("PATCH echoes schematic edit", updated.Content, schEdited)
	}

	// Refdes-substring guard: editing R1 must not affect R10. (R10
	// doesn't appear in this file but the regex should still scope
	// strictly via the `name="..."` literal — we verify that by adding
	// R10 and checking only R1 changes.)
	const withR10 = `import { Circuit } from "tscircuit"

export default () => (
  <board width="25mm" height="25mm">
    <resistor name="R10" resistance="10k" pcb_x={1} pcb_y={1} />
    <resistor name="R1" resistance="1k" pcb_x={2} pcb_y={2} />
  </board>
)
`
	guarded := setCircuitNumericAttr(withR10, "R1", "pcb_x", "9")
	s.True("R10 pcb_x untouched", strings.Contains(guarded, `name="R10" resistance="10k" pcb_x={1}`))
	s.True("R1 pcb_x replaced (substring guard)", strings.Contains(guarded, `name="R1" resistance="1k" pcb_x={9}`))
}
