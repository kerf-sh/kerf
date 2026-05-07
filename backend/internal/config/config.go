package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/pelletier/go-toml/v2"
)

// Config is the flat, runtime-shaped view of the configuration. It's
// populated from a nested TOML file (see kerf.example.toml) but kept flat
// here so callers don't have to thread sub-structs everywhere.
type Config struct {
	// Server
	Env        string
	Port       string
	CORSOrigin string

	// Database
	DatabaseURL string

	// Auth
	JWTSecret      string
	JWTAccessTTL   time.Duration
	JWTRefreshTTL  time.Duration
	PasswordPepper string

	GoogleClientID     string
	GoogleClientSecret string
	GoogleRedirectURL  string

	// LLM
	AnthropicAPIKey string
	OpenAIAPIKey    string
	MoonshotAPIKey  string
	GeminiAPIKey    string
	DefaultModel    string

	// Storage
	StorageBackend    string // "local" | "s3" | "filesystem"
	LocalStoragePath  string
	FilesystemRoot    string
	S3Bucket          string
	S3Region          string
	S3AccessKeyID     string
	S3SecretAccessKey string
	S3Endpoint        string
	S3PublicURLBase   string
	// CDNBaseURL is the public URL prefix for blobs (e.g. a bunny.net
	// Pull Zone over the S3 bucket). When set, Storage.PublicURL emits
	// "<cdn>/<key>?v=<unix>" and the frontend hits the CDN directly
	// instead of going through /api/blobs/. Leave empty to keep blob
	// serving on the auth-protected backend route.
	CDNBaseURL string

	// Usage tracking (token + storage events). Enabled in both OSS and
	// cloud builds when true; cloud builds layer billing on top.
	UsageEnabled bool

	// Limits
	MaxThreadsPerProject int
	// FileRevisionsMax is the per-file cap on retained revision rows. The
	// oldest rows beyond this cap are pruned on every write.
	FileRevisionsMax int
	// StepMaxBytes caps the size of a single STEP file upload (chunked).
	StepMaxBytes int64
	// UploadChunkSize is the chunk size advertised by the chunked upload
	// init endpoint. Clients are expected to honour this exactly.
	UploadChunkSize int64
	// UploadSessionTTL is how long an incomplete upload_sessions row is
	// kept before the janitor sweeps it and its temp chunks.
	UploadSessionTTL time.Duration

	// StepTessellateWorkers is the size of the worker pool that processes
	// step_tessellation_jobs rows. Each worker shells out to the Node
	// sidecar (scripts/step-tessellate.mjs) per job. Set to 0 to disable
	// the worker entirely (jobs queue but never run — useful in unit
	// tests and CI builds without Node).
	StepTessellateWorkers int
	// StepTessellateTimeoutSec caps the runtime of a single Node sidecar
	// invocation. Past this, the worker SIGKILLs the subprocess and marks
	// the job as 'error'. Defaults to 300 (5 minutes).
	StepTessellateTimeoutSec int
	// StepTessellateNodeBin overrides the Node executable path. Empty →
	// PATH lookup of "node".
	StepTessellateNodeBin string
	// StepTessellateScript overrides the path to the sidecar script.
	// Empty → "./scripts/step-tessellate.mjs" relative to cwd.
	StepTessellateScript string

	// System user (seeded by `kerf migrate`).
	SystemUserEmail    string
	SystemUserName     string
	SystemUserPassword string

	// Cloud — only meaningful in cloud builds. OSS builds ignore.
	Cloud CloudConfig

	// Path to the loaded config file (empty if defaults only).
	SourcePath string

	// DeprecationWarnings collects any "this key is gone, here's what
	// replaced it" notes uncovered while parsing. Callers (cmd/server)
	// log them at boot. Never persisted.
	DeprecationWarnings []string
}

// CloudConfig holds the hosted-mode-only settings.
type CloudConfig struct {
	Enabled  bool
	Paystack PaystackConfig
	FX       FXConfig
	Pricing  PricingConfig
	Git      GitConfig
}

