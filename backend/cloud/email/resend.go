//go:build cloud
// +build cloud

package email

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// resendProvider posts to https://api.resend.com/emails.
//
// Resend's API is dead simple: a single POST, JSON-in / JSON-out, the
// API key in an `Authorization: Bearer …` header. We don't bother with
// their Go SDK because pulling in a transitive dep tree to issue one
// HTTPS POST isn't worth it.
type resendProvider struct {
	apiKey   string
	from     string
	client   *http.Client
}

func newResend(creds Credentials) (*resendProvider, error) {
	if creds.APIKey == "" {
		return nil, fmt.Errorf("%w: resend api_key required", ErrInvalidCredentials)
	}
	if creds.FromEmail == "" {
		return nil, fmt.Errorf("%w: resend from_email required", ErrInvalidCredentials)
	}
	from := creds.FromEmail
	if creds.FromName != "" {
		from = fmt.Sprintf("%s <%s>", creds.FromName, creds.FromEmail)
	}
	return &resendProvider{
		apiKey: creds.APIKey,
		from:   from,
		client: &http.Client{Timeout: 15 * time.Second},
	}, nil
}

func (p *resendProvider) Name() string { return ProviderResend }

// resendRequest mirrors https://resend.com/docs/api-reference/emails/send-email
// with only the fields kerf actually populates.
type resendRequest struct {
	From    string            `json:"from"`
	To      []string          `json:"to"`
	Subject string            `json:"subject"`
	HTML    string            `json:"html,omitempty"`
	Text    string            `json:"text,omitempty"`
	ReplyTo string            `json:"reply_to,omitempty"`
	Tags    []resendTag       `json:"tags,omitempty"`
	Headers map[string]string `json:"headers,omitempty"`
}

type resendTag struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

func (p *resendProvider) Send(ctx context.Context, msg Message) error {
	from := msg.From
	if from == "" {
		from = p.from
	}

	tags := make([]resendTag, 0, len(msg.Tags))
	for k, v := range msg.Tags {
		tags = append(tags, resendTag{Name: k, Value: v})
	}

	body := resendRequest{
		From:    from,
		To:      []string{msg.To},
		Subject: msg.Subject,
		HTML:    msg.HTML,
		Text:    msg.Text,
		ReplyTo: msg.ReplyTo,
		Tags:    tags,
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("resend: encode body: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		"https://api.resend.com/emails", bytes.NewReader(raw))
	if err != nil {
		return fmt.Errorf("resend: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+p.apiKey)

	resp, err := p.client.Do(req)
	if err != nil {
		return fmt.Errorf("resend: http: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		// Read up to 4KB of the body to surface why. Resend returns a
		// JSON `{"name":"...","message":"..."}` shape on error; we
		// just bubble the raw text — the admin UI displays it verbatim.
		buf, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("resend: http %d: %s", resp.StatusCode, string(buf))
	}
	return nil
}
