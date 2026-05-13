//go:build cloud
// +build cloud

package main

import (
	"context"
	"log"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/fem"
	"github.com/imranp/kerf/backend/internal/sim"
	"github.com/imranp/kerf/backend/internal/storage"
	"github.com/imranp/kerf/backend/internal/tessellate"
)

func startTessWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	tessellate.New(cfg, pool, store).Run(ctx)
	log.Printf("tessellate: cloud worker pool started")
}

func startFEMWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	fem.New(cfg, pool, store).Run(ctx)
	log.Printf("fem: cloud worker pool started")
}

func startSIMWorker(ctx context.Context, cfg *config.Config, pool *pgxpool.Pool, store storage.Storage) {
	sim.New(cfg, pool, store).Run(ctx)
	log.Printf("sim: cloud worker pool started")
}