// GitConfig configures the cloud-tier real-git integration. Prefix is the
// S3 key prefix (under the same bucket as `[storage.s3]`) where each
// project's bare repo objects/refs are stored. GitHub holds the OAuth
// client used for /auth/github. Stateless by design — every operation is
// a series of S3 reads/writes, so the service is safe to run on
// ephemeral-filesystem platforms (Cloud Run, Fly Machines, etc.).
type GitConfig struct {
	Prefix string
	GitHub GitHubConfig
}

// GitHubConfig is the OAuth client config for linking a Kerf user to a
// GitHub account. RedirectURL must match the GitHub app's configured
// callback (default: http://localhost:8080/auth/github/callback).
type GitHubConfig struct {
	ClientID     string
	ClientSecret string
	RedirectURL  string
}

type PaystackConfig struct {
	SecretKey     string
	PublicKey     string
	WebhookSecret string
}

type FXConfig struct {
	BaseCurrency       string
	SettlementCurrency string
	RefreshURL         string
	SpreadPct          float64
}

type PricingConfig struct {
	TokenMarkupPct        float64
	StorageUSDPerGBMonth  float64
	FreeStorageMB         int
}

// --- TOML parse target (nested shape on disk) ---

type tomlConfig struct {
	Server struct {
		Port       string `toml:"port"`
		Env        string `toml:"env"`
		CORSOrigin string `toml:"cors_origin"`
	} `toml:"server"`

	Database struct {
		URL string `toml:"url"`
	} `toml:"database"`

	Auth struct {
		// Optional is deprecated. Setting it to true logs a one-line
		// deprecation warning at boot but is otherwise ignored — auth is
		// always on and a system_user-driven auto-bootstrap supplies the
		// brew/curl-install "open browser, you're already logged in" UX.
		Optional       bool   `toml:"optional"`
		JWTSecret      string `toml:"jwt_secret"`
		AccessTTL      string `toml:"access_ttl"`
		RefreshTTL     string `toml:"refresh_ttl"`
		PasswordPepper string `toml:"password_pepper"`
		Google         struct {
			ClientID     string `toml:"client_id"`
			ClientSecret string `toml:"client_secret"`
			RedirectURL  string `toml:"redirect_url"`
		} `toml:"google"`
	} `toml:"auth"`

	Storage struct {
		Backend        string `toml:"backend"`
		LocalPath      string `toml:"local_path"`
		FilesystemRoot string `toml:"filesystem_root"`
		CDNBaseURL     string `toml:"cdn_base_url"`
		S3             struct {
			Bucket          string `toml:"bucket"`
			Region          string `toml:"region"`
			AccessKeyID     string `toml:"access_key_id"`
			SecretAccessKey string `toml:"secret_access_key"`
			Endpoint        string `toml:"endpoint"`
			PublicURLBase   string `toml:"public_url_base"`
		} `toml:"s3"`
	} `toml:"storage"`

	LLM struct {
		DefaultModel string `toml:"default_model"`
		Anthropic    struct {
			APIKey string `toml:"api_key"`
		} `toml:"anthropic"`
		OpenAI struct {
			APIKey string `toml:"api_key"`
		} `toml:"openai"`
		Moonshot struct {
			APIKey string `toml:"api_key"`
		} `toml:"moonshot"`
		Gemini struct {
			APIKey string `toml:"api_key"`
		} `toml:"gemini"`
	} `toml:"llm"`

	Usage struct {
		Enabled bool `toml:"enabled"`
	} `toml:"usage"`

	Limits struct {
		MaxThreadsPerProject     int    `toml:"max_threads_per_project"`
		FileRevisionsMax         int    `toml:"file_revisions_max"`
		StepMaxBytes             int64  `toml:"step_max_bytes"`
		UploadChunkSize          int64  `toml:"upload_chunk_size"`
		UploadSessionTTLHours    int    `toml:"upload_session_ttl_hours"`
		StepTessellateWorkers    int    `toml:"step_tessellate_workers"`
		StepTessellateTimeoutSec int    `toml:"step_tessellate_timeout_sec"`
		StepTessellateNodeBin    string `toml:"step_tessellate_node_bin"`
		StepTessellateScript     string `toml:"step_tessellate_script"`
	} `toml:"limits"`

	SystemUser struct {
		Email    string `toml:"email"`
		Name     string `toml:"name"`
		Password string `toml:"password"`
	} `toml:"system_user"`

	Cloud struct {
		Enabled  bool `toml:"enabled"`
		Paystack struct {
			SecretKey     string `toml:"secret_key"`
			PublicKey     string `toml:"public_key"`
			WebhookSecret string `toml:"webhook_secret"`
		} `toml:"paystack"`
		FX struct {
			BaseCurrency       string  `toml:"base_currency"`
			SettlementCurrency string  `toml:"settlement_currency"`
			RefreshURL         string  `toml:"refresh_url"`
			SpreadPct          float64 `toml:"spread_pct"`
		} `toml:"fx"`
		Pricing struct {
			TokenMarkupPct       float64 `toml:"token_markup_pct"`
			StorageUSDPerGBMonth float64 `toml:"storage_usd_per_gb_month"`
			FreeStorageMB        int     `toml:"free_storage_mb"`
		} `toml:"pricing"`
		Git struct {
			Prefix string `toml:"prefix"`
			GitHub struct {
				ClientID     string `toml:"client_id"`
				ClientSecret string `toml:"client_secret"`
				RedirectURL  string `toml:"redirect_url"`
			} `toml:"github"`
		} `toml:"git"`
	} `toml:"cloud"`
}

