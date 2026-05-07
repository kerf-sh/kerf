package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/imranp/kerf/backend/internal/llm"
)

// Server-side bracket-matching mutators for the conventional Kerf JSCAD layout:
//
//   export default function () {
//     return [
//       { id: 'base',  geom: ... },
//       { id: 'peg',   geom: ... },
//     ]
//   }
//
// Mirrors src/lib/jscadObjectOps.js so chat ("duplicate the peg") and the
// ObjectsPanel buttons produce identical edits. Both bail (return ok=false)
// when the file's structure isn't a single top-level `return [{id,geom},...]`.
//
// We do NOT parse the file's AST — the matcher walks the source as a string,
// honouring nested `{}`/`[]`/`()`, single/double/template-literal strings, and
// `// ... ` / `/* ... */` comments. Sufficient for the conventional layout.

// ---------------------------------------------------------------------------
// Tokeniser-aware skipping helpers.

// skipString: if src[i] opens a string literal, advance past the close.
// Returns the new index, or i unchanged if not a string. Honors `\\` escapes
// and `${...}` substitutions inside backticks.
func jsSkipString(src string, i int) int {
	if i >= len(src) {
		return i
	}
	q := src[i]
	if q != '"' && q != '\'' && q != '`' {
		return i
	}
	j := i + 1
	for j < len(src) {
		c := src[j]
		if c == '\\' {
			j += 2
			continue
		}
		if q == '`' && c == '$' && j+1 < len(src) && src[j+1] == '{' {
			depth := 1
			j += 2
			for j < len(src) && depth > 0 {
				cc := src[j]
				if cc == '"' || cc == '\'' || cc == '`' {
					j = jsSkipString(src, j)
					continue
				}
				if cc == '/' && j+1 < len(src) && (src[j+1] == '/' || src[j+1] == '*') {
					j = jsSkipComment(src, j)
					continue
				}
				if cc == '{' {
					depth++
				} else if cc == '}' {
					depth--
				}
				j++
			}
			continue
		}
		if c == q {
			return j + 1
		}
		j++
	}
	return j
}

// skipComment: if src[i] starts a `//` or `/*` comment, advance past its end.
func jsSkipComment(src string, i int) int {
	if i+1 >= len(src) || src[i] != '/' {
		return i
	}
	next := src[i+1]
	if next == '/' {
		j := i + 2
		for j < len(src) && src[j] != '\n' {
			j++
		}
		return j
	}
	if next == '*' {
		j := i + 2
		for j+1 < len(src) {
			if src[j] == '*' && src[j+1] == '/' {
				return j + 2
			}
			j++
		}
		return len(src)
	}
	return i
}

// skipAux: forward-skip past a string OR comment at i; returns i unchanged
// otherwise.
func jsSkipAux(src string, i int) int {
	if i >= len(src) {
		return i
	}
	c := src[i]
	if c == '"' || c == '\'' || c == '`' {
		return jsSkipString(src, i)
	}
	if c == '/' && i+1 < len(src) && (src[i+1] == '/' || src[i+1] == '*') {
		return jsSkipComment(src, i)
	}
	return i
}

// matchBracket: starting at src[start] (which must be `open`), return the
// index of the matching `close`, or -1 if not found.
func jsMatchBracket(src string, start int, open, close byte) int {
	if start >= len(src) || src[start] != open {
		return -1
	}
	depth := 0
	i := start
	for i < len(src) {
		a := jsSkipAux(src, i)
		if a != i {
			i = a
			continue
		}
		c := src[i]
		if c == open {
			depth++
		} else if c == close {
			depth--
			if depth == 0 {
				return i
			}
		}
		i++
	}
	return -1
}

// ---------------------------------------------------------------------------
// Locate the `return [ ... ]` whose body looks like an array of `{id, ...}`
// objects. Returns (arrStart, arrEnd) or (-1, -1) on failure / ambiguity.

func jsLocateReturnArray(source string) (int, int) {
	candidates := [][2]int{}
	i := 0
	for i < len(source) {
		j := jsSkipAux(source, i)
		if j != i {
			i = j
			continue
		}
		if source[i] == 'r' && i+6 <= len(source) && source[i:i+6] == "return" {
			// Word-boundary check.
			before := byte('\n')
			if i > 0 {
				before = source[i-1]
			}
			if !isJSWordByte(before) {
				after := byte(' ')
				if i+6 < len(source) {
					after = source[i+6]
				}
				if isJSWhitespaceByte(after) || after == '/' {
					// Skip whitespace + comments after `return`.
					k := i + 6
					for k < len(source) {
						a := jsSkipAux(source, k)
						if a != k {
							k = a
							continue
						}
						if isJSWhitespaceByte(source[k]) {
							k++
							continue
						}
						break
					}
					if k < len(source) && source[k] == '[' {
						end := jsMatchBracket(source, k, '[', ']')
						if end > 0 {
							slice := source[k : end+1]
							// Sniff for an `id:` field — cheap heuristic to
							// filter out arrays of numbers etc.
							if regexp.MustCompile(`\bid\s*:`).MatchString(slice) {
								candidates = append(candidates, [2]int{k, end})
							}
							i = end + 1
							continue
						}
					}
					i = k
					continue
				}
			}
		}
		i++
	}
	if len(candidates) != 1 {
		return -1, -1
	}
	return candidates[0][0], candidates[0][1]
}

