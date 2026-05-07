// Fixture helpers used by the scenarios. Kept in package main alongside
// the rest of the CLI rather than runner/ so they can grow scenario-specific
// shortcuts without bloating the public runner API.
package main

import (
	"encoding/json"
	"fmt"

	"github.com/imranp/kerf/backend/cmd/test/runner"
)

// authBundle is the shape /auth/register and /auth/login both return.
type authBundle struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	User         struct {
		ID    string `json:"id"`
		Email string `json:"email"`
		Name  string `json:"name"`
	} `json:"user"`
}

// registerUser POSTs /auth/register and returns the parsed bundle.
func registerUser(c *runner.Client, email, password, name string) (authBundle, int, []byte, error) {
	var out authBundle
	status, raw, err := c.DoJSON("POST", "/auth/register", map[string]string{
		"email":    email,
		"password": password,
		"name":     name,
	}, "", &out)
	return out, status, raw, err
}

// loginUser POSTs /auth/login and returns the parsed bundle.
func loginUser(c *runner.Client, email, password string) (authBundle, int, []byte, error) {
	var out authBundle
	status, raw, err := c.DoJSON("POST", "/auth/login", map[string]string{
		"email":    email,
		"password": password,
	}, "", &out)
	return out, status, raw, err
}

// project is the trimmed project shape we care about in scenarios.
type project struct {
	ID      string `json:"id"`
	OwnerID string `json:"owner_id"`
	Name    string `json:"name"`
	MyRole  string `json:"my_role"`
}

// createProject POSTs /api/projects.
func createProject(c *runner.Client, name, token string) (project, int, []byte, error) {
	var out project
	status, raw, err := c.DoJSON("POST", "/api/projects", map[string]string{
		"name":        name,
		"description": "",
	}, token, &out)
	return out, status, raw, err
}

// file is the trimmed file shape used in scenarios.
type file struct {
	ID      string  `json:"id"`
	Name    string  `json:"name"`
	Kind    string  `json:"kind"`
	Content *string `json:"content"`
}

// createFile POSTs /api/projects/{pid}/files.
func createFile(c *runner.Client, pid, name, kind, content, token string) (file, int, []byte, error) {
	body := map[string]any{
		"name": name,
		"kind": kind,
	}
	if content != "" {
		body["content"] = content
	}
	var out file
	status, raw, err := c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/files", pid), body, token, &out)
	return out, status, raw, err
}

// shareLink is the trimmed share-link shape.
type shareLink struct {
	ID    string `json:"id"`
	Token string `json:"token"`
	Role  string `json:"role"`
}

// createShareLink POSTs /api/projects/{pid}/share/links.
func createShareLink(c *runner.Client, pid, role, token string) (shareLink, int, []byte, error) {
	var out shareLink
	status, raw, err := c.DoJSON("POST", fmt.Sprintf("/api/projects/%s/share/links", pid),
		map[string]string{"role": role}, token, &out)
	return out, status, raw, err
}

// rawError peeks at "error" inside a JSON body (for asserting messages).
func rawError(body []byte) string {
	var m map[string]any
	if err := json.Unmarshal(body, &m); err != nil {
		return ""
	}
	if v, ok := m["error"].(string); ok {
		return v
	}
	return ""
}