// Load resolves and reads the config file, applies defaults, and validates.
//
// The pathOverride argument (typically from a --config CLI flag) takes
// highest precedence. Beyond that, search order is:
//
//	$KERF_CONFIG
//	./kerf.toml
//	$XDG_CONFIG_HOME/kerf/config.toml  (or ~/.config/kerf/config.toml)
//	/etc/kerf/config.toml
//
// If nothing is found, Load returns an error explaining where to drop the
// file. To run with no config (e.g. for `kerf init`), call Defaults().
func Load(pathOverride string) (*Config, error) {
	path, err := resolveConfigPath(pathOverride)
	if err != nil {
		return nil, err
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}

	var t tomlConfig
	if err := toml.Unmarshal(raw, &t); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}

	cfg := fromTOML(&t)
	cfg.SourcePath = path
	if t.Auth.Optional {
		cfg.DeprecationWarnings = append(cfg.DeprecationWarnings,
			"[auth].optional is deprecated and ignored — auth is always on; "+
				"set [system_user].password to enable the auto-bootstrap single-user UX")
	}
	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("config %s: %w", path, err)
	}
	return cfg, nil
}

// Defaults returns a Config populated with the same defaults that would
// apply to an empty TOML file. Used by `kerf init` and tests.
func Defaults() *Config {
	cfg := fromTOML(&tomlConfig{})
	return cfg
}

// resolveConfigPath finds the kerf.toml file to load.
func resolveConfigPath(override string) (string, error) {
	tried := []string{}
	check := func(p string) (string, bool) {
		if p == "" {
			return "", false
		}
		expanded := expandHome(p)
		tried = append(tried, expanded)
		if info, err := os.Stat(expanded); err == nil && !info.IsDir() {
			abs, _ := filepath.Abs(expanded)
			return abs, true
		}
		return "", false
	}

	if p, ok := check(override); ok {
		return p, nil
	}
	if p, ok := check(os.Getenv("KERF_CONFIG")); ok {
		return p, nil
	}
	if p, ok := check("./kerf.toml"); ok {
		return p, nil
	}

	xdg := os.Getenv("XDG_CONFIG_HOME")
	if xdg == "" {
		if home, err := os.UserHomeDir(); err == nil {
			xdg = filepath.Join(home, ".config")
		}
	}
	if xdg != "" {
		if p, ok := check(filepath.Join(xdg, "kerf", "config.toml")); ok {
			return p, nil
		}
	}
	if p, ok := check("/etc/kerf/config.toml"); ok {
		return p, nil
	}

	return "", fmt.Errorf("no kerf.toml found (looked in: %s)\nrun `kerf init` to create one, or copy kerf.example.toml", strings.Join(tried, ", "))
}

