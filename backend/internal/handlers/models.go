package handlers

import (
	"net/http"

	"github.com/imranp/kerf/backend/internal/llm"
)

// ModelInfoWithDefault wraps llm.ModelInfo with a per-response IsDefault flag.
type ModelInfoWithDefault struct {
	llm.ModelInfo
	IsDefault bool `json:"is_default"`
}

// ListModels returns the models that are usable on this server (i.e. their
// provider has an API key configured), each annotated with whether it is the
// configured default.
func (d *Deps) ListModels(w http.ResponseWriter, r *http.Request) {
	avail := d.LLM.Available()
	def := d.LLM.Default()
	out := make([]ModelInfoWithDefault, 0, len(avail))
	for _, m := range avail {
		out = append(out, ModelInfoWithDefault{ModelInfo: m, IsDefault: m.ID == def})
	}
	writeJSON(w, http.StatusOK, out)
}
