package models

import (
	"encoding/json"
	"time"
)

type User struct {
	ID          string    `json:"id"`
	Email       string    `json:"email"`
	Name        string    `json:"name"`
	AvatarURL   string    `json:"avatar_url"`
	AccountRole string    `json:"account_role"`
	IsSystem    bool      `json:"is_system"`
	CreatedAt   time.Time `json:"created_at"`
}

type Project struct {
	ID          string    `json:"id"`
	WorkspaceID string    `json:"workspace_id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	Visibility  string    `json:"visibility"`
	MyRole      string    `json:"my_role,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// Workspace is the top-level multi-member container that owns projects.
type Workspace struct {
	ID           string    `json:"id"`
	Slug         string    `json:"slug"`
	Name         string    `json:"name"`
	AvatarURL    string    `json:"avatar_url,omitempty"`
	CreatedBy    string    `json:"created_by"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
	MyRole       string    `json:"my_role,omitempty"`
	MemberCount  int       `json:"member_count,omitempty"`
	ProjectCount int       `json:"project_count,omitempty"`
}

// WorkspaceMember associates a user with a workspace (owner / admin / member).
type WorkspaceMember struct {
	WorkspaceID string    `json:"workspace_id"`
	UserID      string    `json:"user_id"`
	Role        string    `json:"role"`
	User        User      `json:"user"`
	CreatedAt   time.Time `json:"created_at"`
}

// WorkspaceInvite is a pending invite to a workspace by email + token.
type WorkspaceInvite struct {
	ID          string    `json:"id"`
	WorkspaceID string    `json:"workspace_id"`
	Email       string    `json:"email"`
	Role        string    `json:"role"`
	Token       string    `json:"token,omitempty"`
	CreatedBy   string    `json:"created_by"`
	CreatedAt   time.Time `json:"created_at"`
}

type File struct {
	ID          string    `json:"id"`
	ProjectID   string    `json:"project_id"`
	ParentID    *string   `json:"parent_id"`
	Name        string    `json:"name"`
	Kind        string    `json:"kind"`
	Content     *string   `json:"content,omitempty"`
	StorageKey  *string   `json:"storage_key,omitempty"`
	MimeType    *string   `json:"mime_type,omitempty"`
	Size        *int64    `json:"size,omitempty"`
	DownloadURL *string   `json:"download_url,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Thread struct {
	ID            string     `json:"id"`
	ProjectID     string     `json:"project_id"`
	FileID        *string    `json:"file_id"`
	Title         string     `json:"title"`
	IsStarred     bool       `json:"is_starred"`
	LastMessageAt *time.Time `json:"last_message_at"`
	Model         *string    `json:"model"`
	CreatedAt     time.Time  `json:"created_at"`
}

type PartRef struct {
	FileID string `json:"file_id"`
	PartID string `json:"part_id"`
	Label  string `json:"label,omitempty"`
}

type ToolCall struct {
	ID            string `json:"id"`
	Name          string `json:"name"`
	ArgumentsJSON string `json:"arguments"`
}

type Message struct {
	ID         string          `json:"id"`
	ThreadID   string          `json:"thread_id"`
	Role       string          `json:"role"`
	Content    string          `json:"content"`
	PartRefs   json.RawMessage `json:"part_refs"`
	ToolCalls  json.RawMessage `json:"tool_calls"`
	ToolCallID *string         `json:"tool_call_id"`
	// ToolName is denormalized for `role='tool'` rows so the client can render
	// the chip and decide whether to refresh files without cross-referencing
	// the originating assistant message. Not stored in DB; derived on read.
	ToolName  *string   `json:"tool_name,omitempty"`
	Model     *string   `json:"model"`
	CreatedAt time.Time `json:"created_at"`
}

type Member struct {
	UserID    string    `json:"user_id"`
	ProjectID string    `json:"project_id"`
	Role      string    `json:"role"`
	User      User      `json:"user"`
	CreatedAt time.Time `json:"created_at"`
}

type ShareLink struct {
	ID        string     `json:"id"`
	ProjectID string     `json:"project_id"`
	Token     string     `json:"token,omitempty"`
	Role      string     `json:"role"`
	ExpiresAt *time.Time `json:"expires_at"`
	RevokedAt *time.Time `json:"revoked_at"`
	MaxUses   *int       `json:"max_uses"`
	Uses      int        `json:"uses"`
	CreatedAt time.Time  `json:"created_at"`
}
