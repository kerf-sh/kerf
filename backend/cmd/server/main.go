package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	"github.com/imranp/kerf/backend/internal/handlers"
	"github.com/imranp/kerf/backend/internal/llm"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
)

func main() {
	envFlag := flag.String("env", "local", "environment (local|dev|main)")
	flag.Parse()

	cfg, err := config.Load(*envFlag)
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	ctx := context.Background()
	pool, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db: %v", err)
	}
	defer pool.Close()

	authSvc := auth.New(cfg, pool)
	llmClient := llm.New(cfg.AnthropicAPIKey, cfg.AnthropicModel)
	deps := &handlers.Deps{
		Cfg:  cfg,
		Pool: pool,
		Auth: authSvc,
		LLM:  llmClient,
	}

	r := chi.NewRouter()
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(chimw.Logger)
	r.Use(chimw.Recoverer)
	r.Use(chimw.Timeout(60 * time.Second))
	r.Use(kmw.CORS(cfg.CORSOrigin))

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "env": cfg.Env})
	})

	r.Route("/auth", func(r chi.Router) {
		r.Post("/register", deps.Register)
		r.Post("/login", deps.Login)
		r.Post("/refresh", deps.Refresh)
		r.Post("/logout", deps.Logout)
		r.Get("/google/start", deps.GoogleStart)
		r.Get("/google/callback", deps.GoogleCallback)
	})

	r.Route("/api", func(r chi.Router) {
		// Public share lookup (token-only auth handled inside).
		r.Group(func(r chi.Router) {
			r.Use(kmw.OptionalAuth(authSvc))
			r.Get("/share/{token}", deps.LookupShare)
		})

		// Authenticated routes.
		r.Group(func(r chi.Router) {
			r.Use(kmw.RequireAuth(authSvc))

			r.Get("/me", deps.Me)
			r.Post("/share/{token}/accept", deps.AcceptShare)

			r.Route("/projects", func(r chi.Router) {
				r.Get("/", deps.ListProjects)
				r.Post("/", deps.CreateProject)

				r.Route("/{pid}", func(r chi.Router) {
					r.Get("/", deps.GetProject)
					r.Patch("/", deps.UpdateProject)
					r.Delete("/", deps.DeleteProject)

					// Files
					r.Get("/files", deps.ListFiles)
					r.Post("/files", deps.CreateFile)
					r.Get("/files/{fid}", deps.GetFile)
					r.Patch("/files/{fid}", deps.UpdateFile)
					r.Delete("/files/{fid}", deps.DeleteFile)

					// Threads
					r.Get("/threads", deps.ListThreads)
					r.Post("/threads", deps.CreateThread)
					r.Patch("/threads/{tid}", deps.UpdateThread)
					r.Delete("/threads/{tid}", deps.DeleteThread)

					// Messages
					r.Get("/threads/{tid}/messages", deps.ListMessages)
					r.Post("/threads/{tid}/messages", deps.PostMessage)

					// Sharing
					r.Post("/share/links", deps.CreateShareLink)
					r.Get("/share/links", deps.ListShareLinks)
					r.Delete("/share/links/{lid}", deps.DeleteShareLink)

					// Members
					r.Get("/members", deps.ListMembers)
					r.Post("/members", deps.AddMember)
					r.Patch("/members/{uid}", deps.UpdateMember)
					r.Delete("/members/{uid}", deps.RemoveMember)
				})
			})
		})
	})

	srv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           r,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("kerf backend listening on :%s (env=%s)", cfg.Port, cfg.Env)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop
	log.Printf("shutting down")

	shutCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutCtx); err != nil {
		log.Printf("shutdown: %v", err)
	}
}
