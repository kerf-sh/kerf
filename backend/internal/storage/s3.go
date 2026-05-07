package storage

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"

	"github.com/imranp/kerf/backend/internal/config"
)

// S3 is an S3 (or S3-compatible) Storage implementation.
type S3 struct {
	client    *s3.Client
	presigner *s3.PresignClient
	bucket    string
	publicURL string
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

// PublicURL returns S3_PUBLIC_URL_BASE/key, falling back to a virtual-hosted
// style URL if no base is configured.
func (s *S3) PublicURL(key string) string {
	if s.publicURL != "" {
		return s.publicURL + "/" + url.PathEscape(key)
	}
	return fmt.Sprintf("https://%s.s3.amazonaws.com/%s", s.bucket, url.PathEscape(key))
}
