//go:build cloud
// +build cloud

package git

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	smithy "github.com/aws/smithy-go"

	"github.com/go-git/go-billy/v5"
)

// s3FS implements billy.Filesystem on top of an S3-compatible object
// store. It's the entire stateless-git story:
//
//   - billy.Basic   — Open/Create/OpenFile/Stat/Rename/Remove/Join.
//   - billy.Dir     — ReadDir (delimited list) and MkdirAll (no-op).
//   - billy.TempFile — used during pack writes.
//   - billy.Symlink  — Lstat aliased to Stat; Symlink/Readlink return
//                     ErrNotSupported. Bare repos don't symlink.
//   - billy.Chroot   — implemented directly so go-git's storage layer
//                     can ask for an alternates-rooted sub-fs without us
//                     paying the per-segment Lstat cost that the stock
//                     chroot helper imposes.
//
// We deliberately implement Chroot ourselves rather than going through
// the stock chroot.New helper. The helper resolves symlinks segment-by-
// segment by calling Lstat on each prefix — innocuous on disk, brutal
// on S3 (every Stat is a HEAD + maybe a List). Bare repos don't have
// symlinks anyway, so we skip that resolution entirely.
//
// Concurrency model: each Service holds one *s3.Client and one s3FS
// per project (built on demand in openRepo). go-git's filesystem backend
// is safe for single-repo use; we serialize mutating ops across goroutines
// in the same process via Service.lockProject. Cross-container safety
// for ref updates is provided by Create()'s S3 conditional PUT
// (If-None-Match: "*") — concurrent ref-lock attempts get
// PreconditionFailed, which file.Close() maps to os.ErrExist.
type s3FS struct {
	client *s3.Client
	bucket string

	// root is the absolute key prefix (no leading slash, no trailing
	// slash). E.g. "git/abc-1234". Joined with billy paths to form
	// S3 keys.
	root string
}

// newS3FS builds an s3FS rooted at <bucket>/<rootPrefix>. rootPrefix is
// trimmed of any leading or trailing slashes so callers can be sloppy.
func newS3FS(client *s3.Client, bucket, rootPrefix string) *s3FS {
	return &s3FS{
		client: client,
		bucket: bucket,
		root:   strings.Trim(rootPrefix, "/"),
	}
}

// --- billy.Basic ---------------------------------------------------------

func (f *s3FS) Create(filename string) (billy.File, error) {
	return f.OpenFile(filename, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0o666)
}

func (f *s3FS) Open(filename string) (billy.File, error) {
	return f.OpenFile(filename, os.O_RDONLY, 0)
}

// OpenFile opens or creates a file backed by an S3 object.
//
// Read-only opens (O_RDONLY) issue a single GetObject up front and serve
// reads from an in-memory buffer. Write opens issue the PutObject in
// Close(). For a true write+truncate (O_TRUNC), we start with an empty
// buffer; for create-without-truncate, we attempt to seed from the
// existing object.
//
// O_EXCL is honoured by issuing the eventual PUT with
// If-None-Match: "*" (see s3File.Close + s3FS.putBody) so the safety
// check is across containers, not just this process. The pre-open HEAD
// is best-effort.
func (f *s3FS) OpenFile(filename string, flag int, _ os.FileMode) (billy.File, error) {
	key := f.keyFor(filename)
	wantRead := flag&os.O_WRONLY == 0
	wantWrite := flag&(os.O_WRONLY|os.O_RDWR) != 0
	create := flag&os.O_CREATE != 0
	excl := flag&os.O_EXCL != 0
	trunc := flag&os.O_TRUNC != 0

	if excl && create {
		// Best-effort existence check; the conditional PUT in Close()
		// is the real defence against races.
		if _, err := f.head(key); err == nil {
			return nil, os.ErrExist
		}
	}

	// We need to seed the buffer from the existing object whenever the
	// caller will read it (read-only, or read+write without truncate).
	// On pure write+truncate paths, skip the GET entirely.
	needSeed := !trunc && (wantRead || wantWrite)
	if !wantWrite && !create {
		// Pure read of a missing file is the canonical "doesn't exist" case.
		needSeed = true
	}
	var initial []byte
	if needSeed {
		body, err := f.get(key)
		if err == nil {
			initial = body
		} else if errors.Is(err, os.ErrNotExist) {
			if !create {
				return nil, os.ErrNotExist
			}
		} else {
			return nil, err
		}
	}

	return &s3File{
		fs:        f,
		key:       key,
		name:      filename,
		buf:       bytes.NewBuffer(append([]byte(nil), initial...)),
		writable:  wantWrite,
		writeOnce: create && excl,
	}, nil
}

