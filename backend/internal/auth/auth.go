package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"

	"github.com/imranp/kerf/backend/internal/config"
)

// Service is the authentication helper bundle.
type Service struct {
	cfg  *config.Config
	pool *pgxpool.Pool
}

func New(cfg *config.Config, pool *pgxpool.Pool) *Service {
	return &Service{cfg: cfg, pool: pool}
}

// HashPassword applies bcrypt with the supplied pepper. This is the canonical
// implementation used by both the auth service and the migrate CLI's seeder so
// that seeded credentials are interchangeable with normal sign-ups.
func HashPassword(password, pepper string) (string, error) {
	combined := password + pepper
	b, err := bcrypt.GenerateFromPassword([]byte(combined), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(b), nil
}

// CheckPassword verifies a bcrypt hash created with the supplied pepper.
func CheckPassword(hash, password, pepper string) bool {
	combined := password + pepper
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(combined)) == nil
}

// HashPassword applies bcrypt with the configured pepper.
func (s *Service) HashPassword(password string) (string, error) {
	return HashPassword(password, s.cfg.PasswordPepper)
}

// CheckPassword verifies a bcrypt hash created with the configured pepper.
func (s *Service) CheckPassword(hash, password string) bool {
	return CheckPassword(hash, password, s.cfg.PasswordPepper)
}

// IssueAccessToken builds a signed JWT for the given user id.
func (s *Service) IssueAccessToken(userID string) (string, error) {
	now := time.Now()
	claims := jwt.MapClaims{
		"sub": userID,
		"iat": now.Unix(),
		"exp": now.Add(s.cfg.JWTAccessTTL).Unix(),
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return tok.SignedString([]byte(s.cfg.JWTSecret))
}

// ParseAccessToken validates the JWT and returns the contained subject (user id).
func (s *Service) ParseAccessToken(raw string) (string, error) {
	tok, err := jwt.Parse(raw, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return []byte(s.cfg.JWTSecret), nil
	})
	if err != nil {
		return "", err
	}
	claims, ok := tok.Claims.(jwt.MapClaims)
	if !ok || !tok.Valid {
		return "", errors.New("invalid token")
	}
	sub, _ := claims["sub"].(string)
	if sub == "" {
		return "", errors.New("missing sub")
	}
	return sub, nil
}

// IssueRefreshToken creates a fresh opaque refresh token, persists its hash, and
// returns the plaintext token to send to the client.
func (s *Service) IssueRefreshToken(ctx context.Context, userID string) (string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	token := base64.RawURLEncoding.EncodeToString(raw)
	hash := HashToken(token)
	expires := time.Now().Add(s.cfg.JWTRefreshTTL)
	_, err := s.pool.Exec(ctx,
		`insert into refresh_tokens(user_id, token_hash, expires_at) values ($1,$2,$3)`,
		userID, hash, expires)
	if err != nil {
		return "", err
	}
	return token, nil
}

// HashToken produces the sha256 hex digest used for storing refresh tokens.
func HashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

// RotateRefreshToken validates the supplied refresh token, revokes it, and issues
// a new one alongside an access token.
func (s *Service) RotateRefreshToken(ctx context.Context, refresh string) (userID, access, newRefresh string, err error) {
	hash := HashToken(refresh)
	var (
		id        string
		uid       string
		expires   time.Time
		revokedAt *time.Time
	)
	err = s.pool.QueryRow(ctx,
		`select id, user_id, expires_at, revoked_at from refresh_tokens where token_hash = $1`,
		hash).Scan(&id, &uid, &expires, &revokedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", "", "", errors.New("invalid refresh token")
		}
		return "", "", "", err
	}
	if revokedAt != nil {
		return "", "", "", errors.New("refresh token revoked")
	}
	if time.Now().After(expires) {
		return "", "", "", errors.New("refresh token expired")
	}
	if _, err := s.pool.Exec(ctx, `update refresh_tokens set revoked_at = now() where id = $1`, id); err != nil {
		return "", "", "", err
	}
	access, err = s.IssueAccessToken(uid)
	if err != nil {
		return "", "", "", err
	}
	newRefresh, err = s.IssueRefreshToken(ctx, uid)
	if err != nil {
		return "", "", "", err
	}
	return uid, access, newRefresh, nil
}

