package kerf

// FileInfo describes a file entry returned by files.list.
type FileInfo struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Kind     string `json:"kind"`
	ParentID string `json:"parent_id,omitempty"`
}

// FileContent holds the content of a file returned by files.read.
type FileContent struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Kind    string `json:"kind"`
	Content string `json:"content"`
}

// Equation describes a single equation variable.
type Equation struct {
	Name       string `json:"name"`
	Expression string `json:"expression"`
	Value      any    `json:"value,omitempty"`
}

// Configuration describes a named parameter configuration.
type Configuration struct {
	ID     string         `json:"id"`
	Label  string         `json:"label"`
	Params map[string]any `json:"params"`
}

// Revision describes a single file revision.
type Revision struct {
	ID        string `json:"id"`
	FileID    string `json:"file_id"`
	CreatedAt string `json:"created_at"`
	Message   string `json:"message,omitempty"`
}

// DocResult describes a single document search result.
type DocResult struct {
	ID      string  `json:"id"`
	Title   string  `json:"title"`
	Excerpt string  `json:"excerpt"`
	Score   float64 `json:"score"`
	URL     string  `json:"url,omitempty"`
}

// WriteResult is returned by files.write and files.edit.
type WriteResult struct {
	OK         bool   `json:"ok"`
	RevisionID string `json:"revision_id,omitempty"`
}
