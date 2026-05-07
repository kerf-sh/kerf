package storage

import (
	"context"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"

	"github.com/imranp/kerf/backend/internal/config"
)

// S3 is an S3 (or S3-compatible) Storage implementation.
type S3 struct {
	client    *s3.Client
	presigner *s3.PresignClient
	bucket    string
	publicURL string // S3PublicURLBase (e.g. virtual-hosted bucket origin)
	cdnURL    string // CDNBaseURL (bunny.net Pull Zone, CloudFront, etc.)

	// In-flight multipart uploads, keyed by upload session id.
	//
	// NON-DURABLE: this lives only in process memory. A server restart
	// abandons in-flight uploads (the client has to start over from chunk
	// 0). Acceptable for v1 — moving this into Redis or DB is straightforward
	// once it becomes painful.
	mpMu      sync.Mutex
	multipart map[string]*s3MultipartState
}

type s3MultipartState struct {
	// uploadID is the value returned by S3's CreateMultipartUpload.
	uploadID string
	// dstKey is the eventual target key (where ConcatChunksTo will deliver
	// the assembled object). Captured at multipart-create time so the
	// frontend doesn't have to repeat it on every chunk.
	dstKey string
	// parts is the list of completed parts so far, keyed by index. S3
	// expects these in part-number order on CompleteMultipartUpload.
	parts map[int]s3types.CompletedPart
}

// NewS3 builds a Storage backed by S3.
func NewS3(cfg *config.Config) (*S3, error) {
	ctx := context.Background()
	loaders := []func(*awsconfig.LoadOptions) error{}
	if cfg.S3Region != "" {
		loaders = append(loaders, awsconfig.WithRegion(cfg.S3Region))
	}
	if cfg.S3AccessKeyID != "" && cfg.S3SecretAccessKey != "" {
		loaders = append(loaders, awsconfig.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(cfg.S3AccessKeyID, cfg.S3SecretAccessKey, ""),
		))
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, loaders...)
	if err != nil {
		return nil, fmt.Errorf("storage/s3: load config: %w", err)
	}

	clientOpts := []func(*s3.Options){}
	if cfg.S3Endpoint != "" {
		ep := cfg.S3Endpoint
		clientOpts = append(clientOpts, func(o *s3.Options) {
			o.BaseEndpoint = aws.String(ep)
			o.UsePathStyle = true
		})
	}
	client := s3.NewFromConfig(awsCfg, clientOpts...)
	presigner := s3.NewPresignClient(client)

	return &S3{
		client:    client,
		presigner: presigner,
		bucket:    cfg.S3Bucket,
		publicURL: strings.TrimRight(cfg.S3PublicURLBase, "/"),
		cdnURL:    strings.TrimRight(cfg.CDNBaseURL, "/"),
		multipart: make(map[string]*s3MultipartState),
	}, nil
}

// Put uploads an object.
func (s *S3) Put(ctx context.Context, key string, body io.Reader, contentType string, size int64) (PutResult, error) {
	if contentType == "" {
		contentType = guessContentType(key)
	}
	in := &s3.PutObjectInput{
		Bucket:      aws.String(s.bucket),
		Key:         aws.String(key),
		Body:        body,
		ContentType: aws.String(contentType),
	}
	if size > 0 {
		in.ContentLength = aws.Int64(size)
	}
	if _, err := s.client.PutObject(ctx, in); err != nil {
		return PutResult{}, fmt.Errorf("storage/s3: put: %w", err)
	}
	return PutResult{Key: key, Size: size, ContentType: contentType}, nil
}

// Get streams an object back from S3.
func (s *S3) Get(ctx context.Context, key string) (io.ReadCloser, string, error) {
	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, "", fmt.Errorf("storage/s3: get: %w", err)
	}
	ct := ""
	if out.ContentType != nil {
		ct = *out.ContentType
	} else {
		ct = guessContentType(key)
	}
	return out.Body, ct, nil
}

// Delete removes an object.
func (s *S3) Delete(ctx context.Context, key string) error {
	_, err := s.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return fmt.Errorf("storage/s3: delete: %w", err)
	}
	return nil
}

