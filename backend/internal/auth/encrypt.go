package auth

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"errors"
	"fmt"
	"io"
)

// AES-GCM at-rest encryption for opaque secrets we have to keep around
// (per-user GitHub OAuth tokens, operator-configured distributor API
// keys, …).
//
// The key is derived deterministically from cfg.JWTSecret via SHA-256 —
// this is a *poor man's KMS*, intentionally lightweight for v1. Two
// real-world consequences apply to every caller:
//
//  1. Rotating the JWT secret invalidates every stored ciphertext.
//     Users / operators have to re-link or re-enter the secret on next
//     use.
//  2. Anyone with read access to both the database and the kerf.toml
//     can decrypt secrets. A real KMS (cloud HSM, Vault, etc.) is the
//     plan for v2.
//
// Format on disk: nonce (12 bytes) || ciphertext || GCM tag.
// We rely on the standard library's GCM, which appends the auth tag
// to the ciphertext, so the on-disk blob is `nonce + Seal(...)`.
//
// The `domain` argument folds a per-purpose constant into the KDF input
// so a ciphertext written for one subsystem (e.g. github tokens) cannot
// be decrypted by another (e.g. distributor credentials) even though
// both share the same JWT secret.

// deriveKey turns the JWT secret into a 32-byte AES-256 key. The
// `domain` string is mixed in so different callers get different keys.
func deriveKey(domain, secret string) []byte {
	h := sha256.Sum256([]byte("kerf:enc:" + domain + ":" + secret))
	return h[:]
}

// EncryptSecret encrypts plaintext under the given domain with a fresh
// random nonce. The output is intended to be stored as bytea.
func EncryptSecret(domain, secret, plaintext string) ([]byte, error) {
	if secret == "" {
		return nil, errors.New("jwt secret is empty; cannot encrypt secret")
	}
	block, err := aes.NewCipher(deriveKey(domain, secret))
	if err != nil {
		return nil, fmt.Errorf("aes cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm: %w", err)
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("nonce: %w", err)
	}
	ct := gcm.Seal(nil, nonce, []byte(plaintext), nil)
	out := make([]byte, 0, len(nonce)+len(ct))
	out = append(out, nonce...)
	out = append(out, ct...)
	return out, nil
}

// DecryptSecret reverses EncryptSecret. Returns an error if the
// ciphertext is malformed or the JWT secret has changed since it was
// written.
func DecryptSecret(domain, secret string, ciphertext []byte) (string, error) {
	if secret == "" {
		return "", errors.New("jwt secret is empty; cannot decrypt secret")
	}
	block, err := aes.NewCipher(deriveKey(domain, secret))
	if err != nil {
		return "", fmt.Errorf("aes cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("gcm: %w", err)
	}
	ns := gcm.NonceSize()
	if len(ciphertext) < ns {
		return "", errors.New("ciphertext too short")
	}
	nonce, ct := ciphertext[:ns], ciphertext[ns:]
	pt, err := gcm.Open(nil, nonce, ct, nil)
	if err != nil {
		return "", fmt.Errorf("gcm open (ciphertext may be corrupted or jwt secret rotated): %w", err)
	}
	return string(pt), nil
}
