package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/joho/godotenv"
)

// Config holds all environment-driven settings used by the server and CLIs.
type Config struct {
	Env  string
	Port string

	DatabaseURL string

	JWTSecret      string
	JWTAccessTTL   time.Duration
	JWTRefreshTTL  time.Duration
	PasswordPepper string

	GoogleClientID     string
	GoogleClientSecret string
	GoogleRedirectURL  string

	CORSOrigin string

	AnthropicAPIKey string
	AnthropicModel  string

	MaxThreadsPerProject int

	// System user — seeded by `cmd/migrate`. The password is hashed with the
	// same pepper as normal users so the system account can log in via
	// /auth/login like any other user.
	SystemUserEmail    string
	SystemUserName     string
	SystemUserPassword string
}

// Load reads .env files from the repo root according to the provided env name
// and returns a populated Config.
//
//	local -> .env
//	dev   -> .env then .env.dev (overlay)
//	main  -> .env then .env.main (overlay)
func Load(env string) (*Config, error) {
	if env == "" {
		env = "local"
	}

	root, err := repoRoot()
	if err != nil {
		return nil, err
	}

	// Always load base .env first.
	base := filepath.Join(root, ".env")
	if err := godotenv.Overload(base); err != nil && !os.IsNotExist(err) {
		return nil, fmt.Errorf("load %s: %w", base, err)
	}

	switch env {
	case "local":
		// nothing extra
	case "dev":
		overlay := filepath.Join(root, ".env.dev")
		if err := godotenv.Overload(overlay); err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("load %s: %w", overlay, err)
		}
	case "main":
		overlay := filepath.Join(root, ".env.main")
		if err := godotenv.Overload(overlay); err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("load %s: %w", overlay, err)
		}
	default:
		return nil, fmt.Errorf("unknown env %q (expected local|dev|main)", env)
	}

	cfg := &Config{
		Env:                  env,
		Port:                 getenv("PORT", "8080"),
		DatabaseURL:          os.Getenv("DATABASE_URL"),
		JWTSecret:            os.Getenv("JWT_SECRET"),
		PasswordPepper:       os.Getenv("PASSWORD_PEPPER"),
		GoogleClientID:       os.Getenv("GOOGLE_CLIENT_ID"),
		GoogleClientSecret:   os.Getenv("GOOGLE_CLIENT_SECRET"),
		GoogleRedirectURL:    os.Getenv("GOOGLE_REDIRECT_URL"),
		CORSOrigin:           getenv("CORS_ORIGIN", "http://localhost:5173"),
		AnthropicAPIKey:      os.Getenv("ANTHROPIC_API_KEY"),
		AnthropicModel:       getenv("ANTHROPIC_MODEL", "claude-opus-4-7"),
		MaxThreadsPerProject: getenvInt("MAX_THREADS_PER_PROJECT", 50),
		SystemUserEmail:      os.Getenv("SYSTEM_USER_EMAIL"),
		SystemUserName:       os.Getenv("SYSTEM_USER_NAME"),
		SystemUserPassword:   os.Getenv("SYSTEM_USER_PASSWORD"),
	}

	cfg.JWTAccessTTL = parseDuration(getenv("JWT_ACCESS_TTL", "15m"), 15*time.Minute)
	cfg.JWTRefreshTTL = parseDuration(getenv("JWT_REFRESH_TTL", "720h"), 720*time.Hour)

	if cfg.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}

	return cfg, nil
}

// repoRoot walks up from the current working directory looking for a directory
// that contains a `.env.example` file (the repo root marker).
func repoRoot() (string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	dir := cwd
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, ".env.example")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	// Fall back to cwd; godotenv will simply fail to find the file.
	return cwd, nil
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getenvInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
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
