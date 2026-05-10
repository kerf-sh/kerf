package scenarios

// Cross-project derived-artifact cache (ROADMAP row 67 Phase 2).
//
// Proves the v1 cache layer:
//   - Lookup miss → 501 (compile-on-demand-not-yet-wired surface).
//   - Pre-seeded row → 200 with cached:true + payload_b64.
//   - Editing the source content invalidates the cache (sha changes).
//   - DELETE purges all rows for the file; subsequent lookup is 501.
//   - Cross-project caller without source-project membership → 404.
//   - Store endpoint: round-trip via API (store → lookup hit), idempotent
//     re-store, validation (bad kind, malformed b64, empty payload),
//     cross-project store → 404.

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// DerivedCache is registered in main.go's allScenarios.
func DerivedCache(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	// --- 1. Alice + project + source circuit file. ---
	alice, status, raw := registerWS(c, "derived-alice@example.com", "alicepass99hunter", "Derived Alice")
	if !s.Status("register alice", status, 201, raw) {
		return
	}
	if !s.True("alice default_workspace present", alice.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	type proj struct {
		ID string `json:"id"`
	}
	var elecProj proj
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]any{
		"workspace_id": alice.DefaultWorkspace.ID,
		"name":         "Derived — PCB",
		"tags":         []string{"electronics"},
		"starter":      "circuit",
	}, alice.AccessToken, &elecProj)
	if !s.Status("create electronics project", status, 201, raw) {
		return
	}
	pid := elecProj.ID

	circuitSrc := `<board width="40mm" height="30mm" />`
	var circuitRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "main.circuit.tsx",
			"kind":      "circuit",
			"parent_id": nil,
			"content":   circuitSrc,
		}, alice.AccessToken, &circuitRow)
	if !s.Status("create circuit file", status, 201, raw) {
		return
	}
	fid := circuitRow.ID

	// --- 2. Cache miss → 501. ---
	type lookupResp struct {
		Cached      bool   `json:"cached"`
		DerivedKind string `json:"derived_kind"`
		PayloadB64  string `json:"payload_b64,omitempty"`
		Error       string `json:"error,omitempty"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, alice.AccessToken, nil)
	if !s.Status("cache miss → 501", status, 501, raw) {
		return
	}
	// DoJSON only decodes 2xx into out; for 501 we parse raw ourselves.
	var miss lookupResp
	if err := json.Unmarshal(raw, &miss); s.NoError("decode miss body", err) {
		s.Equal("miss.cached=false", miss.Cached, false)
		s.Equal("miss.error message", miss.Error, "compile-on-demand-not-yet-wired")
		s.Equal("miss.derived_kind echo", miss.DerivedKind, "circuit_board_3d")
	}

	// --- 3. Bad derived_kind → 400. ---
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "rocket-fuel"}, alice.AccessToken, nil)
	s.Status("bad derived_kind → 400", status, 400, raw)

	// --- 4. Pre-seed a row directly + lookup hits cache. ---
	sum := sha256.Sum256([]byte(circuitSrc))
	hash := hex.EncodeToString(sum[:])
	payload := []byte("compiled-mesh-v1")
	if _, err := env.Pool.Exec(ctx, `
		insert into derived_artifacts(source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
		values ($1, $2, $3, $4, $5)
	`, fid, hash, "circuit_board_3d", payload, len(payload)); !s.NoError("seed cache row", err) {
		return
	}

	var hit lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, alice.AccessToken, &hit)
	if !s.Status("seeded cache → 200", status, 200, raw) {
		return
	}
	s.Equal("hit.cached=true", hit.Cached, true)
	s.Equal("hit.derived_kind echo", hit.DerivedKind, "circuit_board_3d")
	got, derr := base64.StdEncoding.DecodeString(hit.PayloadB64)
	if s.NoError("decode payload_b64", derr) {
		s.Equal("payload round-trip", string(got), string(payload))
	}

	// Other derived_kind for the same file is still cold.
	var otherKind lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "jscad_mesh"}, alice.AccessToken, &otherKind)
	s.Status("other kind still cold → 501", status, 501, raw)

	// --- 5. Editing the source invalidates by SHA mismatch. ---
	newSrc := circuitSrc + "\n// edited"
	status, raw, _ = c.DoJSON("PATCH", "/api/projects/"+pid+"/files/"+fid,
		map[string]any{"content": newSrc}, alice.AccessToken, nil)
	if !s.Status("edit source content", status, 200, raw) {
		return
	}
	var stale lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, alice.AccessToken, &stale)
	s.Status("stale sha → 501", status, 501, raw)

	// --- 6. DELETE purges all rows. ---
	type purgeResp struct {
		Purged int64 `json:"purged"`
	}
	var purged purgeResp
	status, raw, _ = c.DoJSON("DELETE", "/api/projects/"+pid+"/files/"+fid+"/derived",
		nil, alice.AccessToken, &purged)
	if s.Status("purge → 200", status, 200, raw) {
		s.Equal("purge count = 1 (the seeded row)", purged.Purged, int64(1))
	}

	// Re-seed at the new content hash, confirm hit, then purge again.
	newSum := sha256.Sum256([]byte(newSrc))
	newHash := hex.EncodeToString(newSum[:])
	if _, err := env.Pool.Exec(ctx, `
		insert into derived_artifacts(source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
		values ($1, $2, $3, $4, $5)
	`, fid, newHash, "circuit_board_3d", payload, len(payload)); !s.NoError("re-seed at new sha", err) {
		return
	}
	var hit2 lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, alice.AccessToken, &hit2)
	if s.Status("re-seeded cache → 200", status, 200, raw) {
		s.Equal("re-seed hit.cached=true", hit2.Cached, true)
	}

	// Final purge to confirm count + that subsequent lookup is 501.
	var purged2 purgeResp
	status, raw, _ = c.DoJSON("DELETE", "/api/projects/"+pid+"/files/"+fid+"/derived",
		nil, alice.AccessToken, &purged2)
	if s.Status("second purge → 200", status, 200, raw) {
		s.Equal("second purge count = 1", purged2.Purged, int64(1))
	}
	var afterPurge lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, alice.AccessToken, &afterPurge)
	s.Status("after purge → 501", status, 501, raw)

	// --- 7. Cross-project: Bob (no membership) → 404, no leak. ---
	bob, status, raw := registerWS(c, "derived-bob@example.com", "bobpass99hunter", "Derived Bob")
	if !s.Status("register bob", status, 201, raw) {
		return
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+fid+"/derived",
		map[string]any{"derived_kind": "circuit_board_3d"}, bob.AccessToken, nil)
	s.Status("bob lookup → 404", status, 404, raw)
	status, raw, _ = c.DoJSON("DELETE", "/api/projects/"+pid+"/files/"+fid+"/derived",
		nil, bob.AccessToken, nil)
	s.Status("bob purge → 404", status, 404, raw)

	// Sanity: the response shape on 404 doesn't leak anything project-shaped.
	var probe map[string]any
	if err := json.Unmarshal(raw, &probe); s.NoError("decode bob 404", err) {
		_, hasErr := probe["error"]
		s.True("bob 404 carries error key only", hasErr,
			"expected 'error' key in 404 response, got %v", probe)
	}

	// --- 8. Store endpoint round-trip on a fresh file. ---
	// New file so we don't clash with the prior seed/purge state.
	storeSrc := `<board width="60mm" height="40mm" />`
	var storeRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "store.circuit.tsx",
			"kind":      "circuit",
			"parent_id": nil,
			"content":   storeSrc,
		}, alice.AccessToken, &storeRow)
	if !s.Status("create store-target circuit file", status, 201, raw) {
		return
	}
	storeFid := storeRow.ID

	type storeResp struct {
		Stored           bool   `json:"stored"`
		DerivedKind      string `json:"derived_kind"`
		PayloadSizeBytes int    `json:"payload_size_bytes"`
	}

	// Store → 200, stored:true.
	originalPayload := []byte("compiled-jscad-mesh-v1")
	originalB64 := base64.StdEncoding.EncodeToString(originalPayload)
	var stored storeResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived/store",
		map[string]any{
			"derived_kind": "jscad_mesh",
			"payload_b64":  originalB64,
		}, alice.AccessToken, &stored)
	if s.Status("store payload → 200", status, 200, raw) {
		s.Equal("stored=true", stored.Stored, true)
		s.Equal("stored.derived_kind echo", stored.DerivedKind, "jscad_mesh")
		s.Equal("stored.payload_size_bytes", stored.PayloadSizeBytes, len(originalPayload))
	}

	// Lookup at the same key returns the same payload.
	var afterStore lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived",
		map[string]any{"derived_kind": "jscad_mesh"}, alice.AccessToken, &afterStore)
	if s.Status("lookup after store → 200", status, 200, raw) {
		s.Equal("after-store cached=true", afterStore.Cached, true)
		decoded, derr := base64.StdEncoding.DecodeString(afterStore.PayloadB64)
		if s.NoError("decode after-store payload", derr) {
			s.Equal("payload round-trip via API", string(decoded), string(originalPayload))
		}
	}

	// Re-store at the same key (idempotent) with a different payload —
	// next lookup must reflect the updated bytes.
	updatedPayload := []byte("compiled-jscad-mesh-v2-updated")
	updatedB64 := base64.StdEncoding.EncodeToString(updatedPayload)
	var restored storeResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived/store",
		map[string]any{
			"derived_kind": "jscad_mesh",
			"payload_b64":  updatedB64,
		}, alice.AccessToken, &restored)
	if s.Status("re-store same key → 200", status, 200, raw) {
		s.Equal("re-store payload_size_bytes updated", restored.PayloadSizeBytes, len(updatedPayload))
	}
	var afterRestore lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived",
		map[string]any{"derived_kind": "jscad_mesh"}, alice.AccessToken, &afterRestore)
	if s.Status("lookup after re-store → 200", status, 200, raw) {
		decoded, derr := base64.StdEncoding.DecodeString(afterRestore.PayloadB64)
		if s.NoError("decode after-restore payload", derr) {
			s.Equal("re-store payload reflected on read", string(decoded), string(updatedPayload))
		}
	}

	// Bad derived_kind → 400.
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived/store",
		map[string]any{
			"derived_kind": "rocket-fuel",
			"payload_b64":  originalB64,
		}, alice.AccessToken, nil)
	s.Status("store bad derived_kind → 400", status, 400, raw)

	// Malformed base64 → 400.
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived/store",
		map[string]any{
			"derived_kind": "jscad_mesh",
			"payload_b64":  "!!! not base64 @@",
		}, alice.AccessToken, nil)
	s.Status("store malformed base64 → 400", status, 400, raw)

	// Empty payload is allowed: lookup returns cached:true with an
	// empty payload_b64 string (0-byte payload round-trips cleanly).
	// Use a fresh file so we don't clobber the round-trip assertions
	// above; an empty store at the same key would overwrite the v2
	// payload we just verified.
	emptySrc := `<board width="10mm" height="10mm" />`
	var emptyRow struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{
			"name":      "empty.circuit.tsx",
			"kind":      "circuit",
			"parent_id": nil,
			"content":   emptySrc,
		}, alice.AccessToken, &emptyRow)
	if !s.Status("create empty-payload target file", status, 201, raw) {
		return
	}
	emptyFid := emptyRow.ID
	var emptyStored storeResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+emptyFid+"/derived/store",
		map[string]any{
			"derived_kind": "sketch_geom2",
			"payload_b64":  "",
		}, alice.AccessToken, &emptyStored)
	if s.Status("store empty payload → 200", status, 200, raw) {
		s.Equal("empty payload_size_bytes=0", emptyStored.PayloadSizeBytes, 0)
	}
	var emptyHit lookupResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+emptyFid+"/derived",
		map[string]any{"derived_kind": "sketch_geom2"}, alice.AccessToken, &emptyHit)
	if s.Status("lookup empty stored → 200", status, 200, raw) {
		s.Equal("empty cached=true", emptyHit.Cached, true)
		s.Equal("empty payload_b64 is empty string", emptyHit.PayloadB64, "")
	}

	// Cross-project: bob has no membership; store must 404 too.
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files/"+storeFid+"/derived/store",
		map[string]any{
			"derived_kind": "jscad_mesh",
			"payload_b64":  originalB64,
		}, bob.AccessToken, nil)
	s.Status("bob store → 404", status, 404, raw)
}
