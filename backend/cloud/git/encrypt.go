//go:build cloud
// +build cloud

package git

import (
	"github.com/imranp/kerf/backend/internal/auth"
)

// AES-GCM token encryption for per-user GitHub OAuth tokens.
//
// The actual primitive lives in backend/internal/auth/encrypt.go so the
// same helper backs the OSS distributor-credentials subsystem too. We
// pass a stable per-purpose `domain` string so a github-token ciphertext
// cannot be decrypted under the distributor-credentials domain (and
// vice-versa) even though both subsystems share the same JWT secret.
//
// See the docstring in backend/internal/auth/encrypt.go for the on-disk
// format and the JWT-rotation gotcha.

const githubTokenDomain = "cloud:github-token"

// encryptToken encrypts plaintext with a fresh random nonce. The output
// is intended to be stored as bytea in cloud_github_tokens.
func encryptToken(secret, plaintext string) ([]byte, error) {
	return auth.EncryptSecret(githubTokenDomain, secret, plaintext)
}

// decryptToken reverses encryptToken. Returns an error if the ciphertext
// is malformed or the JWT secret has changed since it was written.
func decryptToken(secret string, ciphertext []byte) (string, error) {
	return auth.DecryptSecret(githubTokenDomain, secret, ciphertext)
}