// RevokeRefreshToken marks the supplied token as revoked. It is a no-op if the
// token is unknown.
func (s *Service) RevokeRefreshToken(ctx context.Context, refresh string) error {
	hash := HashToken(refresh)
	_, err := s.pool.Exec(ctx,
		`update refresh_tokens set revoked_at = now() where token_hash = $1 and revoked_at is null`,
		hash)
	return err
}

// IssueShareToken returns a fresh URL-safe random string for share links.
func IssueShareToken() (string, error) {
	raw := make([]byte, 24)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

const apiTokenPrefix = "kerf_sk_"
const apiTokenRandomLen = 32

func GenerateAPIToken() (string, error) {
	raw := make([]byte, apiTokenRandomLen)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	return apiTokenPrefix + base64.RawURLEncoding.EncodeToString(raw), nil
}

func HashAPIToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

type APITokenMeta struct {
	ID          string
	WorkspaceID string
	UserID      string
	Name        string
	Scopes      []string
	LastUsedAt  *time.Time
	RevokedAt   *time.Time
	CreatedAt   time.Time
}

func (s *Service) CreateAPIToken(ctx context.Context, workspaceID, userID, name string) (token string, err error) {
	token, err = GenerateAPIToken()
	if err != nil {
		return "", err
	}
	hash := HashAPIToken(token)
	_, err = s.pool.Exec(ctx,
		`insert into api_tokens(workspace_id, user_id, token_hash, name) values ($1,$2,$3,$4)`,
		workspaceID, userID, hash, name)
	if err != nil {
		return "", err
	}
	return token, nil
}

func (s *Service) ValidateAPIToken(ctx context.Context, rawToken string) (*APITokenMeta, error) {
	hash := HashAPIToken(rawToken)
	var meta APITokenMeta
	var scopes []byte
	err := s.pool.QueryRow(ctx,
		`select id, workspace_id, user_id, name, scopes, last_used_at, revoked_at, created_at
		   from api_tokens where token_hash = $1`,
		hash).Scan(&meta.ID, &meta.WorkspaceID, &meta.UserID, &meta.Name, &scopes, &meta.LastUsedAt, &meta.RevokedAt, &meta.CreatedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, errors.New("invalid token")
		}
		return nil, err
	}
	if meta.RevokedAt != nil {
		return nil, errors.New("token revoked")
	}
	if err := json.Unmarshal(scopes, &meta.Scopes); err != nil {
		return nil, err
	}
	s.pool.Exec(ctx, `update api_tokens set last_used_at = now() where id = $1`, meta.ID)
	return &meta, nil
}

func (s *Service) ListAPITokens(ctx context.Context, workspaceID, userID string) ([]APITokenMeta, error) {
	rows, err := s.pool.Query(ctx,
		`select id, workspace_id, user_id, name, scopes, last_used_at, revoked_at, created_at
		   from api_tokens where workspace_id = $1 and user_id = $2 and revoked_at is null
		   order by created_at desc`,
		workspaceID, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var tokens []APITokenMeta
	for rows.Next() {
		var m APITokenMeta
		var scopes []byte
		if err := rows.Scan(&m.ID, &m.WorkspaceID, &m.UserID, &m.Name, &scopes, &m.LastUsedAt, &m.RevokedAt, &m.CreatedAt); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(scopes, &m.Scopes); err != nil {
			return nil, err
		}
		tokens = append(tokens, m)
	}
	return tokens, rows.Err()
}

func (s *Service) RevokeAPIToken(ctx context.Context, tokenID, workspaceID, userID string) error {
	_, err := s.pool.Exec(ctx,
		`update api_tokens set revoked_at = now() where id = $1 and workspace_id = $2 and user_id = $3 and revoked_at is null`,
		tokenID, workspaceID, userID)
	return err
}
