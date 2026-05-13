//go:build !cloud
// +build !cloud

package main

import (
	"context"
	"log"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/storage"
	"github.com/imranp/kerf/backend/internal/tess"
)

func startTessWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	tess.RunWorker(ctx, pool, store)
	log.Printf("tess: placeholder worker started")
}

func startFEMWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	log.Printf("fem: worker not available in OSS build")
}

func startSIMWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	log.Printf("sim: worker not available in OSS build")
}