//go:build cloud
// +build cloud

package email

import (
	"bytes"
	"embed"
	"fmt"
	"path"
	"strings"
	"sync"
	"text/template"
)

//go:embed templates/*.html templates/*.txt
var templateFS embed.FS

// templatePair holds the parsed html + txt halves of a single template
// plus its subject line. Subjects live alongside the templates in a
// dedicated `subjects.txt` file (NOT in code) so the operator can change
// wording without recompiling — except, well, the corpus IS embedded,
// so they DO have to recompile. The split is for grep-ability.
type templatePair struct {
	subject string
	html    *template.Template
	text    *template.Template
}

// renderer caches parsed templates. Lazily populated on first use; the
// embed.FS is small enough that eager loading would also be fine, but
// the lazy path means a malformed template doesn't crash boot.
type renderer struct {
	mu    sync.RWMutex
	cache map[string]*templatePair
}

func newRenderer() *renderer {
	return &renderer{cache: map[string]*templatePair{}}
}

// Templates is the canonical list of template names the system knows
// about. Used by the admin "test send" endpoint to validate the input
// against the actual corpus.
var Templates = []string{
	"welcome",
	"password_reset",
	"password_reset_complete",
	"billing_receipt",
	"low_balance",
	"github_linked",
	"workshop_published",
}

// templateSubjects maps template names to subject lines. Subjects with
// `· kerf` suffix are receipts/notifications per the style guide;
// transactional state-change confirmations (welcome, password reset,
// github linked) skip the suffix because their subject already clearly
// names the product or action.
var templateSubjects = map[string]string{
	"welcome":                  "Welcome to kerf",
	"password_reset":           "Reset your kerf password",
	"password_reset_complete":  "Your kerf password was changed",
	"billing_receipt":          "Receipt for your top-up · kerf",
	"low_balance":              "Your balance is running low · kerf",
	"github_linked":            "GitHub linked to your kerf account",
	"workshop_published":       "Your project is live on kerf Workshop · kerf",
}

// Render produces a Message ready to hand off to a Provider. `to` is
// inserted as-is; the caller is responsible for validating it before
// calling. `data` is the template variable bag — see each template for
// the keys it expects. Missing keys render as empty strings (Go's
// default behavior with text/template).
func (r *renderer) Render(name, to string, data map[string]any) (Message, error) {
	pair, err := r.load(name)
	if err != nil {
		return Message{}, err
	}
	var htmlBuf, textBuf bytes.Buffer
	if err := pair.html.Execute(&htmlBuf, data); err != nil {
		return Message{}, fmt.Errorf("render %s html: %w", name, err)
	}
	if err := pair.text.Execute(&textBuf, data); err != nil {
		return Message{}, fmt.Errorf("render %s text: %w", name, err)
	}
	return Message{
		To:      to,
		Subject: pair.subject,
		HTML:    htmlBuf.String(),
		Text:    textBuf.String(),
		Tags:    map[string]string{"template": name},
	}, nil
}

func (r *renderer) load(name string) (*templatePair, error) {
	r.mu.RLock()
	if p, ok := r.cache[name]; ok {
		r.mu.RUnlock()
		return p, nil
	}
	r.mu.RUnlock()

	if !validTemplate(name) {
		return nil, fmt.Errorf("unknown template: %s", name)
	}
	subject, ok := templateSubjects[name]
	if !ok {
		return nil, fmt.Errorf("no subject mapped for %s", name)
	}

	htmlRaw, err := templateFS.ReadFile(path.Join("templates", name+".html"))
	if err != nil {
		return nil, fmt.Errorf("read %s.html: %w", name, err)
	}
	textRaw, err := templateFS.ReadFile(path.Join("templates", name+".txt"))
	if err != nil {
		return nil, fmt.Errorf("read %s.txt: %w", name, err)
	}
	htmlT, err := template.New(name + ".html").Parse(string(htmlRaw))
	if err != nil {
		return nil, fmt.Errorf("parse %s.html: %w", name, err)
	}
	textT, err := template.New(name + ".txt").Parse(string(textRaw))
	if err != nil {
		return nil, fmt.Errorf("parse %s.txt: %w", name, err)
	}

	pair := &templatePair{subject: subject, html: htmlT, text: textT}
	r.mu.Lock()
	r.cache[name] = pair
	r.mu.Unlock()
	return pair, nil
}

func validTemplate(name string) bool {
	for _, t := range Templates {
		if t == name {
			return true
		}
	}
	return false
}

// strippedSubject is a safety net for the SMTP path: if a template's
// subject contains a CR/LF (which would smuggle headers), we panic
// the render. Belt-and-braces — the embedded subjects don't contain
// newlines today, but adding a check costs nothing.
func init() {
	for k, v := range templateSubjects {
		if strings.ContainsAny(v, "\r\n") {
			panic(fmt.Sprintf("email: subject for %q contains CR/LF: %q", k, v))
		}
	}
}