// fromTOML applies defaults and converts the on-disk shape to the runtime
// Config. Empty TOML produces a fully-defaulted Config.
func fromTOML(t *tomlConfig) *Config {
	cfg := &Config{
		// Server
		Env:        firstNonEmpty(t.Server.Env, "local"),
		Port:       firstNonEmpty(t.Server.Port, "8080"),
		CORSOrigin: firstNonEmpty(t.Server.CORSOrigin, "http://localhost:5173"),

		DatabaseURL: t.Database.URL,

		JWTSecret:          t.Auth.JWTSecret,
		PasswordPepper:     t.Auth.PasswordPepper,
		GoogleClientID:     t.Auth.Google.ClientID,
		GoogleClientSecret: t.Auth.Google.ClientSecret,
		GoogleRedirectURL:  firstNonEmpty(t.Auth.Google.RedirectURL, "http://localhost:8080/auth/google/callback"),

		AnthropicAPIKey: t.LLM.Anthropic.APIKey,
		OpenAIAPIKey:    t.LLM.OpenAI.APIKey,
		MoonshotAPIKey:  t.LLM.Moonshot.APIKey,
		GeminiAPIKey:    t.LLM.Gemini.APIKey,
		DefaultModel:    firstNonEmpty(t.LLM.DefaultModel, "claude-opus-4-7"),

		StorageBackend:    firstNonEmpty(t.Storage.Backend, "local"),
		LocalStoragePath:  expandHome(firstNonEmpty(t.Storage.LocalPath, "./.kerf-storage")),
		FilesystemRoot:    expandHome(firstNonEmpty(t.Storage.FilesystemRoot, "~/kerf-projects")),
		CDNBaseURL:        strings.TrimRight(t.Storage.CDNBaseURL, "/"),
		S3Bucket:          t.Storage.S3.Bucket,
		S3Region:          t.Storage.S3.Region,
		S3AccessKeyID:     t.Storage.S3.AccessKeyID,
		S3SecretAccessKey: t.Storage.S3.SecretAccessKey,
		S3Endpoint:        t.Storage.S3.Endpoint,
		S3PublicURLBase:   t.Storage.S3.PublicURLBase,

		UsageEnabled: t.Usage.Enabled,

		MaxThreadsPerProject: defaultInt(t.Limits.MaxThreadsPerProject, 50),
		FileRevisionsMax:     defaultInt(t.Limits.FileRevisionsMax, 200),
		StepMaxBytes:         defaultInt64(t.Limits.StepMaxBytes, 200_000_000),
		UploadChunkSize:      defaultInt64(t.Limits.UploadChunkSize, 5_242_880),
		UploadSessionTTL:     time.Duration(defaultInt(t.Limits.UploadSessionTTLHours, 24)) * time.Hour,

		// StepTessellateWorkers defaults to 2 when the key is unset (zero
		// in the parsed struct). Pass a negative value (-1) to explicitly
		// disable the worker pool while keeping the schema present.
		StepTessellateWorkers:    defaultIntAllowNegativeAsZero(t.Limits.StepTessellateWorkers, 2),
		StepTessellateTimeoutSec: defaultInt(t.Limits.StepTessellateTimeoutSec, 300),
		StepTessellateNodeBin:    t.Limits.StepTessellateNodeBin,
		StepTessellateScript:     t.Limits.StepTessellateScript,

		SystemUserEmail:    t.SystemUser.Email,
		SystemUserName:     t.SystemUser.Name,
		SystemUserPassword: t.SystemUser.Password,

		Cloud: CloudConfig{
			Enabled: t.Cloud.Enabled,
			Paystack: PaystackConfig{
				SecretKey:     t.Cloud.Paystack.SecretKey,
				PublicKey:     t.Cloud.Paystack.PublicKey,
				WebhookSecret: t.Cloud.Paystack.WebhookSecret,
			},
			FX: FXConfig{
				BaseCurrency:       firstNonEmpty(t.Cloud.FX.BaseCurrency, "USD"),
				SettlementCurrency: firstNonEmpty(t.Cloud.FX.SettlementCurrency, "ZAR"),
				RefreshURL:         firstNonEmpty(t.Cloud.FX.RefreshURL, "https://api.exchangerate.host/latest?base=USD&symbols=ZAR"),
				SpreadPct:          defaultFloat(t.Cloud.FX.SpreadPct, 1.5),
			},
			Pricing: PricingConfig{
				TokenMarkupPct:       defaultFloat(t.Cloud.Pricing.TokenMarkupPct, 20.0),
				StorageUSDPerGBMonth: defaultFloat(t.Cloud.Pricing.StorageUSDPerGBMonth, 0.20),
				FreeStorageMB:        defaultInt(t.Cloud.Pricing.FreeStorageMB, 50),
			},
			Git: GitConfig{
				Prefix: firstNonEmpty(t.Cloud.Git.Prefix, "git"),
				GitHub: GitHubConfig{
					ClientID:     t.Cloud.Git.GitHub.ClientID,
					ClientSecret: t.Cloud.Git.GitHub.ClientSecret,
					RedirectURL:  firstNonEmpty(t.Cloud.Git.GitHub.RedirectURL, "http://localhost:8080/auth/github/callback"),
				},
			},
		},
	}

	cfg.JWTAccessTTL = parseDuration(t.Auth.AccessTTL, 15*time.Minute)
	cfg.JWTRefreshTTL = parseDuration(t.Auth.RefreshTTL, 720*time.Hour)

	return cfg
}

