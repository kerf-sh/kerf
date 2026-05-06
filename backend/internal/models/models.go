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
	OwnerID     string    `json:"owner_id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	Visibility  string    `json:"visibility"`
	MyRole      string    `json:"my_role,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type File struct {
	ID        string    `json:"id"`
	ProjectID string    `json:"project_id"`
	ParentID  *string   `json:"parent_id"`
	Name      string    `json:"name"`
	Kind      string    `json:"kind"`
	Content   *string   `json:"content,omitempty"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Thread struct {
	ID            string     `json:"id"`
	ProjectID     string     `json:"project_id"`
	FileID        *string    `json:"file_id"`
	Title         string     `json:"title"`
	IsStarred     bool       `json:"is_starred"`
	LastMessageAt *time.Time `json:"last_message_at"`
	CreatedAt     time.Time  `json:"created_at"`
}

type PartRef struct {
	FileID string `json:"file_id"`
	PartID string `json:"part_id"`
	Label  string `json:"label,omitempty"`
}

type Message struct {
	ID        string          `json:"id"`
	ThreadID  string          `json:"thread_id"`
	Role      string          `json:"role"`
	Content   string          `json:"content"`
	PartRefs  json.RawMessage `json:"part_refs"`
	CreatedAt time.Time       `json:"created_at"`
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