// SignedURL returns a presigned GET URL for the object.
func (s *S3) SignedURL(ctx context.Context, key string, ttl time.Duration) (string, error) {
	if ttl <= 0 {
		ttl = 15 * time.Minute
	}
	req, err := s.presigner.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(ttl))
	if err != nil {
		return "", err
	}
	return req.URL, nil
}

// PublicURL prefers a configured CDN base (bunny.net Pull Zone, CloudFront,
// etc.) over the bucket's own public URL. When neither is set we fall back
// to a virtual-hosted-style S3 URL — which only works if the bucket itself
// is publicly readable. Most cloud deploys should set CDNBaseURL.
//
// Cache-buster: when updatedAt is non-zero we append "?v=<unix>" so a
// fresh upload busts CDN edge caches without an explicit purge.
func (s *S3) PublicURL(key string, updatedAt time.Time) string {
	base := ""
	switch {
	case s.cdnURL != "":
		base = s.cdnURL + "/" + escapeKey(key)
	case s.publicURL != "":
		base = s.publicURL + "/" + escapeKey(key)
	default:
		base = fmt.Sprintf("https://%s.s3.amazonaws.com/%s", s.bucket, escapeKey(key))
	}
	if !updatedAt.IsZero() {
		return base + "?v=" + strconv.FormatInt(updatedAt.Unix(), 10)
	}
	return base
}

// --- Chunked upload helpers ------------------------------------------------
//
// We map the abstract chunked-upload API onto S3's native multipart upload.
// The first PutChunk call lazily kicks off CreateMultipartUpload using a
// temp object key under `_uploads/<uploadKey>`; subsequent PutChunks call
// UploadPart. ConcatChunksTo calls CompleteMultipartUpload, which copies the
// assembled object to the requested final key (S3 semantics — the multipart
// target IS the final key, so we issue a server-side copy after completion
// to land it at dstKey, then delete the temp). DeleteUpload calls
// AbortMultipartUpload.

func (s *S3) tempKey(uploadKey string) string {
	return "_uploads/" + uploadKey
}

func (s *S3) ensureMultipart(ctx context.Context, uploadKey string) (*s3MultipartState, error) {
	s.mpMu.Lock()
	defer s.mpMu.Unlock()
	if st, ok := s.multipart[uploadKey]; ok {
		return st, nil
	}
	tempKey := s.tempKey(uploadKey)
	out, err := s.client.CreateMultipartUpload(ctx, &s3.CreateMultipartUploadInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(tempKey),
	})
	if err != nil {
		return nil, fmt.Errorf("storage/s3: create multipart: %w", err)
	}
	st := &s3MultipartState{
		uploadID: aws.ToString(out.UploadId),
		dstKey:   tempKey,
		parts:    make(map[int]s3types.CompletedPart),
	}
	s.multipart[uploadKey] = st
	return st, nil
}

func (s *S3) lookupMultipart(uploadKey string) *s3MultipartState {
	s.mpMu.Lock()
	defer s.mpMu.Unlock()
	return s.multipart[uploadKey]
}

func (s *S3) forgetMultipart(uploadKey string) {
	s.mpMu.Lock()
	defer s.mpMu.Unlock()
	delete(s.multipart, uploadKey)
}

// PutChunk uploads chunk #chunkIndex as an S3 part. Part numbers are 1-based
// in S3 — we add one to the 0-indexed chunk index on the wire.
func (s *S3) PutChunk(ctx context.Context, uploadKey string, chunkIndex int, body io.Reader) error {
	if chunkIndex < 0 {
		return fmt.Errorf("storage/s3: negative chunk index")
	}
	st, err := s.ensureMultipart(ctx, uploadKey)
	if err != nil {
		return err
	}
	partNumber := int32(chunkIndex + 1)
	out, err := s.client.UploadPart(ctx, &s3.UploadPartInput{
		Bucket:     aws.String(s.bucket),
		Key:        aws.String(st.dstKey),
		UploadId:   aws.String(st.uploadID),
		PartNumber: aws.Int32(partNumber),
		Body:       body,
	})
	if err != nil {
		return fmt.Errorf("storage/s3: upload part %d: %w", chunkIndex, err)
	}
	s.mpMu.Lock()
	st.parts[chunkIndex] = s3types.CompletedPart{
		ETag:       out.ETag,
		PartNumber: aws.Int32(partNumber),
	}
	s.mpMu.Unlock()
	return nil
}

