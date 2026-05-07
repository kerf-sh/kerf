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
	"strconv"
	"strings"
	"time"
)

// Mouser integration. Uses Mouser Search API v1:
//
//   POST /api/v1/search/partnumber?apiKey=...   (exact-MPN lookup)
//   POST /api/v1/search/keyword?apiKey=...      (free-text)
//
// API key goes in the URL (no OAuth flow — simpler than DigiKey).
// Pricing is returned in the locale's currency; for the default
// US-account we pull USD. Mouser quotes prices as a `PriceBreaks`
// list of {Quantity, Price}; we take the unit price at qty 1 as the
// single value we surface.

const mouserBase = "https://api.mouser.com"

type mouserService struct {
	client *http.Client
	apiKey string
}

func newMouser(c *http.Client, creds Credentials) Service {
	return &mouserService{client: c, apiKey: creds.APIKey}
}

func (m *mouserService) Name() string { return ProviderMouser }

func (m *mouserService) Lookup(ctx context.Context, sku string) (*DistributorPart, error) {
	if sku == "" {
		return nil, ErrNotFound
	}
	body := map[string]any{
		"SearchByPartRequest": map[string]any{
			"mouserPartNumber": sku,
		},
	}
	parts, err := m.post(ctx, "/api/v1/search/partnumber", body, 1)
	if err != nil {
		return nil, err
	}
	if len(parts) == 0 {
		return nil, ErrNotFound
	}
	return parts[0], nil
}

func (m *mouserService) Search(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	if query == "" {
		return nil, errors.New("mouser search: empty query")
	}
	if limit <= 0 || limit > 50 {
		limit = 10
	}
	body := map[string]any{
		"SearchByKeywordRequest": map[string]any{
			"keyword":        query,
			"records":        limit,
			"startingRecord": 0,
		},
	}
	return m.post(ctx, "/api/v1/search/keyword", body, limit)
}

// post is the shared mouser request path.
func (m *mouserService) post(ctx context.Context, path string, body any, limit int) ([]*DistributorPart, error) {
	if m.apiKey == "" {
		return nil, errors.New("mouser: missing api key")
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	u, _ := url.Parse(mouserBase + path)
	q := u.Query()
	q.Set("apiKey", m.apiKey)
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := m.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("mouser request: %w", err)
	}
	defer resp.Body.Close()
	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("mouser %s: status %d: %s", path, resp.StatusCode, truncate(string(respBody), 200))
	}

	var sr mouserSearchResp
	if err := json.Unmarshal(respBody, &sr); err != nil {
		return nil, fmt.Errorf("mouser decode: %w", err)
	}
	if sr.Errors != nil && len(*sr.Errors) > 0 {
		// Mouser returns 200 even when the credentials are bad — surface
		// the inline error so it doesn't silently look like "no match."
		first := (*sr.Errors)[0]
		return nil, fmt.Errorf("mouser error: %s %s", first.Code, first.Message)
	}
	out := make([]*DistributorPart, 0, limit)
	parts := sr.SearchResults.Parts
	for i := range parts {
		p := &parts[i]
		price, _ := parseMouserPrice(p.PriceBreaks)
		var priceUSD *float64
		if price > 0 {
			v := price
			priceUSD = &v
		}
		var stock *int
		if n, err := strconv.Atoi(p.Availability); err == nil {
			s := n
			stock = &s
		}
		out = append(out, &DistributorPart{
			Name:      ProviderMouser,
			SKU:       p.MouserPartNumber,
			URL:       p.ProductDetailURL,
			PriceUSD:  priceUSD,
			Stock:     stock,
			FetchedAt: time.Now().UTC(),
		})
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

// parseMouserPrice picks the qty-1 price from the PriceBreaks list. The
// returned currency is whatever Mouser returns (USD for US accounts);
// we trust the operator to configure a USD-locale account.
func parseMouserPrice(breaks []mouserPriceBreak) (float64, string) {
	for _, b := range breaks {
		// Format: "$0.014" or "0.014 EUR" depending on locale.
		s := strings.TrimSpace(b.Price)
		s = strings.TrimPrefix(s, "$")
		s = strings.ReplaceAll(s, ",", "")
		// Drop trailing currency code (e.g. "0.014 EUR")
		if sp := strings.Index(s, " "); sp > 0 {
			s = s[:sp]
		}
		v, err := strconv.ParseFloat(s, 64)
		if err == nil && v > 0 {
			return v, b.Currency
		}
	}
	return 0, ""
}

type mouserPriceBreak struct {
	Quantity int    `json:"Quantity"`
	Price    string `json:"Price"`
	Currency string `json:"Currency"`
}

type mouserSearchResp struct {
	Errors        *[]mouserError `json:"Errors,omitempty"`
	SearchResults struct {
		NumberOfResult int          `json:"NumberOfResult"`
		Parts          []mouserPart `json:"Parts"`
	} `json:"SearchResults"`
}

type mouserError struct {
	Code    string `json:"Code"`
	Message string `json:"Message"`
}

type mouserPart struct {
	MouserPartNumber string             `json:"MouserPartNumber"`
	ProductDetailURL string             `json:"ProductDetailUrl"`
	Availability     string             `json:"Availability"`
	PriceBreaks      []mouserPriceBreak `json:"PriceBreaks"`
}