func (f *s3FS) Stat(filename string) (os.FileInfo, error) {
	key := f.keyFor(filename)
	out, err := f.head(key)
	if err != nil {
		// Could be a "directory" (no real key, but objects exist
		// under that prefix) — try ReadDir.
		if errors.Is(err, os.ErrNotExist) {
			if entries, derr := f.ReadDir(filename); derr == nil && len(entries) > 0 {
				return synthDirInfo(path.Base(filename)), nil
			}
		}
		return nil, err
	}
	size := int64(0)
	if out.ContentLength != nil {
		size = *out.ContentLength
	}
	mod := time.Time{}
	if out.LastModified != nil {
		mod = *out.LastModified
	}
	return &s3FileInfo{name: path.Base(filename), size: size, mod: mod}, nil
}

func (f *s3FS) Rename(from, to string) error {
	srcKey := f.keyFor(from)
	dstKey := f.keyFor(to)
	if srcKey == dstKey {
		return nil
	}
	ctx := context.Background()
	if _, err := f.client.CopyObject(ctx, &s3.CopyObjectInput{
		Bucket:     aws.String(f.bucket),
		Key:        aws.String(dstKey),
		CopySource: aws.String(f.bucket + "/" + srcKey),
	}); err != nil {
		if isS3NotFound(err) {
			return os.ErrNotExist
		}
		return fmt.Errorf("billyfs: rename copy %s -> %s: %w", srcKey, dstKey, err)
	}
	if _, err := f.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(f.bucket),
		Key:    aws.String(srcKey),
	}); err != nil {
		return fmt.Errorf("billyfs: rename delete %s: %w", srcKey, err)
	}
	return nil
}

func (f *s3FS) Remove(filename string) error {
	key := f.keyFor(filename)
	_, err := f.client.DeleteObject(context.Background(), &s3.DeleteObjectInput{
		Bucket: aws.String(f.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		if isS3NotFound(err) {
			return os.ErrNotExist
		}
		return fmt.Errorf("billyfs: remove %s: %w", key, err)
	}
	return nil
}

// Join uses POSIX path semantics. Git on disk uses forward slashes
// regardless of host OS, and we use forward slashes for S3 keys.
func (f *s3FS) Join(elem ...string) string {
	return path.Join(elem...)
}

// --- billy.Dir -----------------------------------------------------------

// ReadDir is implemented as a delimited ListObjectsV2 with the path as
// the prefix and "/" as the delimiter. CommonPrefixes become synthetic
// directory entries.
func (f *s3FS) ReadDir(p string) ([]os.FileInfo, error) {
	prefix := f.keyFor(p)
	if prefix != "" && !strings.HasSuffix(prefix, "/") {
		prefix += "/"
	}

	ctx := context.Background()
	infos := []os.FileInfo{}
	var token *string
	for {
		out, err := f.client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
			Bucket:            aws.String(f.bucket),
			Prefix:            aws.String(prefix),
			Delimiter:         aws.String("/"),
			ContinuationToken: token,
		})
		if err != nil {
			return nil, fmt.Errorf("billyfs: readdir %s: %w", prefix, err)
		}
		for _, o := range out.Contents {
			if o.Key == nil {
				continue
			}
			name := strings.TrimPrefix(*o.Key, prefix)
			if name == "" {
				continue
			}
			size := int64(0)
			if o.Size != nil {
				size = *o.Size
			}
			mod := time.Time{}
			if o.LastModified != nil {
				mod = *o.LastModified
			}
			infos = append(infos, &s3FileInfo{name: name, size: size, mod: mod})
		}
		for _, cp := range out.CommonPrefixes {
			if cp.Prefix == nil {
				continue
			}
			name := strings.TrimSuffix(strings.TrimPrefix(*cp.Prefix, prefix), "/")
			if name == "" {
				continue
			}
			infos = append(infos, synthDirInfo(name))
		}
		if out.IsTruncated == nil || !*out.IsTruncated {
			break
		}
		token = out.NextContinuationToken
	}
	return infos, nil
}

