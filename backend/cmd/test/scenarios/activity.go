package scenarios

// Activity timeline scenarios.
//
// Verifies the merged event feed (revisions + chat + file lifecycle +
// project_created) returned by GET /api/projects/{pid}/activity, the
// pagination cursor, and the privacy 404 for non-members.

import (
	"fmt"
	"net/url"
	"time"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// Activity exercises GET /api/projects/{pid}/activity end-to-end.
func Activity(s *runner.Suite, env *runner.Env) {
	c := env.Client
	_ = env

	owner, status, raw := register(c, "act-owner@example.com", "actpass1", "Act Owner")
	if !s.Status("register act owner", status, 201, raw) {
		return
	}
	stranger, status, raw := register(c, "stranger@example.com", "strangerpass1", "Stranger")
	if !s.Status("register stranger", status, 201, raw) {
		return
	}

	var proj struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects",
		map[string]string{"name": "Active project"}, owner.AccessToken, &proj)
	if !s.Status("create act project", status, 201, raw) {
		return
	}
	pid := proj.ID

	// --- Generate a mix of events: file creates + edits + delete + chat. ---
	type fileResp struct {
		ID   string `json:"id"`
		Kind string `json:"kind"`
	}
	var f1 fileResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "alpha.jscad", "kind": "file", "content": "// v1"},
		owner.AccessToken, &f1)
	s.Status("create alpha", status, 201, raw)

	// Two patches → two extra edit events.
	for i, body := range []string{"// v2", "// v3"} {
		status, raw, _ = c.Do("PATCH", "/api/projects/"+pid+"/files/"+f1.ID,
			map[string]string{"content": body}, owner.AccessToken)
		s.Status(fmt.Sprintf("patch alpha #%d", i+1), status, 200, raw)
	}

	var f2 fileResp
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/files",
		map[string]any{"name": "beta.jscad", "kind": "file", "content": "// b1"},
		owner.AccessToken, &f2)
	s.Status("create beta", status, 201, raw)

	// Delete beta → file_deleted event.
	status, raw, _ = c.Do("DELETE", "/api/projects/"+pid+"/files/"+f2.ID, nil, owner.AccessToken)
	s.Status("delete beta", status, 204, raw)

	// Chat: thread + user message → chat event.
	var thread struct {
		ID string `json:"id"`
	}
	status, raw, _ = c.DoJSON("POST", "/api/projects/"+pid+"/threads",
		map[string]string{"title": "Activity thread"}, owner.AccessToken, &thread)
	s.Status("create thread", status, 201, raw)
	status, raw, _ = c.Do("POST",
		"/api/projects/"+pid+"/threads/"+thread.ID+"/messages",
		map[string]any{"content": "How tall is this?"}, owner.AccessToken)
	s.Status("post message", status, 201, raw)

	// --- GET /activity?limit=20. ---
	var feed activityResp
	status, raw, _ = c.DoJSON("GET",
		"/api/projects/"+pid+"/activity?limit=20",
		nil, owner.AccessToken, &feed)
	if !s.Status("GET /activity", status, 200, raw) {
		return
	}

	s.True("feed has events", len(feed.Events) > 0, "got %d", len(feed.Events))

	kinds := map[string]int{}
	for _, e := range feed.Events {
		kinds[e.Kind]++
	}
	s.True("has project_created", kinds["project_created"] >= 1, "kinds=%v", kinds)
	s.True("has file_created (alpha+beta)", kinds["file_created"] >= 2, "got %d", kinds["file_created"])
	s.True("has file_deleted (beta)", kinds["file_deleted"] >= 1, "got %d", kinds["file_deleted"])
	s.True("has edit", kinds["edit"] >= 1, "got %d", kinds["edit"])
	s.True("has chat", kinds["chat"] >= 1, "got %d", kinds["chat"])

	// Newest-first ordering.
	if len(feed.Events) >= 2 {
		first := feed.Events[0].CreatedAt
		last := feed.Events[len(feed.Events)-1].CreatedAt
		s.True("newest-first ordering", !first.Before(last),
			"first=%s last=%s", first, last)
	}

	// --- Pagination via ?before=. ---
	var page1 activityResp
	status, raw, _ = c.DoJSON("GET",
		"/api/projects/"+pid+"/activity?limit=2",
		nil, owner.AccessToken, &page1)
	if s.Status("GET /activity limit=2", status, 200, raw) {
		s.Equal("page1 len=2", len(page1.Events), 2)
		s.True("page1 has next_cursor", page1.NextCursor != nil, "cursor=%v", page1.NextCursor)
		if page1.NextCursor != nil {
			cur := *page1.NextCursor
			var page2 activityResp
			status, raw, _ = c.DoJSON("GET",
				"/api/projects/"+pid+"/activity?limit=2&before="+url.QueryEscape(cur),
				nil, owner.AccessToken, &page2)
			s.Status("GET /activity page2", status, 200, raw)
			s.True("page2 non-empty", len(page2.Events) > 0)
			if len(page1.Events) > 0 && len(page2.Events) > 0 {
				p1Oldest := page1.Events[len(page1.Events)-1].CreatedAt
				p2Newest := page2.Events[0].CreatedAt
				s.True("page2 strictly older",
					p2Newest.Before(p1Oldest) ||
						(p2Newest.Equal(p1Oldest) && page2.Events[0].ID != page1.Events[len(page1.Events)-1].ID),
					"p2[0]=%s p1[-1]=%s", p2Newest, p1Oldest)
			}
		}
	}

	// --- Permissions: stranger gets 404 (existence privacy). ---
	status, raw, _ = c.Do("GET", "/api/projects/"+pid+"/activity", nil, stranger.AccessToken)
	s.Status("stranger /activity → 404", status, 404, raw)
}

type activityResp struct {
	Events     []activityEvent `json:"events"`
	NextCursor *string         `json:"next_cursor"`
}

type activityEvent struct {
	ID        string    `json:"id"`
	Kind      string    `json:"kind"`
	CreatedAt time.Time `json:"created_at"`
}
