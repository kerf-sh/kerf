//go:build cloud
// +build cloud

package email

import (
	"context"
	"fmt"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/sesv2"
	sestypes "github.com/aws/aws-sdk-go-v2/service/sesv2/types"
)

// sesProvider sends through AWS SES v2.
//
// Credential resolution mirrors the pattern in backend/internal/storage/s3.go:
//
//   - If APIKey + SMTPPassword are present in the encrypted blob, they're
//     used as the access key id + secret access key (the schema reuses
//     SMTPUsername/Password slots so we don't need an extra column;
//     SMTP creds are repurposed because the SES v2 API uses sigv4 not
//     SMTP creds — only the field names overlap).
//   - Otherwise, the default AWS credential chain is used. This is the
//     preferred path on EC2/ECS/EKS where instance roles cover IAM.
//
// FromEmail is required and must be a verified identity in SES (either
// the address itself or its parent domain).
type sesProvider struct {
	client    *sesv2.Client
	from      string
	fromEmail string // bare address for the From header attribute
	fromName  string
}

func newSES(creds Credentials) (*sesProvider, error) {
	if creds.FromEmail == "" {
		return nil, fmt.Errorf("%w: ses from_email required", ErrInvalidCredentials)
	}
	if creds.Region == "" {
		return nil, fmt.Errorf("%w: ses region required", ErrInvalidCredentials)
	}
	ctx := context.Background()
	loaders := []func(*awsconfig.LoadOptions) error{
		awsconfig.WithRegion(creds.Region),
	}
	// Static creds path. The SDK validates non-empty access key + secret;
	// either both must be set or both must be empty.
	if creds.APIKey != "" && creds.SMTPPassword != "" {
		loaders = append(loaders, awsconfig.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(creds.APIKey, creds.SMTPPassword, ""),
		))
	}
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, loaders...)
	if err != nil {
		return nil, fmt.Errorf("ses: load aws config: %w", err)
	}
	from := creds.FromEmail
	if creds.FromName != "" {
		from = fmt.Sprintf("%s <%s>", creds.FromName, creds.FromEmail)
	}
	return &sesProvider{
		client:    sesv2.NewFromConfig(awsCfg),
		from:      from,
		fromEmail: creds.FromEmail,
		fromName:  creds.FromName,
	}, nil
}

func (p *sesProvider) Name() string { return ProviderSES }

func (p *sesProvider) Send(ctx context.Context, msg Message) error {
	from := msg.From
	if from == "" {
		from = p.from
	}

	body := &sestypes.Body{}
	if msg.HTML != "" {
		body.Html = &sestypes.Content{
			Data:    aws.String(msg.HTML),
			Charset: aws.String("UTF-8"),
		}
	}
	if msg.Text != "" {
		body.Text = &sestypes.Content{
			Data:    aws.String(msg.Text),
			Charset: aws.String("UTF-8"),
		}
	}

	in := &sesv2.SendEmailInput{
		FromEmailAddress: aws.String(from),
		Destination: &sestypes.Destination{
			ToAddresses: []string{msg.To},
		},
		Content: &sestypes.EmailContent{
			Simple: &sestypes.Message{
				Subject: &sestypes.Content{
					Data:    aws.String(msg.Subject),
					Charset: aws.String("UTF-8"),
				},
				Body: body,
			},
		},
	}
	if msg.ReplyTo != "" {
		in.ReplyToAddresses = []string{msg.ReplyTo}
	}
	for k, v := range msg.Tags {
		in.EmailTags = append(in.EmailTags, sestypes.MessageTag{
			Name:  aws.String(k),
			Value: aws.String(v),
		})
	}

	if _, err := p.client.SendEmail(ctx, in); err != nil {
		return fmt.Errorf("ses: SendEmail: %w", err)
	}
	return nil
}