// validate performs the minimum checks required for the server to start.
// Auth-only-via-Google installs may not need a JWT secret, but a Postgres
// URL is currently always required.
func (c *Config) validate() error {
	if c.DatabaseURL == "" {
		return fmt.Errorf("database.url is required")
	}
	switch c.StorageBackend {
	case "local", "s3", "filesystem":
	case "":
		c.StorageBackend = "local"
	default:
		return fmt.Errorf("storage.backend must be local|s3|filesystem (got %q)", c.StorageBackend)
	}
	return nil
}

// expandHome substitutes a leading ~ for the current user's home dir.
func expandHome(p string) string {
	if p == "" || !strings.HasPrefix(p, "~") {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return p
	}
	if p == "~" {
		return home
	}
	if strings.HasPrefix(p, "~/") {
		return filepath.Join(home, p[2:])
	}
	return p
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

func defaultInt(v, def int) int {
	if v == 0 {
		return def
	}
	return v
}

// defaultIntAllowNegativeAsZero is like defaultInt but treats a negative
// value as an explicit "0 / disabled" signal. Lets `step_tessellate_workers
// = -1` in TOML disable the worker pool without colliding with the
// "unset → default" path.
func defaultIntAllowNegativeAsZero(v, def int) int {
	if v == 0 {
		return def
	}
	if v < 0 {
		return 0
	}
	return v
}

func defaultInt64(v, def int64) int64 {
	if v == 0 {
		return def
	}
	return v
}

func defaultFloat(v, def float64) float64 {
	if v == 0 {
		return def
	}
	return v
}

func parseDuration(v string, def time.Duration) time.Duration {
	if v == "" {
		return def
	}
	d, err := time.ParseDuration(v)
	if err != nil {
		return def
	}
	return d
}
