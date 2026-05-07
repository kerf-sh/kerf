package scenarios

import (
	"fmt"
	"strings"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// Features exercises CRUD across the major resources: projects, files,
// revisions, threads/messages (with the no-LLM fallback), share links, and
// members.
func Features(s *runner.Suite, env *runner.Env) {
	c := env.Client

	// Two registered users so we can test members + share.
	owner, status, raw := register(c, "owner@example.com", "ownerpassword1", "Owner")
	if !s.Status("register owner", status, 201, raw) {
		return
	}
	guest, status, raw := register(c, "guest@example.com", "guestpassword1", "Guest")
	if !s.Status("register guest", status, 201, raw) {
		return
	}

	// --- Project create / update / delete ---
	var proj struct {
		ID      string `json:"id"`
		OwnerID string `json:"owner_id"`
		Name    string `json:"name"`
		MyRole  string `json:"my_role"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects", map[string]string{
		"name": "Feature project",
	}, owner.AccessToken, &proj)
	if !s.Status("create project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// PATCH /api/projects/{pid}.
	var updated struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	status, raw, _ = c.DoJSON("PATCH", "/api/projects/"+pid, map[string]string{
		"name": "Renamed project",
	}, owner.AccessToken, &updated)
	if s.Status("patch project", status, 200, raw) {
		s.Equal("project renamed", updated.Name, "Renamed project")
	}

	// --- File CRUD with revisions ---
	type fileResp struct {
		ID      string  `json:"id"`
		Name    string  `json:"name"`
		Kind    string  `json:"kind"`
		Content *string `json:"content"`
	}
	var f fileResp
	status, raw, _ = c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/files", pid), map[string]any{
		"name":    "widget.jscad",
		"kind":    "file",
		"content": "// v1",
	}, owner.AccessToken, &f)
	if !s.Status("create file", status, 201, raw) {
		return
	}
	s.Equal("file kind", f.Kind, "file")
	fid := f.ID

	// GET /api/projects/{pid}/files/{fid} returns content.
	var got fileResp
	status, raw, _ = c.DoJSON("GET", fmt.Sprintf("/api/projects/%s/files/%s", pid, fid),
		nil, owner.AccessToken, &got)
	if s.Status("get file", status, 200, raw) {
		s.True("file content present", got.Content != nil, "content is nil")
		if got.Content != nil {
			s.Equal("file content matches", *got.Content, "// v1")
		}
	}

	// PATCH content → revision recorded.
	status, raw, _ = c.DoJSON("PATCH", fmt.Sprintf("/api/projects/%s/files/%s", pid, fid),
		map[string]string{"content": "// v2"}, owner.AccessToken, &got)
	if s.Status("patch file content", status, 200, raw) {
		s.Equal("file v2 content", *got.Content, "// v2")
	}

	// Revisions list should now have 2+ entries (initial + v2).
	var revisions []struct {
		ID     string `json:"id"`
		Source string `json:"source"`
	}
	status, raw, _ = c.DoJSON("GET", fmt.Sprintf("/api/projects/%s/files/%s/revisions", pid, fid),
		nil, owner.AccessToken, &revisions)
	if s.Status("list revisions", status, 200, raw) {
		s.True("at least 2 revisions", len(revisions) >= 2, "got %d revisions", len(revisions))
	}

	// DELETE soft-deletes.
	status, raw, _ = c.Do("DELETE", fmt.Sprintf("/api/projects/%s/files/%s", pid, fid),
		nil, owner.AccessToken)
	s.Status("delete file", status, 204, raw)

	// File no longer appears in list.
	var fileList []fileResp
	status, raw, _ = c.DoJSON("GET", fmt.Sprintf("/api/projects/%s/files", pid), nil, owner.AccessToken, &fileList)
	if s.Status("list files post-delete", status, 200, raw) {
		found := false
		for _, x := range fileList {
			if x.ID == fid {
				found = true
				break
			}
		}
		s.False("deleted file not in list", found, "deleted file still listed")
	}

	// Revisions endpoint still works for the soft-deleted file.
	var revisionsAfter []struct {
		ID     string `json:"id"`
		Source string `json:"source"`
	}
	status, raw, _ = c.DoJSON("GET", fmt.Sprintf("/api/projects/%s/files/%s/revisions", pid, fid),
		nil, owner.AccessToken, &revisionsAfter)
	if s.Status("list revisions post-delete", status, 200, raw) {
		s.True("revisions still readable", len(revisionsAfter) >= 1, "got 0 revisions")
	}

	// Restore: pick the oldest revision and resurrect.
	if len(revisionsAfter) > 0 {
		rid := revisionsAfter[len(revisionsAfter)-1].ID
		var restored fileResp
		status, raw, _ = c.DoJSON("POST",
			fmt.Sprintf("/api/projects/%s/files/%s/restore/%s", pid, fid, rid),
			nil, owner.AccessToken, &restored)
		if s.Status("restore revision", status, 200, raw) {
			s.Equal("restored id", restored.ID, fid)
		}
	}

	// --- Threads + messages w/ no LLM configured (fallback) ---
	var thread struct {
		ID    string `json:"id"`
		Title string `json:"title"`
	}
	status, raw, _ = c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/threads", pid),
		map[string]string{"title": "Hello"}, owner.AccessToken, &thread)
	if !s.Status("create thread", status, 201, raw) {
		return
	}

	var postResp struct {
		AssistantMessage struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"assistant_message"`
	}
	status, raw, _ = c.DoJSON("POST",
		fmt.Sprintf("/api/projects/%s/threads/%s/messages", pid, thread.ID),
		map[string]any{"content": "make a cube"}, owner.AccessToken, &postResp)
	if s.Status("post message no-llm", status, 201, raw) {
		s.Equal("assistant role", postResp.AssistantMessage.Role, "assistant")
		s.Contains("fallback message text",
			postResp.AssistantMessage.Content, "LLM not configured")
	}

	// --- Share link ---
	var share struct {
		ID    string `json:"id"`
		Token string `json:"token"`
		Role  string `json:"role"`
	}
	status, raw, _ = c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/share/links", pid),
		map[string]string{"role": "viewer"}, owner.AccessToken, &share)
	if !s.Status("create share link", status, 201, raw) {
		return
	}

	// List share links (token is redacted in list, but at least one row).
	var shareList []map[string]any
	status, raw, _ = c.DoJSON("GET", fmt.Sprintf("/api/projects/%s/share/links", pid),
		nil, owner.AccessToken, &shareList)
	if s.Status("list share links", status, 200, raw) {
		s.True("share list >= 1", len(shareList) >= 1, "got %d", len(shareList))
	}

	// Anonymous lookup of /api/share/{token} succeeds without auth.
	status, raw, _ = c.Do("GET", "/api/share/"+share.Token, nil, "")
	s.Status("share lookup anon", status, 200, raw)

	// guest accepts → guest now has viewer role on the project.
	status, raw, _ = c.Do("POST", "/api/share/"+share.Token+"/accept", nil, guest.AccessToken)
	s.Status("share accept by guest", status, 200, raw)

	// guest's GET project should now succeed.
	var guestSeesProject struct {
		MyRole string `json:"my_role"`
	}
	status, raw, _ = c.DoJSON("GET", "/api/projects/"+pid, nil, guest.AccessToken, &guestSeesProject)
	if s.Status("guest GET shared project", status, 200, raw) {
		s.Equal("guest role", guestSeesProject.MyRole, "viewer")
	}

	// --- Members: add by email, change role, remove ---
	type memberResp struct {
		UserID string `json:"user_id"`
		Role   string `json:"role"`
	}
	// Add a third user just for member CRUD.
	third, status, raw := register(c, "third@example.com", "thirdpassword1", "Third")
	if !s.Status("register third", status, 201, raw) {
		return
	}
	var added memberResp
	status, raw, _ = c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/members", pid),
		map[string]string{"email": "third@example.com", "role": "editor"},
		owner.AccessToken, &added)
	if s.Status("add member", status, 201, raw) {
		s.Equal("added.role", added.Role, "editor")
		s.Equal("added.user_id", added.UserID, third.User.ID)
	}

	// Change role.
	var changed memberResp
	status, raw, _ = c.DoJSON("PATCH",
		fmt.Sprintf("/api/projects/%s/members/%s", pid, third.User.ID),
		map[string]string{"role": "viewer"}, owner.AccessToken, &changed)
	if s.Status("change role", status, 200, raw) {
		s.Equal("changed.role", changed.Role, "viewer")
	}

	// Remove.
	status, raw, _ = c.Do("DELETE",
		fmt.Sprintf("/api/projects/%s/members/%s", pid, third.User.ID),
		nil, owner.AccessToken)
	s.Status("remove member", status, 204, raw)

	// DELETE project (owner).
	status, raw, _ = c.Do("DELETE", "/api/projects/"+pid, nil, owner.AccessToken)
	s.Status("delete project", status, 204, raw)

	// Final sanity: GET deleted project → 404.
	status, raw, _ = c.Do("GET", "/api/projects/"+pid, nil, owner.AccessToken)
	s.Status("GET deleted project", status, 404, raw)

	// (Helper to silence unused-import flagged otherwise.)
	_ = strings.TrimSpace
}
