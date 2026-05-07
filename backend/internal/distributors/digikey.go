package distributors

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// DigiKey integration. Uses the v3 Search API:
//
//   POST /v1/oauth2/token              (client_credentials grant)
//   POST /Search/v3/Products/Keyword   (search by keyword)
//   GET  /Search/v3/Products/{partNumber}
//
// We cache the OAuth access token in process for `expires_in - 60s` so
// the boot-time + first-request paths share one token. DigiKey's
// production/sandbox split is reflected in the host name; for v1 we
// hard-code production. Operators who need sandbox can override the
// `client_id` to a sandbox app and we'll add an explicit env knob if
// the demand materializes.

const (
	digikeyBase     = "https://api.digikey.com"
	digikeyTokenURL = digikeyBase + "/v1/oauth2/token"
	digikeySearch   = digikeyBase + "/Search/v3/Products/Keyword"
	digikeyProduct  = digikeyBase + "/Search/v3/Products/"
)

type digikeyService struct {
	client       *http.Client
	clientID     string
	clientSecret string

	mu         sync.Mutex
	token      string
	tokenExp   time.Time
	tokenError error
}

func newDigiKey(c *http.Client, creds Credentials) Service {
	return &digikeyService{
		client:       c,
		clientID:     creds.ClientID,
		clientSecret: creds.ClientSecret,
	}
}

func (d *digikeyService) Name() string { return ProviderDigiKey }

// token returns a cached OAuth token, refreshing if expired. Errors
// during refresh are sticky for ~30s — repeated calls don't hammer the
// upstream when the credentials are clearly invalid.
func (d *digikeyService) ensureToken(ctx context.Context) (string, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	now := time.Now()
	if d.token != "" && now.Before(d.tokenExp) {
		return d.token, nil
	}
	if d.tokenError != nil && now.Before(d.tokenExp) {
		return "", d.tokenError
	}
	form := url.Values{}
	form.Set("client_id", d.clientID)
	form.Set("client_secret", d.clientSecret)
	form.Set("grant_type", "client_credentials")
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, digikeyTokenURL,
		strings.NewReader(form.Encode()))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := d.client.Do(req)
	if err != nil {
		d.tokenError = fmt.Errorf("digikey token request: %w", err)
		d.tokenExp = now.Add(30 * time.Second)
		return "", d.tokenError
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		d.tokenError = fmt.Errorf("digikey token: status %d: %s", resp.StatusCode, truncate(string(body), 200))
		d.tokenExp = now.Add(30 * time.Second)
		return "", d.tokenError
	}
	var tr struct {
		AccessToken string `json:"access_token"`
		ExpiresIn   int    `json:"expires_in"`
		TokenType   string `json:"token_type"`
	}
	if err := json.Unmarshal(body, &tr); err != nil {
		d.tokenError = fmt.Errorf("digikey token decode: %w", err)
		d.tokenExp = now.Add(30 * time.Second)
		return "", d.tokenError
	}
	if tr.AccessToken == "" {
		d.tokenError = errors.New("digikey token: empty access_token")
		d.tokenExp = now.Add(30 * time.Second)
		return "", d.tokenError
	}
	exp := tr.ExpiresIn
	if exp <= 60 {
		exp = 600
	}
	d.token = tr.AccessToken
	d.tokenExp = now.Add(time.Duration(exp-60) * time.Second)
	d.tokenError = nil
	return d.token, nil
}

// Lookup hits the keyword endpoint with the SKU because the
// /Products/{partNumber} variant is fussy about exact matches and
// returns 404s on perfectly valid digi-key part numbers when
// formatting differs (-ND vs -CT-ND etc.).
func (d *digikeyService) Lookup(ctx context.Context, sku string) (*DistributorPart, error) {
	if sku == "" {
		return nil, ErrNotFound
	}
	parts, err := d.searchInternal(ctx, sku, 1)
	if err != nil {
		return nil, err
	}
	if len(parts) == 0 {
		return nil, ErrNotFound
	}
	return parts[0], nil
}

func (d *digikeyService) Search(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	if query == "" {
		return nil, errors.New("digikey search: empty query")
	}
	if limit <= 0 || limit > 25 {
		limit = 10
	}
	return d.searchInternal(ctx, query, limit)
}

// searchInternal posts the v3 Search/Keyword body and parses the
// trimmed-down response shape we care about.
func (d *digikeyService) searchInternal(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	tok, err := d.ensureToken(ctx)
	if err != nil {
		return nil, err
	}
	body := map[string]any{
		"Keywords":     query,
		"RecordCount":  limit,
		"RecordStartPosition": 0,
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, digikeySearch, bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+tok)
	req.Header.Set("X-DIGIKEY-Client-Id", d.clientID)
	// Locale headers — v3 requires these; default to US/USD/en. We
	// could expose these as config knobs once a customer asks.
	req.Header.Set("X-DIGIKEY-Locale-Site", "US")
	req.Header.Set("X-DIGIKEY-Locale-Language", "en")
	req.Header.Set("X-DIGIKEY-Locale-Currency", "USD")
	resp, err := d.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("digikey search: %w", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		// Token might be stale; force refresh on next call.
		d.mu.Lock()
		d.token = ""
		d.tokenExp = time.Time{}
		d.mu.Unlock()
		return nil, fmt.Errorf("digikey search: %d (token may be stale)", resp.StatusCode)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("digikey search: status %d: %s", resp.StatusCode, truncate(string(respBody), 200))
	}

	var sr digikeySearchResp
	if err := json.Unmarshal(respBody, &sr); err != nil {
		return nil, fmt.Errorf("digikey search decode: %w", err)
	}
	out := make([]*DistributorPart, 0, len(sr.Products))
	for i := range sr.Products {
		p := &sr.Products[i]
		var price *float64
		if p.UnitPrice > 0 {
			v := p.UnitPrice
			price = &v
		}
		var stock *int
		if p.QuantityAvailable >= 0 {
			s := p.QuantityAvailable
			stock = &s
		}
		out = append(out, &DistributorPart{
			Name:      ProviderDigiKey,
			SKU:       p.DigiKeyPartNumber,
			URL:       p.ProductURL,
			PriceUSD:  price,
			Stock:     stock,
			FetchedAt: time.Now().UTC(),
		})
	}
	return out, nil
}

// digikeySearchResp is the trimmed response we care about. The full
// payload is huge; we keep just the fields the BOM uses.
type digikeySearchResp struct {
	Products []struct {
		DigiKeyPartNumber string  `json:"DigiKeyPartNumber"`
		ProductURL        string  `json:"ProductUrl"`
		UnitPrice         float64 `json:"UnitPrice"`
		QuantityAvailable int     `json:"QuantityAvailable"`
	} `json:"Products"`
}

// truncate caps a debug string at n runes to keep error messages from
// dragging an entire HTML 500 page into the logs.
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}
