package tessellate

import (
	"bytes"
	"fmt"
	"io"
)

// readAllCapped is io.ReadAll with a hard size limit to keep a malicious
// or runaway STEP from blowing through process memory. Returns an error
// if the body exceeds cap bytes.
func readAllCapped(r io.Reader, cap int64) ([]byte, error) {
	if cap <= 0 {
		cap = 500 * 1024 * 1024
	}
	limited := io.LimitReader(r, cap+1)
	buf, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if int64(len(buf)) > cap {
		return nil, fmt.Errorf("input exceeds %d bytes", cap)
	}
	return buf, nil
}

// byteReader wraps a []byte in an io.Reader. Cheaper than bytes.NewReader
// when we only need it for one Storage.Put call.
func byteReader(b []byte) io.Reader { return bytes.NewReader(b) }
