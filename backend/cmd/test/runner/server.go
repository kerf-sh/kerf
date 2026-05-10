package runner

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/imranp/kerf/backend/internal/auth"
	"github.com/imranp/kerf/backend/internal/config"
	"github.com/imranp/kerf/backend/internal/db"
	"github.com/imranp/kerf/backend/internal/filesystem"
	"github.com/imranp/kerf/backend/internal/handlers"
	"github.com/imranp/kerf/backend/internal/llm"
	kmw "github.com/imranp/kerf/backend/internal/middleware"
	"github.com/imranp/kerf/backend/internal/storage"
)

// Env bundles the live test server, its pgx pool, and a configured client.
// Scenarios pull whatever they need off this struct.
type Env struct {
	Server *httptest.Server
	Pool   *pgxpool.Pool
	Cfg    *config.Config
	Auth   *auth.Service
	Mirror *filesystem.Mirror
	Client *Client
	// MigrationsDir is recorded so scenarios can ResetSchema() if they need
	// extra isolation mid-scenario.
	MigrationsDir string
	// FilesystemRoot is the on-disk root used when StorageBackend ==
	// "filesystem". Empty otherwise.
	FilesystemRoot string
}

// Cleanup tears the env down: closes the http server, the pool, and (if
// requested) drops the schema.
func (e *Env) Cleanup(ctx context.Context, dropSchema bool) {
	if e.Server != nil {
		e.Server.Close()
	}
	if dropSchema && e.Pool != nil {
		_ = DropSchema(ctx, e.Pool)
	}
	if e.Pool != nil {
		e.Pool.Close()
	}
	if e.FilesystemRoot != "" {
		_ = os.RemoveAll(e.FilesystemRoot)
	}
}

// BootOptions tweaks server behavior per-scenario.
type BootOptions struct {
	JWTAccessTTL      time.Duration
	JWTRefreshTTL     time.Duration
	StorageBackend    string // "local" | "filesystem"
	FilesystemRoot    string // when blank, a tempdir is used in filesystem mode
	UsageEnabled      bool
	FileRevisionsMax  int
	MaxThreadsPerProj int
	// SystemUserEmail/Password populate the [system_user] block so the
	// auto-bootstrap path (auth.EnsureSystemUser) runs in scenarios that
	// want to exercise it. Empty values skip the bootstrap.
	SystemUserEmail    string
	SystemUserPassword string
	SystemUserName     string
	// StatePath, if non-empty, sets KERF_STATE_PATH for the duration of
	// Boot so the bootstrap state.json lands under the test's tempdir.
	StatePath string
	// LocalMode is a tri-state pointer. nil → leave the config default
	// (true under OSS), &true → force local_mode on, &false → force
	// it off. Lets the local_mode scenario flip the flag explicitly
	// while leaving every other scenario unchanged.
	LocalMode *bool
}

// DatabaseURL returns the test DB URL: env override or the documented default.
func DatabaseURL() string {
	if v := os.Getenv("KERF_TEST_DATABASE_URL"); v != "" {
		return v
	}
	return "postgres://postgres:postgres@localhost:5432/kerf_test?sslmode=disable"
}

