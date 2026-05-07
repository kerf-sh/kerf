//go:build cloud
// +build cloud

package email

import (
	"bytes"
	"errors"
	"fmt"
	"mime/quotedprintable"
	"net/smtp"
	"strconv"
	"strings"
	"context"
	"crypto/rand"
	"encoding/hex"
	"time"
)

// smtpProvider posts to a self-hosted MTA via stdlib net/smtp. Auth is
// PLAIN over TLS-wrapped connection (most modern relays — sendgrid,
// mailgun, postmark — accept this; if you're running your own MTA you
// already know what to do).
//
// Why include this at all? Operators who want to keep the email path
// inside their own perimeter (regulated environments, audit-heavy
// industries) won't accept a third-party SaaS in the loop. SMTP is the
// fallback for that case.
type smtpProvider struct {
	host string
	port int
	user string
	pass string
	from string
}

func newSMTP(creds Credentials) (*smtpProvider, error) {
	if creds.SMTPHost == "" || creds.SMTPPort == 0 {
		return nil, fmt.Errorf("%w: smtp host+port required", ErrInvalidCredentials)
	}
	if creds.FromEmail == "" {
		return nil, fmt.Errorf("%w: smtp from_email required", ErrInvalidCredentials)
	}
	from := creds.FromEmail
	if creds.FromName != "" {
		from = fmt.Sprintf("%s <%s>", creds.FromName, creds.FromEmail)
	}
	return &smtpProvider{
		host: creds.SMTPHost,
		port: creds.SMTPPort,
		user: creds.SMTPUsername,
		pass: creds.SMTPPassword,
		from: from,
	}, nil
}

func (p *smtpProvider) Name() string { return ProviderSMTP }

// Send composes a multipart/alternative message (text + html) and posts
// it via smtp.SendMail. ctx is used for a timeout — net/smtp doesn't
// take a context directly so we run the send in a goroutine and wait.
func (p *smtpProvider) Send(ctx context.Context, msg Message) error {
	from := msg.From
	if from == "" {
		from = p.from
	}
	if msg.To == "" {
		return errors.New("smtp: empty recipient")
	}

	body, err := buildMimeMessage(from, msg)
	if err != nil {
		return fmt.Errorf("smtp: encode body: %w", err)
	}

	addr := p.host + ":" + strconv.Itoa(p.port)
	var auth smtp.Auth
	if p.user != "" {
		auth = smtp.PlainAuth("", p.user, p.pass, p.host)
	}

	// Run the synchronous SendMail under the caller's ctx by ferrying
	// the result through a channel. If the deadline fires, the
	// underlying TCP connection will eventually close (tied to OS
	// keepalive); we don't fight that — just unblock the caller.
	done := make(chan error, 1)
	go func() {
		done <- smtp.SendMail(addr, auth, p.fromAddr(from), []string{msg.To}, body)
	}()
	select {
	case err := <-done:
		if err != nil {
			return fmt.Errorf("smtp: send: %w", err)
		}
		return nil
	case <-ctx.Done():
		return fmt.Errorf("smtp: %w", ctx.Err())
	}
}

// fromAddr extracts the bare email from a `"Name" <email>` header value
// for use as the SMTP envelope sender.
func (p *smtpProvider) fromAddr(from string) string {
	if i := strings.LastIndex(from, "<"); i >= 0 {
		if j := strings.Index(from[i:], ">"); j > 0 {
			return strings.TrimSpace(from[i+1 : i+j])
		}
	}
	return strings.TrimSpace(from)
}

// buildMimeMessage produces a multipart/alternative MIME blob with both
// the text and html parts. quoted-printable encoded so 8-bit chars in
// the body don't get mangled by relays.
func buildMimeMessage(from string, msg Message) ([]byte, error) {
	var b bytes.Buffer
	boundary := "kerf-" + randomBoundary()

	fmt.Fprintf(&b, "From: %s\r\n", from)
	fmt.Fprintf(&b, "To: %s\r\n", msg.To)
	if msg.ReplyTo != "" {
		fmt.Fprintf(&b, "Reply-To: %s\r\n", msg.ReplyTo)
	}
	fmt.Fprintf(&b, "Subject: %s\r\n", msg.Subject)
	fmt.Fprintf(&b, "Date: %s\r\n", time.Now().UTC().Format(time.RFC1123Z))
	fmt.Fprintf(&b, "MIME-Version: 1.0\r\n")
	fmt.Fprintf(&b, "Content-Type: multipart/alternative; boundary=%q\r\n", boundary)
	fmt.Fprintf(&b, "\r\n")

	// Plain text part (always included; if Text empty, derive from
	// HTML by stripping tags via a tiny crude pass — acceptable for
	// transactional templates that already ship with both halves).
	textBody := msg.Text
	if textBody == "" {
		textBody = stripTags(msg.HTML)
	}
	fmt.Fprintf(&b, "--%s\r\n", boundary)
	fmt.Fprintf(&b, "Content-Type: text/plain; charset=UTF-8\r\n")
	fmt.Fprintf(&b, "Content-Transfer-Encoding: quoted-printable\r\n\r\n")
	if err := writeQP(&b, textBody); err != nil {
		return nil, err
	}
	fmt.Fprintf(&b, "\r\n")

	// HTML part. Skipped if no HTML supplied.
	if msg.HTML != "" {
		fmt.Fprintf(&b, "--%s\r\n", boundary)
		fmt.Fprintf(&b, "Content-Type: text/html; charset=UTF-8\r\n")
		fmt.Fprintf(&b, "Content-Transfer-Encoding: quoted-printable\r\n\r\n")
		if err := writeQP(&b, msg.HTML); err != nil {
			return nil, err
		}
		fmt.Fprintf(&b, "\r\n")
	}

	fmt.Fprintf(&b, "--%s--\r\n", boundary)
	return b.Bytes(), nil
}

func writeQP(w *bytes.Buffer, s string) error {
	enc := quotedprintable.NewWriter(w)
	if _, err := enc.Write([]byte(s)); err != nil {
		return err
	}
	return enc.Close()
}

// stripTags is a deliberately tiny tag stripper so the SMTP path always
// has *something* in the text/plain leg even when the caller only
// supplied HTML. It is NOT a sanitizer — we trust our own templates.
func stripTags(html string) string {
	var b strings.Builder
	in := false
	for _, r := range html {
		switch r {
		case '<':
			in = true
		case '>':
			in = false
		default:
			if !in {
				b.WriteRune(r)
			}
		}
	}
	return b.String()
}

func randomBoundary() string {
	var buf [8]byte
	_, _ = rand.Read(buf[:])
	return hex.EncodeToString(buf[:])
}
