package kerf

import (
	"errors"
	"fmt"
)

// Error wraps a JSON-RPC error response.
type Error struct {
	Code    int
	Message string
	Data    any
}

func (e *Error) Error() string {
	return fmt.Sprintf("kerf: %d %s", e.Code, e.Message)
}

// Is implements errors.Is semantics by matching on Code.
func (e *Error) Is(target error) bool {
	var t *Error
	if errors.As(target, &t) {
		return e.Code == t.Code
	}
	return false
}

// Sentinel errors for common JSON-RPC response codes.
var (
	// ErrMissingEnv is returned when a required environment variable is absent.
	ErrMissingEnv = errors.New("kerf: missing required env var")

	// ErrUnauthorized is returned when the server responds with code -32001.
	ErrUnauthorized = &Error{Code: -32001, Message: "unauthorized"}

	// ErrNotFound is returned when the server responds with code -32004.
	ErrNotFound = &Error{Code: -32004, Message: "not found"}

	// ErrRateLimited is returned when the server responds with code -32429.
	ErrRateLimited = &Error{Code: -32429, Message: "rate limited"}
)

// rpcErrorToSentinel maps a freshly-decoded *Error to a sentinel where possible,
// preserving the original message and data on the returned value while still
// satisfying errors.Is against the sentinels.
func rpcErrorToSentinel(e *Error) *Error {
	switch e.Code {
	case ErrUnauthorized.Code:
		return &Error{Code: e.Code, Message: e.Message, Data: e.Data}
	case ErrNotFound.Code:
		return &Error{Code: e.Code, Message: e.Message, Data: e.Data}
	case ErrRateLimited.Code:
		return &Error{Code: e.Code, Message: e.Message, Data: e.Data}
	}
	return e
}
