package main

import (
	"context"
	"encoding/json"
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
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
	"github.com/imranp/kerf/backend/internal/storage"
	"github.com/imranp/kerf/backend/internal/tools"
	"github.com/imranp/kerf/backend/internal/web"
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
	registry := llm.NewRegistry(llm.Config{
		AnthropicAPIKey: cfg.AnthropicAPIKey,
		OpenAIAPIKey:    cfg.OpenAIAPIKey,
		MoonshotAPIKey:  cfg.MoonshotAPIKey,
		GeminiAPIKey:    cfg.GeminiAPIKey,
		DefaultModel:    cfg.DefaultModel,
	})
	store, err := storage.New(cfg)
	if err != nil {
		log.Fatalf("storage: %v", err)
	}
	deps := &handlers.Deps{
		Cfg:     cfg,
		Pool:    pool,
		Auth:    authSvc,
		LLM:     registry,
		Storage: store,
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

	// /api/config — public bootstrap config consumed by the frontend's
	// useCloudConfig hook. Exposes only what the SPA needs to decide
	// which build flavor it's talking to (cloud vs OSS) and whether
	// to skip the login screen (local_mode).
	r.Get("/api/config", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"google_client_id": cfg.GoogleClientID,
			"cloud_enabled":    cfg.Cloud.Enabled,
			"local_mode":       cfg.LocalMode,
			"default_model":    cfg.DefaultModel,
		})
	})

	// /api/bootstrap — public read of the on-disk state.json (single-machine
	// brew/curl-install path). Always present; a multi-user deploy with no
	// state.json simply gets has_state=false.
	r.Get("/api/bootstrap", deps.Bootstrap)

	r.Route("/auth", func(r chi.Router) {
		r.Post("/register", deps.Register)
		r.Post("/login", deps.Login)
		r.Post("/refresh", deps.Refresh)
		r.Post("/logout", deps.Logout)
		r.Get("/google/start", deps.GoogleStart)
		r.Get("/google/callback", deps.GoogleCallback)
		// Local-mode-only: auto-account endpoint. Handler 404s on
		// cloud builds / local_mode=false so the cloud signup flow
		// can't be bypassed.
		r.Post("/bootstrap-local", deps.BootstrapLocal)
	})

	r.Route("/api", func(r chi.Router) {
		// Public share lookup (token-only auth handled inside).
		r.Group(func(r chi.Router) {
			r.Use(kmw.OptionalAuth(authSvc, pool))
			r.Get("/share/{token}", deps.LookupShare)
		})

		// Authenticated routes.
		r.Group(func(r chi.Router) {
			r.Use(kmw.RequireAuth(authSvc, pool))

			r.Get("/me", deps.Me)
			r.Patch("/me", deps.UpdateMe)
			r.Get("/models", deps.ListModels)
			r.Post("/share/{token}/accept", deps.AcceptShare)

			// API tokens (workspace-scoped).
			r.Post("/api-tokens", deps.CreateAPIToken)
			r.Get("/api-tokens", deps.ListAPITokens)
			r.Delete("/api-tokens/{token_id}", deps.RevokeAPIToken)

			// Authenticated blob serving for the local storage backend.
			r.Get("/blobs/*", deps.ServeBlob)

			// Workspaces.
			r.Route("/workspaces", func(r chi.Router) {
				r.Get("/", deps.ListWorkspaces)
				r.Post("/", deps.CreateWorkspace)
				r.Post("/accept", deps.AcceptWorkspaceInvite)
				r.Get("/avatar/{id}", deps.ServeWorkspaceAvatar)

				r.Route("/{slug}", func(r chi.Router) {
					r.Get("/", deps.GetWorkspace)
					r.Patch("/", deps.UpdateWorkspace)
					r.Delete("/", deps.DeleteWorkspace)

					r.Post("/avatar", deps.UploadWorkspaceAvatar)
					r.Delete("/avatar", deps.DeleteWorkspaceAvatar)

					r.Post("/members", deps.InviteWorkspaceMember)
					r.Patch("/members/{user_id}", deps.ChangeWorkspaceMemberRole)
					r.Delete("/members/{user_id}", deps.RemoveWorkspaceMember)
				})
			})

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
					r.Get("/files/{fid}/download", deps.DownloadFile)
					r.Post("/files/{fid}/tessellate", deps.Tessellate)
					r.Delete("/files/{fid}/tessellate", deps.PurgeTessellation)
					r.Post("/files/{fid}/fem", deps.RunFEM)
					r.Post("/files/{fid}/sim", deps.RunSim)
					r.Get("/files/{fid}/sim/status", deps.SimJobStatus)

					// Cross-project derived-artifact cache (ROADMAP row 67).
					r.Post("/files/{fid}/derived", deps.LookupDerivedArtifact)
					r.Post("/files/{fid}/derived/store", deps.StoreDerivedArtifact)
					r.Delete("/files/{fid}/derived", deps.PurgeDerivedArtifacts)

					// Assets (binary uploads — STEP files etc.)
					r.Post("/assets", deps.UploadAsset)

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

	// /v1/rpc — JSON-RPC 2.0 endpoint for kerf-sdk (Python package).
	// Accepts {"jsonrpc": "2.0", "method": "files.read", "params": {"project_id": "..."}, "id": 1}
	// and maps method names to the agent tool registry.
	r.Route("/v1", func(r chi.Router) {
		r.Use(kmw.RequireAuth(authSvc, pool))
		r.Post("/rpc", deps.HandleRPC)

		// /tools — tool registry for kerf-sdk consumers.
		// Returns the full tool list regardless of auth (SDKs filter per-token).
		r.Get("/tools", func(w http.ResponseWriter, r *http.Request) {
			specs := tools.Specs("editor")
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{"tools": specs})
		})
	})

	// SPA: serve the embedded Vite bundle at the root. Skipped when the
	// dist/ tree isn't populated (typical dev workflow uses `vite dev`
	// alongside, with the SPA at :5173 proxying /api/* to this server).
	if dist, ok := web.Sub(); ok {
		fileServer := http.FileServer(http.FS(dist))
		// Asset routes hit the file server directly; everything else
		// falls back to index.html so React Router can resolve the path.
		r.Handle("/assets/*", fileServer)
		r.Get("/favicon.ico", fileServer.ServeHTTP)
		r.Get("/apple-touch-icon.png", fileServer.ServeHTTP)
		r.Get("/manifest.webmanifest", fileServer.ServeHTTP)
		r.NotFound(func(w http.ResponseWriter, req *http.Request) {
			// API misses should 404 cleanly; SPA paths get index.html.
			if strings.HasPrefix(req.URL.Path, "/api/") || strings.HasPrefix(req.URL.Path, "/auth/") {
				http.NotFound(w, req)
				return
			}
			f, err := dist.Open("index.html")
			if err != nil {
				http.NotFound(w, req)
				return
			}
			defer f.Close()
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
			io.Copy(w, f)
		})
	}

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

	startTessWorker(ctx, cfg, pool, store)
	startFEMWorker(ctx, cfg, pool, store)
	startSIMWorker(ctx, cfg, pool, store)

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