func isJSWordByte(b byte) bool {
	return (b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') ||
		(b >= '0' && b <= '9') || b == '_' || b == '$'
}
func isJSWhitespaceByte(b byte) bool {
	return b == ' ' || b == '\t' || b == '\n' || b == '\r' || b == '\f' || b == '\v'
}

// ---------------------------------------------------------------------------
// Walk the array body and return one descriptor per top-level entry.

type jsObjectEntry struct {
	EntryStart int    // index of `{`
	EntryEnd   int    // index of matching `}`
	SepEnd     int    // index AFTER trailing comma (or EntryEnd+1 if none)
	ID         string // parsed `id: '...'` value, "" if absent
	Valid      bool   // entry is a literal `{` and we extracted an id
}

func jsParseArrayEntries(source string, arrStart, arrEnd int) ([]jsObjectEntry, bool) {
	entries := []jsObjectEntry{}
	i := arrStart + 1
	for i < arrEnd {
		a := jsSkipAux(source, i)
		if a != i {
			i = a
			continue
		}
		c := source[i]
		if isJSWhitespaceByte(c) || c == ',' {
			i++
			continue
		}
		if c != '{' {
			// Non-object element (spread, function call). Bail.
			return nil, false
		}
		entryStart := i
		entryEnd := jsMatchBracket(source, i, '{', '}')
		if entryEnd < 0 {
			return nil, false
		}
		// Find trailing comma.
		s := entryEnd + 1
		for s < arrEnd {
			sa := jsSkipAux(source, s)
			if sa != s {
				s = sa
				continue
			}
			if isJSWhitespaceByte(source[s]) {
				s++
				continue
			}
			break
		}
		sepEnd := entryEnd + 1
		if s < arrEnd && source[s] == ',' {
			sepEnd = s + 1
		}
		id, ok := jsReadEntryID(source, entryStart, entryEnd)
		entries = append(entries, jsObjectEntry{
			EntryStart: entryStart,
			EntryEnd:   entryEnd,
			SepEnd:     sepEnd,
			ID:         id,
			Valid:      ok,
		})
		i = sepEnd
	}
	return entries, true
}

// jsReadEntryID: read the `id: '<name>'` field from inside an entry's `{ ... }`.
// Returns the literal value + ok=true, or "" + ok=false.
func jsReadEntryID(source string, entryStart, entryEnd int) (string, bool) {
	i := entryStart + 1
	for i < entryEnd {
		a := jsSkipAux(source, i)
		if a != i {
			i = a
			continue
		}
		if i+1 < entryEnd && source[i] == 'i' && source[i+1] == 'd' {
			before := byte(' ')
			if i > 0 {
				before = source[i-1]
			}
			after := byte(' ')
			if i+2 < len(source) {
				after = source[i+2]
			}
			if !isJSWordByte(before) && !isJSWordByte(after) {
				k := i + 2
				for k < entryEnd && isJSWhitespaceByte(source[k]) {
					k++
				}
				if k >= entryEnd || source[k] != ':' {
					i++
					continue
				}
				k++
				for k < entryEnd && isJSWhitespaceByte(source[k]) {
					k++
				}
				if k >= entryEnd {
					return "", false
				}
				q := source[k]
				if q != '"' && q != '\'' && q != '`' {
					return "", false
				}
				end := jsSkipString(source, k)
				if end <= k+1 || end > entryEnd+1 {
					return "", false
				}
				// Slice between the quotes (exclude opening + closing q).
				return source[k+1 : end-1], true
			}
		}
		i++
	}
	return "", false
}

// ---------------------------------------------------------------------------
// Public mutators.

// jsFindObjectEntry returns the entries list + a pointer to the matching
// entry, or (nil, -1, false) when the file's structure isn't recognized or
// the id isn't found.
func jsFindObjectEntry(source, objectID string) ([]jsObjectEntry, int, bool) {
	arrStart, arrEnd := jsLocateReturnArray(source)
	if arrStart < 0 {
		return nil, -1, false
	}
	entries, ok := jsParseArrayEntries(source, arrStart, arrEnd)
	if !ok {
		return nil, -1, false
	}
	for _, e := range entries {
		if !e.Valid {
			return nil, -1, false
		}
	}
	for i, e := range entries {
		if e.ID == objectID {
			return entries, i, true
		}
	}
	return entries, -1, true
}

// mintCopyID picks a fresh `<base>-copy[-N]` id given the existing ids.
func jsMintCopyID(base string, taken []string) string {
	t := map[string]bool{}
	for _, s := range taken {
		t[s] = true
	}
	root := base + "-copy"
	if !t[root] {
		return root
	}
	for n := 2; ; n++ {
		cand := fmt.Sprintf("%s-%d", root, n)
		if !t[cand] {
			return cand
		}
	}
}

// jsRenameIDInEntry rewrites the first top-level `id: '<old>'` literal in an
// entry's text. Uses the same quote style as the source. Returns "", false on
// failure (shouldn't happen — caller already validated via jsReadEntryID).
func jsRenameIDInEntry(entryText, oldID, newID string) (string, bool) {
	i := 1 // skip opening `{`
	for i < len(entryText)-1 {
		a := jsSkipAux(entryText, i)
		if a != i {
			i = a
			continue
		}
		if i+1 < len(entryText) && entryText[i] == 'i' && entryText[i+1] == 'd' {
			before := byte(' ')
			if i > 0 {
				before = entryText[i-1]
			}
			after := byte(' ')
			if i+2 < len(entryText) {
				after = entryText[i+2]
			}
			if !isJSWordByte(before) && !isJSWordByte(after) {
				k := i + 2
				for k < len(entryText) && isJSWhitespaceByte(entryText[k]) {
					k++
				}
				if k >= len(entryText) || entryText[k] != ':' {
					i++
					continue
				}
				k++
				for k < len(entryText) && isJSWhitespaceByte(entryText[k]) {
					k++
				}
				if k >= len(entryText) {
					return "", false
				}
				q := entryText[k]
				if q != '"' && q != '\'' && q != '`' {
					return "", false
				}
				end := jsSkipString(entryText, k)
				if end <= k+1 {
					return "", false
				}
				lit := entryText[k+1 : end-1]
				if lit != oldID {
					return "", false
				}
				return entryText[:k] + string(q) + escapeForJSQuote(newID, q) + string(q) + entryText[end:], true
			}
		}
		i++
	}
	return "", false
}

func escapeForJSQuote(s string, q byte) string {
	s = strings.ReplaceAll(s, `\`, `\\`)
	s = strings.ReplaceAll(s, string(q), `\`+string(q))
	return s
}

// jsDuplicateObject inserts a clone of the matching entry just after the
// original, with id renamed. Returns the new source + ok, or ("", false) if
// the file's shape isn't `return [{id,geom},...]`.
func jsDuplicateObject(source, objectID, newID string) (string, bool) {
	if source == "" || objectID == "" {
		return "", false
	}
	entries, idx, _ := jsFindObjectEntry(source, objectID)
	if entries == nil || idx < 0 {
		return "", false
	}
	target := entries[idx]
	taken := []string{}
	for _, e := range entries {
		if e.ID != "" {
			taken = append(taken, e.ID)
		}
	}
	if newID == "" {
		newID = jsMintCopyID(objectID, taken)
	}
	for _, t := range taken {
		if t == newID {
			return "", false
		}
	}
	entryText := source[target.EntryStart : target.EntryEnd+1]
	renamed, ok := jsRenameIDInEntry(entryText, objectID, newID)
	if !ok {
		return "", false
	}
	// Compute leading indent of the original entry (whitespace since the
	// previous newline) to keep the clone aligned.
	lineStart := target.EntryStart
	for lineStart > 0 && source[lineStart-1] != '\n' {
		lineStart--
	}
	indent := source[lineStart:target.EntryStart]

	hasTrailingComma := target.SepEnd > target.EntryEnd+1
	insertion := ""
	if hasTrailingComma {
		insertion = "\n" + indent + renamed + ","
	} else {
		insertion = ",\n" + indent + renamed
	}
	insertAt := target.SepEnd
	return source[:insertAt] + insertion + source[insertAt:], true
}

// jsDeleteObject removes the matching entry along with its trailing comma +
// surrounding whitespace.
func jsDeleteObject(source, objectID string) (string, bool) {
	if source == "" || objectID == "" {
		return "", false
	}
	entries, idx, _ := jsFindObjectEntry(source, objectID)
	if entries == nil || idx < 0 {
		return "", false
	}
	target := entries[idx]
	from := target.EntryStart
	to := target.SepEnd
	// Pull `from` back to the start of the line.
	for from > 0 && (source[from-1] == ' ' || source[from-1] == '\t') {
		from--
	}
	// If the previous char is a newline, also try to consume one of the
	// surrounding newlines so we don't leave a blank line behind.
	if from > 0 && source[from-1] == '\n' {
		look := to
		for look < len(source) && (source[look] == ' ' || source[look] == '\t') {
			look++
		}
		if look < len(source) && source[look] == '\n' {
			to = look + 1
		} else {
			from--
		}
	}
	return source[:from] + source[to:], true
}

// ---------------------------------------------------------------------------
// LLM tools.

var duplicateObjectSpec = llm.ToolSpec{
	Name:        "duplicate_object",
	Description: "Clone a single Object (one entry in a Part's exported `[{id, geom}, ...]` array) and append the clone after the original. Pass `new_id` to set the clone's id; otherwise it defaults to `<object_id>-copy[-N]`. Bails with PARSE_FAILED if the file's structure isn't a clean `return [{id,...}, ...]`.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":      map[string]any{"type": "string"},
			"object_id": map[string]any{"type": "string"},
			"new_id":    map[string]any{"type": "string"},
		},
		"required": []string{"path", "object_id"},
	},
}

type duplicateObjectArgs struct {
	Path     string `json:"path"`
	ObjectID string `json:"object_id"`
	NewID    string `json:"new_id"`
}

func runDuplicateObject(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a duplicateObjectArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.Path == "" || a.ObjectID == "" {
		return errPayload("path and object_id are required", "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	if rp.Kind == "step" || rp.Kind == "folder" || rp.Kind == "assembly" || rp.Kind == "drawing" {
		return errPayload("not a JSCAD file (kind="+rp.Kind+")", "BAD_KIND"), nil
	}
	if rp.Kind == "sketch" {
		return errPayload("sketches are read-only via tools; use the sketch UI", "READONLY_SKETCH"), nil
	}
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	next, ok := jsDuplicateObject(content, a.ObjectID, a.NewID)
	if !ok {
		return errPayload(
			"couldn't auto-duplicate; the file's structure isn't a single `return [{id, geom}, ...]`. Use edit_file to clone the entry by hand.",
			"PARSE_FAILED",
		), nil
	}
	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
		next, rp.ID, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, rp.ID, next, "tool")
	return okPayload(map[string]any{
		"path":      a.Path,
		"object_id": a.ObjectID,
	}), nil
}

var deleteObjectSpec = llm.ToolSpec{
	Name:        "delete_object",
	Description: "Remove a single Object entry from a Part's exported `[{id, geom}, ...]` array. Bails with PARSE_FAILED if the file's structure isn't a clean `return [{id,...}, ...]`.",
	InputSchema: map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":      map[string]any{"type": "string"},
			"object_id": map[string]any{"type": "string"},
		},
		"required": []string{"path", "object_id"},
	},
}

type deleteObjectArgs struct {
	Path     string `json:"path"`
	ObjectID string `json:"object_id"`
}

func runDeleteObject(ctx context.Context, pc ProjectCtx, args json.RawMessage) (string, error) {
	var a deleteObjectArgs
	if err := json.Unmarshal(args, &a); err != nil {
		return errPayload("invalid args: "+err.Error(), "BAD_ARGS"), nil
	}
	if a.Path == "" || a.ObjectID == "" {
		return errPayload("path and object_id are required", "BAD_ARGS"), nil
	}
	rp, err := resolvePath(ctx, pc, a.Path)
	if err != nil || !rp.Exists {
		return errPayload("file not found: "+a.Path, "NOT_FOUND"), nil
	}
	if rp.Kind == "step" || rp.Kind == "folder" || rp.Kind == "assembly" || rp.Kind == "drawing" {
		return errPayload("not a JSCAD file (kind="+rp.Kind+")", "BAD_KIND"), nil
	}
	if rp.Kind == "sketch" {
		return errPayload("sketches are read-only via tools; use the sketch UI", "READONLY_SKETCH"), nil
	}
	var content string
	if err := pc.Pool.QueryRow(ctx,
		`select content from files where id = $1 and project_id = $2`,
		rp.ID, pc.ProjectID).Scan(&content); err != nil {
		return "", err
	}
	next, ok := jsDeleteObject(content, a.ObjectID)
	if !ok {
		return errPayload(
			"couldn't auto-delete; the file's structure isn't a single `return [{id, geom}, ...]`. Use edit_file to remove the entry by hand.",
			"PARSE_FAILED",
		), nil
	}
	if _, err := pc.Pool.Exec(ctx,
		`update files set content = $1, updated_at = now() where id = $2 and project_id = $3`,
		next, rp.ID, pc.ProjectID); err != nil {
		return "", err
	}
	_ = recordRevisionForFile(ctx, pc, rp.ID, next, "tool")
	return okPayload(map[string]any{
		"path":      a.Path,
		"object_id": a.ObjectID,
	}), nil
}
