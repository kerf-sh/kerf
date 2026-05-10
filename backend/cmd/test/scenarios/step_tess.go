package scenarios

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"time"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// StepTess exercises the STEP pre-tessellation pipeline end-to-end:
//
//   1. Upload a tiny STEP-shaped binary via /api/projects/:pid/assets.
//   2. Verify a step_tessellation_jobs row was enqueued.
//   3. Poll GET /api/projects/:pid/files/:fid until tessellation_status='done'.
//   4. Verify mesh_url is non-empty (handlers.attachMeshURL hangs that off
//      mesh_storage_key, which the placeholder worker stamped on the file).
//
// The placeholder worker writes an "empty" GLB — we don't try to load it
// here; the wiring contract is "row reaches done; mesh_url present". Real
// OCCT-WASM tessellation lands in a follow-up.
func StepTess(s *runner.Suite, env *runner.Env) {
	c := env.Client
	ctx := context.Background()

	owner, status, raw := registerWS(c, "step-tess@example.com", "steptesspass1", "Step Tess")
	if !s.Status("register step_tess owner", status, 201, raw) {
		return
	}
	if !s.True("step_tess default_workspace present", owner.DefaultWorkspace != nil,
		"expected default_workspace on register response") {
		return
	}

	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]string{
		"name":         "Step Tess",
		"workspace_id": owner.DefaultWorkspace.ID,
	}, owner.AccessToken, &proj)
	if !s.Status("create step_tess project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// Build a multipart body matching UploadAsset's shape: kind=step,
	// file=<bytes>. The placeholder worker doesn't validate STEP content,
	// so a header-shaped stub is sufficient.
	body, contentType := buildStepMultipart("dummy.step",
		[]byte("ISO-10303-21;\nHEADER;\nDUMMY;\nENDSEC;\nEND-ISO-10303-21;\n"))
	req, err := http.NewRequest("POST", c.BaseURL+"/api/projects/"+pid+"/assets", body)
	if !s.NoError("build upload request", err) {
		return
	}
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("Authorization", "Bearer "+owner.AccessToken)
	resp, err := c.DoRaw(req)
	if !s.NoError("send upload request", err) {
		return
	}
	uploadedBody, _ := io.ReadAll(resp.Body)
	_ = resp.Body.Close()
	if !s.Status("POST /assets kind=step", resp.StatusCode, 201, uploadedBody) {
		return
	}
	var fileResp struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(uploadedBody, &fileResp); !s.NoError("decode upload response", err) {
		return
	}
	fid := fileResp.ID
	if !s.NotEmpty("uploaded file id", fid) {
		return
	}

	// Sanity: a job row exists for this file with status queued|running|done.
	var jobStatus string
	if err := env.Pool.QueryRow(ctx,
		`select status from step_tessellation_jobs where file_id=$1`, fid,
	).Scan(&jobStatus); s.NoError("lookup job row", err) {
		s.True("job status is one of queued/running/done",
			jobStatus == "queued" || jobStatus == "running" || jobStatus == "done",
			"got %q", jobStatus)
	}

	// Poll the file detail endpoint up to 10s for tessellation_status='done'.
	// The placeholder worker's fakeWork is 100ms + 500ms idle gap so we
	// expect the first or second poll iteration to see done.
	deadline := time.Now().Add(10 * time.Second)
	type fileDetail struct {
		ID                 string  `json:"id"`
		MeshURL            *string `json:"mesh_url"`
		TessellationStatus *string `json:"tessellation_status"`
	}
	var fileOut fileDetail
	for {
		fileOut = fileDetail{}
		status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid+"/files/"+fid, nil,
			owner.AccessToken, &fileOut)
		if status != 200 {
			s.Status("GET file during poll", status, 200, raw)
			return
		}
		if fileOut.TessellationStatus != nil && *fileOut.TessellationStatus == "done" {
			break
		}
		if time.Now().After(deadline) {
			cur := "<nil>"
			if fileOut.TessellationStatus != nil {
				cur = *fileOut.TessellationStatus
			}
			s.Fail("await tessellation_status=done",
				fmt.Sprintf("timed out after 10s; last status=%s", cur))
			return
		}
		time.Sleep(100 * time.Millisecond)
	}

	s.Equal("final tessellation_status", *fileOut.TessellationStatus, "done")
	if !s.True("mesh_url non-nil", fileOut.MeshURL != nil, "expected mesh_url to be set") {
		return
	}
	s.NotEmpty("mesh_url non-empty", *fileOut.MeshURL)
}

// buildStepMultipart wraps the (filename, payload) in the same multipart
// shape UploadAsset expects: a `kind` text field plus a `file` part.
func buildStepMultipart(filename string, payload []byte) (*bytes.Buffer, string) {
	body := &bytes.Buffer{}
	mw := multipart.NewWriter(body)
	_ = mw.WriteField("kind", "step")
	hdr := textproto.MIMEHeader{}
	hdr.Set("Content-Disposition", fmt.Sprintf(`form-data; name="file"; filename=%q`, filename))
	hdr.Set("Content-Type", "model/step")
	pw, _ := mw.CreatePart(hdr)
	_, _ = pw.Write(payload)
	mw.Close()
	return body, mw.FormDataContentType()
}
