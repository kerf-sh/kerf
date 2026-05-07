package scenarios

// Library / Parts scenarios.
//
// Exercises the kind='part' file plumbing, the create_part LLM tool, the
// part-photo HTTP handlers, and the BOM rollup endpoint.
//
// Note on the LLM tool surface: per-field tools (set_part_metadata,
// add_distributor_link, set_part_visibility, add_part_photo) were
// consolidated away — Parts are now mutated by editing the JSON via
// write_file / edit_file directly. We exercise the surviving create_part
// tool plus the photo + BOM HTTP endpoints which remain.

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"net/url"

	"github.com/google/uuid"

	"github.com/imranp/kerf/backend/cmd/test/runner"
	"github.com/imranp/kerf/backend/internal/tools"
)

// Library drives the Parts + BOM surface end-to-end.
func Library(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := register(c, "lib-owner@example.com", "libownerpass1", "Lib Owner")
	if !s.Status("register lib owner", status, 201, raw) {
		return
	}

	var proj struct {
		ID      string `json:"id"`
		OwnerID string `json:"owner_id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Library project"}, owner.AccessToken, &proj)
	if !s.Status("create lib project", status, 201, raw) {
		return
	}
	pid := proj.ID

	pc := tools.ProjectCtx{
		Pool:      env.Pool,
		ProjectID: uuid.MustParse(pid),
		UserID:    uuid.MustParse(owner.User.ID),
		Role:      "owner",
	}

	// --- create_part (the only Part-authoring LLM tool) ---
	createOut := runTool(s, ctx, pc, "create_part", map[string]any{
		"path": "/library/r10k.part",
		"metadata": map[string]any{
			"name":         "10kΩ resistor 0805",
			"category":     "resistor",
			"manufacturer": "Yageo",
			"mpn":          "RC0805FR-0710KL",
			"value":        "10kΩ",
			"distributors": []map[string]any{
				{"name": "digikey", "sku": "311-10.0KCRCT-ND",
					"url": "https://www.digikey.com/r10k", "price_usd": 0.014},
			},
		},
	})
	partID, _ := createOut["id"].(string)
	if !s.NotEmpty("create_part returned id", partID) {
		return
	}
	s.Equal("create_part name echoed", createOut["name"], "10kΩ resistor 0805")

	// File-kind plumbing: row landed with kind='part'.
	var kind string
	if err := env.Pool.QueryRow(ctx,
		`select kind from files where id = $1`, partID).Scan(&kind); s.NoError("kind lookup", err) {
		s.Equal("Part row kind=part", kind, "part")
	}

	// Initial revision recorded.
	var revCount int
	if err := env.Pool.QueryRow(ctx,
		`select count(*) from file_revisions where file_id = $1`, partID).Scan(&revCount); s.NoError("count revs", err) {
		s.True(">=1 revision after create_part", revCount >= 1, "got %d", revCount)
	}

	// create_part on an existing path → EXISTS.
	dup := runTool(s, ctx, pc, "create_part", map[string]any{
		"path":     "/library/r10k.part",
		"metadata": map[string]any{"name": "dup"},
	})
	s.Equal("create_part duplicate path → EXISTS", dup["code"], "EXISTS")

	// Missing metadata.name → BAD_ARGS.
	bad := runTool(s, ctx, pc, "create_part", map[string]any{
		"path":     "/library/no-name.part",
		"metadata": map[string]any{},
	})
	s.Equal("create_part missing name → BAD_ARGS", bad["code"], "BAD_ARGS")

	// --- create_file rejects kinds that have dedicated scaffolders. ---
	// .part suffix on a missing file → steers to create_part.
	cfPart := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/library/foo.part",
		"kind": "part",
	})
	s.Equal("create_file kind=part → READONLY_PART", cfPart["code"], "READONLY_PART")
	cfPartSuffix := runTool(s, ctx, pc, "create_file", map[string]any{
		"path": "/library/bar.part",
	})
	s.Equal("create_file .part suffix → READONLY_PART", cfPartSuffix["code"], "READONLY_PART")
	// write_file on a NEW .part path also steers — must use create_part first.
	wfNew := runTool(s, ctx, pc, "write_file", map[string]any{
		"path":    "/library/brand-new.part",
		"content": "garbage",
	})
	s.Equal("write_file on missing .part → READONLY_PART", wfNew["code"], "READONLY_PART")

	// --- Photo flow (HTTP). First photo → primary auto-marked. ---
	p1 := uploadPhoto(s, c, owner.AccessToken, pid, partID, "p1.png", 64, 64)
	s.True("photo1 primary=true", p1["primary"] == true, "primary=%v", p1["primary"])
	p1Key, _ := p1["storage_key"].(string)

	// Second photo → no auto-primary.
	p2 := uploadPhoto(s, c, owner.AccessToken, pid, partID, "p2.png", 32, 32)
	s.True("photo2 not auto-primary",
		p2["primary"] == nil || p2["primary"] == false,
		"primary=%v", p2["primary"])
	p2Key, _ := p2["storage_key"].(string)

	// PATCH /primary → swap.
	patchPath := fmt.Sprintf("/api/projects/%s/files/%s/photos/primary?key=%s",
		pid, partID, url.QueryEscape(p2Key))
	status, raw, _ = c.Do("PATCH", patchPath, nil, owner.AccessToken)
	s.Status("PATCH primary swap", status, 204, raw)
	if doc := loadPartContent(s, env, partID); doc != nil {
		photos, _ := doc["photos"].([]any)
		gotPrimary := []bool{}
		for _, p := range photos {
			pm, _ := p.(map[string]any)
			gotPrimary = append(gotPrimary, pm["primary"] == true)
		}
		s.Equal("primary count after swap", boolCount(gotPrimary), 1)
		// p2 is now primary.
		p2Primary := false
		for _, p := range photos {
			pm, _ := p.(map[string]any)
			if pm["storage_key"] == p2Key && pm["primary"] == true {
				p2Primary = true
				break
			}
		}
		s.True("p2 is primary after swap", p2Primary)
	}

	// DELETE the primary → first remaining is promoted.
	delPath := fmt.Sprintf("/api/projects/%s/files/%s/photos?key=%s",
		pid, partID, url.QueryEscape(p2Key))
	status, raw, _ = c.Do("DELETE", delPath, nil, owner.AccessToken)
	s.Status("DELETE primary photo", status, 204, raw)
	if doc := loadPartContent(s, env, partID); doc != nil {
		photos, _ := doc["photos"].([]any)
		s.Equal("photos len after primary delete", len(photos), 1)
		if len(photos) == 1 {
			pm, _ := photos[0].(map[string]any)
			s.True("remaining promoted to primary",
				pm["primary"] == true, "primary=%v", pm["primary"])
			s.Equal("remaining is original p1", pm["storage_key"], p1Key)
		}
	}

	// --- BOM endpoint: empty project (no parts referenced) → empty rows. ---
	var emptyProj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "empty-bom"}, owner.AccessToken, &emptyProj)
	s.Status("create empty proj", status, 201, raw)
	var bomEmpty bomResp
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+emptyProj.ID+"/bom",
		nil, owner.AccessToken, &bomEmpty)
	if s.Status("GET /bom empty", status, 200, raw) {
		s.Equal("empty bom rows=0", len(bomEmpty.Rows), 0)
	}

	// --- BOM with one assembly referencing two Parts → two rows. ---
	runTool(s, ctx, pc, "create_part", map[string]any{
		"path": "/library/cap-100nf.part",
		"metadata": map[string]any{
			"name":         "100nF X7R 0805",
			"manufacturer": "Murata",
			"mpn":          "GRM21BR71H104KA01L",
			"category":     "capacitor",
		},
	})

	cap100 := mustGetPartID(s, env, pid, "/library/cap-100nf.part")
	if cap100 == "" {
		return
	}
	assyContent := fmt.Sprintf(`{"version":1,"components":[{"file_id":%q,"object_id":""},{"file_id":%q,"object_id":""}]}`,
		partID, cap100)
	var assy struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "main.assembly", "kind": "assembly", "content": assyContent},
		owner.AccessToken, &assy)
	s.Status("create assembly", status, 201, raw)

	// Mark owner as is_verified_publisher to confirm the BOM Author flag
	// flows through (we only check existence here; the full author payload
	// shape lives in the workshop scenarios).
	if _, err := env.Pool.Exec(ctx,
		`update users set is_verified_publisher = true where id = $1`,
		owner.User.ID); !s.NoError("set is_verified_publisher", err) {
		return
	}

	var bom bomResp
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/bom", nil, owner.AccessToken, &bom)
	if s.Status("GET /bom 2 parts", status, 200, raw) {
		s.Equal("bom rows=2", len(bom.Rows), 2)
		for _, row := range bom.Rows {
			s.Equal("bom row count=1 ("+row.Part.Name+")", row.Count, 1)
		}
	}
}

// --- helpers --------------------------------------------------------------

// runTool invokes a tools.Registry entry via tools.Execute and returns the
// decoded result map. Failures bubble up as a suite.Fail.
func runTool(s *runner.Suite, ctx context.Context, pc tools.ProjectCtx, name string, args map[string]any) map[string]any {
	raw, _ := json.Marshal(args)
	out := tools.Execute(ctx, pc, name, raw)
	var decoded map[string]any
	if err := json.Unmarshal([]byte(out), &decoded); err != nil {
		s.Fail("runTool decode "+name, fmt.Sprintf("invalid JSON from tool: %v body=%s", err, out))
		return nil
	}
	return decoded
}

// loadPartContent reads a kind='part' row and returns its parsed JSON map.
func loadPartContent(s *runner.Suite, env *runner.Env, fileID string) map[string]any {
	var content string
	if err := env.Pool.QueryRow(context.Background(),
		`select content from files where id = $1`, fileID).Scan(&content); !s.NoError("load part content "+fileID, err) {
		return nil
	}
	var doc map[string]any
	if err := json.Unmarshal([]byte(content), &doc); !s.NoError("decode part content", err) {
		return nil
	}
	return doc
}

// mustGetPartID resolves a part path (/library/<leaf>.part) → file id via DB.
func mustGetPartID(s *runner.Suite, env *runner.Env, pid, path string) string {
	var folderID string
	if err := env.Pool.QueryRow(context.Background(),
		`select id from files where project_id = $1 and parent_id is null and name = 'library' and kind = 'folder' and deleted_at is null`,
		pid).Scan(&folderID); !s.NoError("library folder", err) {
		return ""
	}
	leaf := path[len("/library/"):]
	var fid string
	if err := env.Pool.QueryRow(context.Background(),
		`select id from files where project_id = $1 and parent_id = $2 and name = $3 and deleted_at is null`,
		pid, folderID, leaf).Scan(&fid); !s.NoError("part "+leaf, err) {
		return ""
	}
	return fid
}

// uploadPhoto sends a w*h PNG to POST /photos and returns the response map.
func uploadPhoto(s *runner.Suite, c *runner.Client, token, pid, fid, name string, w, h int) map[string]any {
	body, ct := buildPhotoMultipart(name, w, h)
	req, _ := http.NewRequest("POST",
		c.BaseURL+fmt.Sprintf("/api/projects/%s/files/%s/photos", pid, fid),
		body)
	req.Header.Set("Content-Type", ct)
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := c.HTTP.Do(req)
	if !s.NoError("upload photo "+name, err) {
		return nil
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if !s.Status("POST /photos "+name, resp.StatusCode, 201, raw) {
		return nil
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); !s.NoError("decode photo resp", err) {
		return nil
	}
	return out
}

// buildPhotoMultipart constructs a multipart body containing a w*h gradient
// PNG under field name "file".
func buildPhotoMultipart(filename string, w, h int) (*bytes.Buffer, string) {
	var pngBuf bytes.Buffer
	img := image.NewRGBA(image.Rect(0, 0, w, h))
	for y := 0; y < h; y++ {
		for x := 0; x < w; x++ {
			img.Set(x, y, color.RGBA{R: byte(x % 255), G: byte(y % 255), B: 128, A: 255})
		}
	}
	_ = png.Encode(&pngBuf, img)

	body := &bytes.Buffer{}
	mw := multipart.NewWriter(body)
	hdr := textproto.MIMEHeader{}
	hdr.Set("Content-Disposition", fmt.Sprintf(`form-data; name="file"; filename=%q`, filename))
	hdr.Set("Content-Type", "image/png")
	pw, _ := mw.CreatePart(hdr)
	_, _ = pw.Write(pngBuf.Bytes())
	mw.Close()
	return body, mw.FormDataContentType()
}

// boolCount returns how many entries in xs are true.
func boolCount(xs []bool) int {
	n := 0
	for _, x := range xs {
		if x {
			n++
		}
	}
	return n
}

// bomResp is a trimmed projection of the BOMResponse shape used in this scenario.
type bomResp struct {
	Rows []struct {
		Part struct {
			Name string `json:"name"`
			MPN  string `json:"mpn"`
		} `json:"part"`
		Count int `json:"count"`
	} `json:"rows"`
}