// Boot starts a fresh in-process server. Migrations are applied (or
// re-applied — the schema is reset first) so the scenario sees an empty DB.
//
// Caller MUST invoke Env.Cleanup when done.
func Boot(ctx context.Context, opts BootOptions) (*Env, error) {
	migDir, err := FindMigrationsDir()
	if err != nil {
		return nil, err
	}

	pool, err := db.Connect(ctx, DatabaseURL())
	if err != nil {
		return nil, fmt.Errorf("db.Connect: %w\nhint: ensure the test DB exists. Run:\n  createdb kerf_test\n  (or set KERF_TEST_DATABASE_URL to point at an existing DB)", err)
	}

	if err := ResetSchema(ctx, pool, migDir); err != nil {
		pool.Close()
		return nil, fmt.Errorf("reset schema: %w", err)
	}

	cfg := buildConfig(opts)

	authSvc := auth.New(cfg, pool)

	if opts.StatePath != "" {
		_ = os.Setenv("KERF_STATE_PATH", opts.StatePath)
	}
	if cfg.SystemUserPassword != "" && cfg.SystemUserEmail != "" {
		if _, err := auth.EnsureSystemUser(ctx, cfg, pool, authSvc); err != nil {
			pool.Close()
			return nil, fmt.Errorf("ensure system user: %w", err)
		}
	}
	registry := llm.NewRegistry(llm.Config{DefaultModel: cfg.DefaultModel})

	// storage.New only supports "s3" | "local" — for filesystem mode we still
	// need a blob store for asset uploads, so we point storage.New at "local"
	// regardless. The Mirror handles source-file mirroring separately.
	storeCfg := *cfg
	if storeCfg.StorageBackend == "filesystem" {
		storeCfg.StorageBackend = "local"
	}
	store, err := storage.New(&storeCfg)
	if err != nil {
		pool.Close()
		return nil, fmt.Errorf("storage.New: %w", err)
	}

	var mirror *filesystem.Mirror
	fsRoot := ""
	if cfg.StorageBackend == "filesystem" {
		mirror, err = filesystem.New(cfg.FilesystemRoot)
		if err != nil {
			pool.Close()
			return nil, fmt.Errorf("filesystem.New: %w", err)
		}
		fsRoot = mirror.Root()
	}

	deps := &handlers.Deps{
		Cfg:     cfg,
		Pool:    pool,
		Auth:    authSvc,
		LLM:     registry,
		Storage: store,
		Mirror:  mirror,
	}

	r := buildRouter(cfg, authSvc, deps)
	srv := httptest.NewServer(r)

	env := &Env{
		Server:         srv,
		Pool:           pool,
		Cfg:            cfg,
		Auth:           authSvc,
		Mirror:         mirror,
		MigrationsDir:  migDir,
		FilesystemRoot: fsRoot,
	}
	env.Client = NewClient(srv.URL)
	return env, nil
}

// buildConfig produces a runtime config that matches what the production
// server expects, but populated entirely in code (no kerf.toml).
func buildConfig(opts BootOptions) *config.Config {
	cfg := config.Defaults()
	cfg.DatabaseURL = DatabaseURL()
	cfg.Env = "test"
	cfg.Port = "0"
	cfg.CORSOrigin = "http://localhost:5173"
	cfg.JWTSecret = "kerf-test-jwt-secret-please-do-not-use-in-prod"
	cfg.PasswordPepper = "kerf-test-pepper"
	if opts.JWTAccessTTL > 0 {
		cfg.JWTAccessTTL = opts.JWTAccessTTL
	} else {
		cfg.JWTAccessTTL = 15 * time.Minute
	}
	if opts.JWTRefreshTTL > 0 {
		cfg.JWTRefreshTTL = opts.JWTRefreshTTL
	} else {
		cfg.JWTRefreshTTL = 720 * time.Hour
	}

	cfg.UsageEnabled = opts.UsageEnabled
	if opts.FileRevisionsMax > 0 {
		cfg.FileRevisionsMax = opts.FileRevisionsMax
	}
	if opts.MaxThreadsPerProj > 0 {
		cfg.MaxThreadsPerProject = opts.MaxThreadsPerProj
	}

	switch opts.StorageBackend {
	case "filesystem":
		cfg.StorageBackend = "filesystem"
		root := opts.FilesystemRoot
		if root == "" {
			tmp, err := os.MkdirTemp("", "kerf-test-fs-*")
			if err == nil {
				root = tmp
			} else {
				root = filepath.Join(os.TempDir(), "kerf-test-fs")
			}
		}
		cfg.FilesystemRoot = root
		// LocalStoragePath is still required by storage.New for the
		// "local" backend used as the binary blob store. Filesystem
		// mode is for source files; binaries still need a place to live.
		cfg.LocalStoragePath = filepath.Join(root, ".blobs")
	case "", "local":
		cfg.StorageBackend = "local"
		tmp, err := os.MkdirTemp("", "kerf-test-blobs-*")
		if err == nil {
			cfg.LocalStoragePath = tmp
		}
	default:
		cfg.StorageBackend = opts.StorageBackend
	}

	if opts.SystemUserEmail != "" {
		cfg.SystemUserEmail = opts.SystemUserEmail
	}
	if opts.SystemUserPassword != "" {
		cfg.SystemUserPassword = opts.SystemUserPassword
	}
	if opts.SystemUserName != "" {
		cfg.SystemUserName = opts.SystemUserName
	}

	if opts.LocalMode != nil {
		cfg.LocalMode = *opts.LocalMode
	}

	return cfg
}

