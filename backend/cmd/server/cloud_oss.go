//go:build !cloud
// +build !cloud

package main

import (
	"context"

	"github.com/go-chi/chi/v5"

	"github.com/imranp/kerf/backend/internal/handlers"
)

// registerCloud is the OSS-build no-op. The cloud build replaces this
// (see cloud_enabled.go) with real route mounting + service init —
// Paystack billing, FX refresher, quota middleware.
func registerCloud(_ context.Context, _ chi.Router, _ *handlers.Deps) {}
