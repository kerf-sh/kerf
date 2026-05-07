package distributors

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// LCSC integration. The "official" LCSC API is gated behind a partner
// program; the public surface most operators use is JLCPCB's
// EasyEDA-flavoured search at https://wmsc.lcsc.com/wmsc/. For v1 we
// hit the public search endpoint and accept that LCSC will rate-limit
// us aggressively (the configurable rate_limit_per_minute is the right
// knob here).
//
// Pricing is returned in CNY. We convert to USD via the cloud FX
// fetcher when available (see Registry.fxConvert); when FX is missing
// (OSS build, or before the daily refresh has run), we leave PriceUSD
// nil and stash the raw CNY price in Raw.

const lcscBase = "https://wmsc.lcsc.com/wmsc"

type lcscService struct {
	client *http.Client
	apiKey string
	fx     FXConverter
}

func newLCSC(c *http.Client, creds Credentials, fx FXConverter) Service {
	return &lcscService{client: c, apiKey: creds.APIKey, fx: fx}
}

func (l *lcscService) Name() string { return ProviderLCSC }

func (l *lcscService) Lookup(ctx context.Context, sku string) (*DistributorPart, error) {
	if sku == "" {
		return nil, ErrNotFound
	}
	parts, err := l.search(ctx, sku, 1)
	if err != nil {
		return nil, err
	}
	if len(parts) == 0 {
		return nil, ErrNotFound
	}
	return parts[0], nil
}

func (l *lcscService) Search(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	if query == "" {
		return nil, errors.New("lcsc search: empty query")
	}
	if limit <= 0 || limit > 25 {
		limit = 10
	}
	return l.search(ctx, query, limit)
}

// search hits the keyword endpoint. The response shape varies between
// "search by keyword" and "search by part number" but the fields we
// care about (productCode, productPriceList, productUrl, stockNumber)
// are common.
func (l *lcscService) search(ctx context.Context, query string, limit int) ([]*DistributorPart, error) {
	u, _ := url.Parse(lcscBase + "/search/global")
	q := u.Query()
	q.Set("keyword", query)
	q.Set("currentPage", "1")
	q.Set("pageSize", strconv.Itoa(limit))
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if l.apiKey != "" {
		req.Header.Set("X-LCSC-API-Key", l.apiKey)
	}
	resp, err := l.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("lcsc request: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("lcsc: status %d: %s", resp.StatusCode, truncate(string(body), 200))
	}
	var sr lcscSearchResp
	if err := json.Unmarshal(body, &sr); err != nil {
		return nil, fmt.Errorf("lcsc decode: %w", err)
	}
	products := sr.Result.ProductList
	out := make([]*DistributorPart, 0, len(products))
	for i := range products {
		p := &products[i]
		var priceCNY float64
		for _, pb := range p.ProductPriceList {
			if pb.LadderLevel == 1 {
				priceCNY = pb.ProductPrice
				break
			}
		}
		if priceCNY == 0 && len(p.ProductPriceList) > 0 {
			priceCNY = p.ProductPriceList[0].ProductPrice
		}
		dp := &DistributorPart{
			Name:      ProviderLCSC,
			SKU:       p.ProductCode,
			URL:       p.ProductURL,
			FetchedAt: time.Now().UTC(),
		}
		if p.StockNumber > 0 {
			s := p.StockNumber
			dp.Stock = &s
		}
		// FX conversion: CNY → USD when available.
		if priceCNY > 0 && l.fx != nil {
			if usd, ok := l.fx.Convert(priceCNY, "CNY", "USD"); ok && usd > 0 {
				dp.PriceUSD = &usd
			}
		}
		// Always stash the raw CNY price for callers that want to surface it.
		if priceCNY > 0 {
			rawJSON, _ := json.Marshal(map[string]any{
				"price_cny": priceCNY,
				"product":   p.ProductCode,
			})
			dp.Raw = rawJSON
		}
		out = append(out, dp)
	}
	return out, nil
}

type lcscPriceBreak struct {
	LadderLevel  int     `json:"ladderLevel"`
	ProductPrice float64 `json:"productPrice"`
}

type lcscProduct struct {
	ProductCode      string           `json:"productCode"`
	ProductURL       string           `json:"productUrl"`
	StockNumber      int              `json:"stockNumber"`
	ProductPriceList []lcscPriceBreak `json:"productPriceList"`
}

type lcscSearchResp struct {
	Code   int `json:"code"`
	Result struct {
		ProductList []lcscProduct `json:"productList"`
	} `json:"result"`
}