// MkdirAll is a no-op. S3 has no directories — the path is implied by
// the keys. dotgit calls MkdirAll during Initialize() but it's safe to
// pretend it succeeded; the keys will appear when actual files are
// written.
func (f *s3FS) MkdirAll(string, os.FileMode) error { return nil }

// --- billy.TempFile ------------------------------------------------------

// TempFile creates a temp object under <dir>/.tmp-<random> and returns a
// writable handle. go-git uses this during pack-write, then Renames the
// finished pack to its final name. The .tmp- prefix is recognized by
// dotgit's pack-write pipeline.
func (f *s3FS) TempFile(dir, prefix string) (billy.File, error) {
	suffix := randomSuffix()
	name := f.Join(dir, fmt.Sprintf(".tmp-%s-%s", prefix, suffix))
	return f.OpenFile(name, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0o600)
}

// --- billy.Symlink (no-op) ----------------------------------------------

// Lstat is identical to Stat — no symlinks in S3.
func (f *s3FS) Lstat(filename string) (os.FileInfo, error) { return f.Stat(filename) }

func (f *s3FS) Symlink(string, string) error    { return billy.ErrNotSupported }
func (f *s3FS) Readlink(string) (string, error) { return "", billy.ErrNotSupported }

// --- billy.Chroot --------------------------------------------------------

// Chroot returns a new s3FS rooted under p. go-git asks for these when
// it sets up alternates; for our use the result is just another
// stateless wrapper, so we don't have to worry about lifecycle.
func (f *s3FS) Chroot(p string) (billy.Filesystem, error) {
	sub := strings.Trim(path.Clean("/"+p), "/")
	root := f.root
	if sub != "" {
		if root == "" {
			root = sub
		} else {
			root = root + "/" + sub
		}
	}
	return &s3FS{client: f.client, bucket: f.bucket, root: root}, nil
}

// Root returns the current root prefix. go-git uses it to render
// "filesystem" paths in errors. We return "/" rather than the S3 key so
// downstream debuggers see a familiar shape.
func (f *s3FS) Root() string { return "/" }

// Capabilities tells go-git this fs supports basic write+read+seek+
// truncate. We deliberately omit ReadAndWriteCapability so dotgit's
// SetRef goes through the simpler `setRefNorwfs` path that doesn't try
// to OpenFile in O_RDWR mode for ref updates — instead it reads, then
// writes via Create(). Our Create flow's conditional PUT is the
// cross-container safety net.
func (f *s3FS) Capabilities() billy.Capability {
	return billy.WriteCapability | billy.ReadCapability |
		billy.SeekCapability | billy.TruncateCapability
}

// --- internals -----------------------------------------------------------

// keyFor maps a billy path to the absolute S3 object key under the
// project root. Both leading slashes and dotted components are
// normalised away.
func (f *s3FS) keyFor(p string) string {
	p = strings.TrimLeft(path.Clean("/"+p), "/")
	if f.root == "" {
		return p
	}
	if p == "" {
		return f.root
	}
	return f.root + "/" + p
}