// ListChunks returns the chunk indices we've recorded as uploaded. Pulled
// from the in-memory part map.
func (s *S3) ListChunks(ctx context.Context, uploadKey string) ([]int, error) {
	st := s.lookupMultipart(uploadKey)
	if st == nil {
		return []int{}, nil
	}
	s.mpMu.Lock()
	out := make([]int, 0, len(st.parts))
	for idx := range st.parts {
		out = append(out, idx)
	}
	s.mpMu.Unlock()
	sort.Ints(out)
	return out, nil
}

// ConcatChunksTo finishes the multipart upload, then copies the assembled
// object to the requested destination key (since multipart writes to a fixed
// key chosen at create time). Returns the total byte count via HeadObject.
func (s *S3) ConcatChunksTo(ctx context.Context, uploadKey string, dstKey string) (int64, error) {
	st := s.lookupMultipart(uploadKey)
	if st == nil {
		return 0, fmt.Errorf("storage/s3: no multipart state for upload %q (server restart?)", uploadKey)
	}
	s.mpMu.Lock()
	indices := make([]int, 0, len(st.parts))
	for idx := range st.parts {
		indices = append(indices, idx)
	}
	sort.Ints(indices)
	parts := make([]s3types.CompletedPart, 0, len(indices))
	for _, idx := range indices {
		parts = append(parts, st.parts[idx])
	}
	tempKey := st.dstKey
	uploadID := st.uploadID
	s.mpMu.Unlock()

	if len(parts) == 0 {
		return 0, fmt.Errorf("storage/s3: no parts uploaded for %q", uploadKey)
	}

	if _, err := s.client.CompleteMultipartUpload(ctx, &s3.CompleteMultipartUploadInput{
		Bucket:          aws.String(s.bucket),
		Key:             aws.String(tempKey),
		UploadId:        aws.String(uploadID),
		MultipartUpload: &s3types.CompletedMultipartUpload{Parts: parts},
	}); err != nil {
		return 0, fmt.Errorf("storage/s3: complete multipart: %w", err)
	}

	// Server-side copy to the final key, then delete the temp.
	copySource := s.bucket + "/" + tempKey
	if _, err := s.client.CopyObject(ctx, &s3.CopyObjectInput{
		Bucket:     aws.String(s.bucket),
		Key:        aws.String(dstKey),
		CopySource: aws.String(copySource),
	}); err != nil {
		return 0, fmt.Errorf("storage/s3: copy assembled object: %w", err)
	}
	_, _ = s.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(tempKey),
	})

	// Pull final size via HeadObject — caller relies on this for the files row.
	head, err := s.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(dstKey),
	})
	if err != nil {
		return 0, fmt.Errorf("storage/s3: head assembled object: %w", err)
	}
	s.forgetMultipart(uploadKey)
	if head.ContentLength != nil {
		return *head.ContentLength, nil
	}
	return 0, nil
}

// DeleteUpload aborts the multipart upload (if any). Idempotent.
func (s *S3) DeleteUpload(ctx context.Context, uploadKey string) error {
	st := s.lookupMultipart(uploadKey)
	if st == nil {
		return nil
	}
	_, err := s.client.AbortMultipartUpload(ctx, &s3.AbortMultipartUploadInput{
		Bucket:   aws.String(s.bucket),
		Key:      aws.String(st.dstKey),
		UploadId: aws.String(st.uploadID),
	})
	s.forgetMultipart(uploadKey)
	if err != nil {
		// Don't surface AWS errors here — the goal of DeleteUpload is to
		// best-effort wipe state. The S3 lifecycle rule will eventually
		// reap any orphans.
		return fmt.Errorf("storage/s3: abort multipart: %w", err)
	}
	return nil
}