// buildRouter mirrors cmd/server/main.go's route wiring (minus the SPA
// fallback and cloud routes, which are out of scope for the runner).
func buildRouter(cfg *config.Config, authSvc *auth.Service, deps *handlers.Deps) http.Handler {
	r := chi.NewRouter()
	r.Use(chimw.RequestID)
	r.Use(chimw.Recoverer)
	r.Use(chimw.Timeout(60 * time.Second))
	r.Use(kmw.CORS(cfg.CORSOrigin))

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "env": cfg.Env})
	})

	r.Get("/api/config", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"google_client_id": cfg.GoogleClientID,
			"cloud_enabled":    cfg.Cloud.Enabled,
			"local_mode":       cfg.LocalMode,
			"default_model":    cfg.DefaultModel,
		})
	})

	r.Get("/api/bootstrap", deps.Bootstrap)

	r.Route("/auth", func(r chi.Router) {
		r.Post("/register", deps.Register)
		r.Post("/login", deps.Login)
		r.Post("/refresh", deps.Refresh)
		r.Post("/logout", deps.Logout)
		r.Get("/google/start", deps.GoogleStart)
		r.Get("/google/callback", deps.GoogleCallback)
		r.Post("/bootstrap-local", deps.BootstrapLocal)
	})

	r.Route("/api", func(r chi.Router) {
		r.Group(func(r chi.Router) {
			r.Use(kmw.OptionalAuth(authSvc, deps.Pool))
			r.Get("/share/{token}", deps.LookupShare)
		})

		r.Group(func(r chi.Router) {
			r.Use(kmw.RequireAuth(authSvc, deps.Pool))

			r.Get("/me", deps.Me)
			r.Post("/me/avatar", deps.UploadAvatar)
			r.Delete("/me/avatar", deps.DeleteAvatar)
			r.Get("/models", deps.ListModels)
			r.Post("/share/{token}/accept", deps.AcceptShare)
			r.Get("/blobs/*", deps.ServeBlob)

			// Workspaces — mirrors cmd/server/main.go's wiring.
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

					// Bill of Materials + per-project activity timeline.
					r.Get("/bom", deps.GetBOM)
					r.Get("/activity", deps.GetActivity)

					// Part photos (kind='part' files only — handler enforces).
					r.Post("/files/{fid}/photos", deps.AddPartPhoto)
					r.Delete("/files/{fid}/photos", deps.DeletePartPhoto)
					r.Patch("/files/{fid}/photos/primary", deps.SetPartPhotoPrimary)

					r.Get("/files", deps.ListFiles)
					r.Post("/files", deps.CreateFile)
					r.Get("/files/{fid}", deps.GetFile)
					r.Patch("/files/{fid}", deps.UpdateFile)
					r.Delete("/files/{fid}", deps.DeleteFile)
					r.Get("/files/{fid}/download", deps.DownloadFile)

					// Cross-project derived-artifact cache.
					r.Post("/files/{fid}/derived", deps.LookupDerivedArtifact)
					r.Post("/files/{fid}/derived/store", deps.StoreDerivedArtifact)
					r.Delete("/files/{fid}/derived", deps.PurgeDerivedArtifacts)

					r.Get("/files/{fid}/revisions", deps.ListRevisions)
					r.Get("/files/{fid}/revisions/{rid}", deps.GetRevision)
					r.Post("/files/{fid}/restore/{rid}", deps.RestoreRevision)

					r.Post("/assets", deps.UploadAsset)

					r.Get("/threads", deps.ListThreads)
					r.Post("/threads", deps.CreateThread)
					r.Patch("/threads/{tid}", deps.UpdateThread)
					r.Delete("/threads/{tid}", deps.DeleteThread)

					r.Get("/threads/{tid}/messages", deps.ListMessages)
					r.Post("/threads/{tid}/messages", deps.PostMessage)

					r.Post("/share/links", deps.CreateShareLink)
					r.Get("/share/links", deps.ListShareLinks)
					r.Delete("/share/links/{lid}", deps.DeleteShareLink)

					r.Get("/members", deps.ListMembers)
					r.Post("/members", deps.AddMember)
					r.Patch("/members/{uid}", deps.UpdateMember)
					r.Delete("/members/{uid}", deps.RemoveMember)
				})
			})
		})
	})

	return r
}
