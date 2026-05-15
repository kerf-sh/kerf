// Package kerf is the Go SDK for Kerf (https://kerf.app).
//
// Quickstart:
//
//	k, err := kerf.FromEnv()
//	if err != nil {
//	    log.Fatal(err)
//	}
//	files, err := k.Files.List(ctx, "proj_123")
//
// Auth: set KERF_API_TOKEN (and optionally KERF_API_URL) in your environment,
// or pass values explicitly to New().
package kerf

import (
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/kerf-sh/kerf-sdk-go/configurations"
	"github.com/kerf-sh/kerf-sdk-go/docs"
	"github.com/kerf-sh/kerf-sdk-go/equations"
	"github.com/kerf-sh/kerf-sdk-go/files"
	"github.com/kerf-sh/kerf-sdk-go/revisions"
)

const defaultAPIURL = "https://kerf.app"

// Client is the top-level Kerf SDK client.
// Construct with New or FromEnv; then use the sub-package clients directly.
type Client struct {
	hc *httpClient

	// Files provides operations on project files.
	Files *files.Client
	// Equations provides read/write access to equation variables.
	Equations *equations.Client
	// Configurations provides listing and activation of named configurations.
	Configurations *configurations.Client
	// Revisions provides history browsing and restoration.
	Revisions *revisions.Client
	// Docs provides full-text search across the Kerf documentation.
	Docs *docs.Client
}

// New constructs a Client with an explicit API URL and token.
// apiURL defaults to "https://kerf.app" when empty.
func New(apiURL, apiToken string) *Client {
	if apiURL == "" {
		apiURL = defaultAPIURL
	}
	apiURL = strings.TrimRight(apiURL, "/")

	transport := &http.Client{Timeout: 30 * time.Second}
	hc := &httpClient{
		client:   transport,
		apiURL:   apiURL,
		apiToken: apiToken,
	}

	return &Client{
		hc:             hc,
		Files:          files.NewClient(hc),
		Equations:      equations.NewClient(hc),
		Configurations: configurations.NewClient(hc),
		Revisions:      revisions.NewClient(hc),
		Docs:           docs.NewClient(hc),
	}
}

// FromEnv constructs a Client from the KERF_API_TOKEN and (optionally)
// KERF_API_URL environment variables.
// Returns an error wrapping ErrMissingEnv when KERF_API_TOKEN is unset.
func FromEnv() (*Client, error) {
	token := strings.TrimSpace(os.Getenv("KERF_API_TOKEN"))
	if token == "" {
		return nil, fmt.Errorf("%w: KERF_API_TOKEN", ErrMissingEnv)
	}
	apiURL := strings.TrimSpace(os.Getenv("KERF_API_URL"))
	if apiURL == "" {
		apiURL = defaultAPIURL
	}
	return New(apiURL, token), nil
}

// Caller is the interface implemented by *httpClient and consumed by sub-packages.
// It is exported via the internal bridge so sub-packages can be typed without
// importing the root package (avoiding import cycles).
//
// Sub-packages receive a Caller at construction; the root package passes its
// *httpClient which satisfies the interface.
var _ interface {
	files.Caller
	equations.Caller
	configurations.Caller
	revisions.Caller
	docs.Caller
} = (*httpClient)(nil)

// errorsIs verifies that errors.Is works against ErrMissingEnv.
// This is a compile-time check only; no runtime cost.
var _ = func() bool { return errors.Is(ErrMissingEnv, ErrMissingEnv) }