func (f *s3FS) head(key string) (*s3.HeadObjectOutput, error) {
	out, err := f.client.HeadObject(context.Background(), &s3.HeadObjectInput{
		Bucket: aws.String(f.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		if isS3NotFound(err) {
			return nil, os.ErrNotExist
		}
		return nil, fmt.Errorf("billyfs: head %s: %w", key, err)
	}
	return out, nil
}

func (f *s3FS) get(key string) ([]byte, error) {
	out, err := f.client.GetObject(context.Background(), &s3.GetObjectInput{
		Bucket: aws.String(f.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		if isS3NotFound(err) {
			return nil, os.ErrNotExist
		}
		return nil, fmt.Errorf("billyfs: get %s: %w", key, err)
	}
	defer out.Body.Close()
	return io.ReadAll(out.Body)
}

// putBody uploads a byte slice to S3. If conditionExclusive is true, we
// add `If-None-Match: "*"` so the call fails with PreconditionFailed if
// the key already exists. This is the cross-container safety net for
// ref-lock files (`*.lock` writes during `git update-ref`) and for any
// other O_CREATE|O_EXCL semantics callers rely on.
func (f *s3FS) putBody(key string, body []byte, conditionExclusive bool) error {
	in := &s3.PutObjectInput{
		Bucket: aws.String(f.bucket),
		Key:    aws.String(key),
		Body:   bytes.NewReader(body),
	}
	if conditionExclusive {
		in.IfNoneMatch = aws.String("*")
	}
	_, err := f.client.PutObject(context.Background(), in)
	if err != nil {
		if conditionExclusive && isPreconditionFailed(err) {
			return os.ErrExist
		}
		return fmt.Errorf("billyfs: put %s: %w", key, err)
	}
	return nil
}

// deleteByPrefix wipes every object whose key starts with prefix. Used
// when a project's git is disabled (DELETE /repo).
func (f *s3FS) deleteByPrefix(ctx context.Context, prefix string) error {
	if prefix != "" && !strings.HasSuffix(prefix, "/") {
		prefix += "/"
	}
	var token *string
	for {
		out, err := f.client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
			Bucket:            aws.String(f.bucket),
			Prefix:            aws.String(prefix),
			ContinuationToken: token,
		})
		if err != nil {
			return fmt.Errorf("billyfs: list %s: %w", prefix, err)
		}
		for _, o := range out.Contents {
			if o.Key == nil {
				continue
			}
			if _, err := f.client.DeleteObject(ctx, &s3.DeleteObjectInput{
				Bucket: aws.String(f.bucket),
				Key:    o.Key,
			}); err != nil {
				return fmt.Errorf("billyfs: delete %s: %w", *o.Key, err)
			}
		}
		if out.IsTruncated == nil || !*out.IsTruncated {
			return nil
		}
		token = out.NextContinuationToken
	}
}

// listAnyKey returns true if any object under the prefix exists. Cheap
// existence check used to decide between Init and Open.
func (f *s3FS) listAnyKey(ctx context.Context, prefix string) (bool, error) {
	if prefix != "" && !strings.HasSuffix(prefix, "/") {
		prefix += "/"
	}
	var max int32 = 1
	out, err := f.client.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
		Bucket:  aws.String(f.bucket),
		Prefix:  aws.String(prefix),
		MaxKeys: &max,
	})
	if err != nil {
		return false, fmt.Errorf("billyfs: list-any %s: %w", prefix, err)
	}
	if len(out.Contents) > 0 {
		return true, nil
	}
	return false, nil
}

// --- file impl -----------------------------------------------------------

// s3File is the billy.File backing a single OpenFile call. Reads pull
// from an in-memory buffer that was seeded at open time; writes
// accumulate into the same buffer, with a single PutObject in Close()
// if the file was opened for write.
type s3File struct {
	fs   *s3FS
	key  string
	name string

	mu      sync.Mutex
	buf     *bytes.Buffer
	readPos int

	writable bool
	dirty    bool

	// writeOnce: if true, the eventual PutObject in Close() uses a
	// conditional `If-None-Match: "*"` so racing creators get
	// os.ErrExist. Set when the file was opened with O_CREATE|O_EXCL.
	writeOnce bool

	closed bool
}

func (f *s3File) Name() string { return f.name }

func (f *s3File) Read(p []byte) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.readPos >= f.buf.Len() {
		return 0, io.EOF
	}
	n := copy(p, f.buf.Bytes()[f.readPos:])
	f.readPos += n
	return n, nil
}

func (f *s3File) ReadAt(p []byte, off int64) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if off < 0 {
		return 0, errors.New("billyfs: negative offset")
	}
	src := f.buf.Bytes()
	if int(off) >= len(src) {
		return 0, io.EOF
	}
	n := copy(p, src[off:])
	if n < len(p) {
		return n, io.EOF
	}
	return n, nil
}

