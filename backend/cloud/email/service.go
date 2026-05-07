//go:build cloud
// +build cloud

// Package email implements the transactional email subsystem for Kerf's
// hosted tier. The package is cloud-only: every file is gated by the
// `cloud` build tag and this code is never linked into OSS builds.
//
// Three pluggable providers ship out of the box:
//
//   - Resend  — preferred default, simplest HTTPS surface.
//   - SES     — AWS SES v2 via aws-sdk-go-v2/service/sesv2.
//   - SMTP    — stdlib net/smtp for self-hosted MTAs.
//
// Provider precedence is "first enabled in the precedence list," which
// is `resend → ses → smtp`. If multiple providers are configured and
// enabled, the higher-priority one is used and the others act as cold
// failover candidates that the operator could promote by disabling
// the active one. Failover-on-error is intentionally NOT implemented;
// retries hit the same provider with exponential backoff, and the
// operator's escalation path is the admin UI.
//
// All sends go through Mailer.SendTemplate, which:
//
//  1. inserts a `queued` row in cloud_email_log,
//  2. returns immediately,
//  3. lets a background goroutine drain the queue and dispatch via the
//     active provider,
//  4. retries failed rows up to 3 times with exponential backoff before
//     marking them `failed` permanently.
package email

import (
	"context"
	"errors"
)

// secretDomain is the per-purpose constant mixed into the AES-GCM key
// when encrypting/decrypting cloud_email_credentials.secret_encrypted.
// Changing this string invalidates every stored credential — the
// operator would need to re-enter every provider's API key/SMTP password.
const secretDomain = "cloud:email-credentials"

// providerOrder is the precedence list. The first provider in this slice
// that is both configured AND enabled is the one Mailer.send picks.
//
// The order is deliberate:
//   - Resend is the simplest to operate (one API key) so it sits first.
//   - SES is the cheapest/most-reliable for high volume but requires
//     AWS credentials and DNS setup; second.
//   - SMTP is last because it's the riskiest deliverability surface
//     (running your own MTA is rarely the right call) but the most
//     flexible escape hatch.
var providerOrder = []string{ProviderResend, ProviderSES, ProviderSMTP}

// Provider names. Constants used both as the DB row's `provider` value
// and as the dispatch key inside the registry.
const (
	ProviderResend = "resend"
	ProviderSES    = "ses"
	ProviderSMTP   = "smtp"
)

// Message is the provider-agnostic shape of a single outbound email.
// Templates render into this; providers consume it.
//
// Tags are passed through to providers that support them (Resend's
// `tags`, SES's `tags`, ignored by SMTP). Useful for downstream
// analytics / deliverability dashboards. Optional.
type Message struct {
	To      string
	From    string
	ReplyTo string
	Subject string
	HTML    string
	Text    string
	Tags    map[string]string
}

// Provider is the minimal surface a transport implements. Send is the
// only required method — the registry handles selection, the mailer
// handles queueing.
type Provider interface {
	Name() string
	Send(ctx context.Context, msg Message) error
}

// Credentials is the decrypted JSON blob stored per provider. Different
// providers use different subsets of these fields:
//
//   - resend: APIKey + FromEmail (FromName optional)
//   - ses:    APIKey (= IAM secret) + APIKeyID (in APIKey is fine if
//             stored as a single-string credential, but we encode both
//             via SMTPUsername/SMTPPassword to keep schema flat — the
//             SES provider reads them out of those fields when present;
//             alternatively the operator can rely on the default AWS
//             credential chain by leaving APIKey/SMTPPassword empty)
//             + Region + FromEmail
//   - smtp:   SMTPHost + SMTPPort + SMTPUsername + SMTPPassword + FromEmail
//
// FromName is shared and optional everywhere — when set, the From line
// is rendered as `"Name" <email>`.
type Credentials struct {
	APIKey       string `json:"api_key,omitempty"`
	FromEmail    string `json:"from_email,omitempty"`
	FromName     string `json:"from_name,omitempty"`
	Region       string `json:"region,omitempty"`
	SMTPHost     string `json:"smtp_host,omitempty"`
	SMTPPort     int    `json:"smtp_port,omitempty"`
	SMTPUsername string `json:"smtp_username,omitempty"`
	SMTPPassword string `json:"smtp_password,omitempty"`
}

// ErrNoProvider means no provider is configured AND enabled. Mailer
// returns it from SendTemplate's drain path; the row is marked failed.
var ErrNoProvider = errors.New("email: no provider configured")

// ErrInvalidCredentials is returned by buildProvider when the decoded
// Credentials JSON is missing required fields for the given provider.
var ErrInvalidCredentials = errors.New("email: invalid provider credentials")

// validateCredentials is called before encrypting + storing a row.
// Mirrored against the per-provider buildProvider; keeping validation
// here lets the admin handler surface a 400 instead of an opaque 500
// after the next reload.
func validateCredentials(provider string, c Credentials) error {
	if c.FromEmail == "" {
		return errors.New("from_email is required")
	}
	switch provider {
	case ProviderResend:
		if c.APIKey == "" {
			return errors.New("resend: api_key is required")
		}
	case ProviderSES:
		// AWS allows the default credential chain when APIKey is
		// empty (instance role, env vars, ~/.aws/credentials), so we
		// don't require it here. Region is required because the v2
		// SDK doesn't have a sane US-east-1 fallback for SES.
		if c.Region == "" {
			return errors.New("ses: region is required")
		}
	case ProviderSMTP:
		if c.SMTPHost == "" {
			return errors.New("smtp: smtp_host is required")
		}
		if c.SMTPPort == 0 {
			return errors.New("smtp: smtp_port is required")
		}
	default:
		return errors.New("email: unknown provider: " + provider)
	}
	return nil
}