func (f *s3File) Write(p []byte) (int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.writable {
		return 0, errors.New("billyfs: file not opened for write")
	}
	n, err := f.buf.Write(p)
	if n > 0 {
		f.dirty = true
	}
	return n, err
}

// Seek supports SeekStart, SeekCurrent, SeekEnd for the read cursor.
// Writes always append to the buffer (we don't support seek-then-
// overwrite — go-git doesn't need it for the bare-repo ops we run).
func (f *s3File) Seek(offset int64, whence int) (int64, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var abs int64
	switch whence {
	case io.SeekStart:
		abs = offset
	case io.SeekCurrent:
		abs = int64(f.readPos) + offset
	case io.SeekEnd:
		abs = int64(f.buf.Len()) + offset
	default:
		return 0, fmt.Errorf("billyfs: invalid whence %d", whence)
	}
	if abs < 0 {
		return 0, errors.New("billyfs: negative seek")
	}
	f.readPos = int(abs)
	return abs, nil
}

func (f *s3File) Truncate(size int64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !f.writable {
		return errors.New("billyfs: file not opened for write")
	}
	cur := f.buf.Bytes()
	if int64(len(cur)) == size {
		return nil
	}
	var next []byte
	if int64(len(cur)) > size {
		next = append([]byte(nil), cur[:size]...)
	} else {
		next = append(append([]byte(nil), cur...), make([]byte, size-int64(len(cur)))...)
	}
	f.buf = bytes.NewBuffer(next)
	if f.readPos > len(next) {
		f.readPos = len(next)
	}
	f.dirty = true
	return nil
}

// Lock/Unlock are intentional no-ops. We don't advertise
// LockCapability and dotgit's setRefNorwfs path does not call them.
func (f *s3File) Lock() error   { return nil }
func (f *s3File) Unlock() error { return nil }

// Close flushes any pending writes to S3. Read-only handles are a
// no-op. The conditional-PUT path runs only when the file was opened
// with O_CREATE|O_EXCL.
func (f *s3File) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.closed {
		return nil
	}
	f.closed = true
	if !f.writable || !f.dirty {
		return nil
	}
	return f.fs.putBody(f.key, f.buf.Bytes(), f.writeOnce)
}

// --- helpers -------------------------------------------------------------

// s3FileInfo is the os.FileInfo we synthesize from S3 HEAD/list output.
type s3FileInfo struct {
	name string
	size int64
	mod  time.Time
	dir  bool
}

func (i *s3FileInfo) Name() string { return i.name }
func (i *s3FileInfo) Size() int64  { return i.size }
func (i *s3FileInfo) Mode() os.FileMode {
	if i.dir {
		return os.ModeDir | 0o755
	}
	return 0o644
}
func (i *s3FileInfo) ModTime() time.Time { return i.mod }
func (i *s3FileInfo) IsDir() bool        { return i.dir }
func (i *s3FileInfo) Sys() any           { return nil }

func synthDirInfo(name string) *s3FileInfo {
	return &s3FileInfo{name: name, dir: true}
}

// isS3NotFound returns true for the various NoSuchKey/NotFound shapes
// the S3 SDK can produce on missing objects. R2 + MinIO use slightly
// different codes, so we accept all the variants we've observed.
func isS3NotFound(err error) bool {
	if err == nil {
		return false
	}
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		switch apiErr.ErrorCode() {
		case "NoSuchKey", "NotFound", "404":
			return true
		}
	}
	return false
}

// isPreconditionFailed returns true when an If-None-Match: "*" PUT
// raced and another writer already created the key.
func isPreconditionFailed(err error) bool {
	if err == nil {
		return false
	}
	var apiErr smithy.APIError
	if errors.As(err, &apiErr) {
		if apiErr.ErrorCode() == "PreconditionFailed" {
			return true
		}
	}
	return false
}

// randomSuffix produces a short hex string for temp filenames.
func randomSuffix() string {
	var b [8]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}
