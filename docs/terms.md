# Terms of Service

**Effective date:** 2026-05-15

These terms govern your use of the **hosted Kerf service at `kerf.sh`**
(the "Service"). If you run Kerf locally from the open-source code, the
[MIT License](https://github.com/kerf-sh/kerf/blob/main/LICENSE) applies
to that copy and these terms do not.

By creating an account or using the Service, you agree to these terms.

## 1. The Service

Kerf provides a chat-driven CAD platform — mechanical, electronics,
drawings, BIM — running on our infrastructure. We bill for storage,
LLM credits, and worker compute as set out on the
[Pricing page](https://kerf.sh/pricing). The full software is MIT-licensed
and available at [github.com/kerf-sh/kerf](https://github.com/kerf-sh/kerf)
if you'd rather self-host.

## 2. Accounts

- You must be 16 or older to create an account.
- You're responsible for keeping your password and API tokens secret. If
  a token is compromised, rotate it immediately from your Profile page.
- One person, one account. Workspaces are for teams; team members each
  have their own account.
- Provide accurate billing information.

## 3. Acceptable use

You agree not to use the Service to:

- Violate any law or regulation, or another person's rights.
- Upload malware, exploit code targeting other users, or content
  designed to defraud.
- Send unsolicited bulk messages, spam, or phishing through any Kerf
  feature.
- Scrape, mirror, or resell the Service's content without our written
  consent (your own projects are yours to export, of course — see
  Section 6).
- Reverse-engineer or stress-test our infrastructure beyond ordinary use.
  If you want to run a load test that goes beyond your tier's quotas,
  email us first.
- Run automated workloads at a scale that disrupts other users. The
  per-API-token daily spend cap and per-user monthly limits are there
  to bound this; intentionally trying to evade them is grounds for
  suspension.

We reserve the right to suspend or terminate accounts that violate
these rules.

## 4. Content

**Your content stays yours.** You retain all rights to projects, files,
sketches, designs, and chat history you create on Kerf. By using the
Service, you grant us a limited license to store, process, and display
your content as needed to operate the Service (e.g. render your projects,
back up your data, send your chat messages to the LLM provider you
chose).

**Public Workshop content.** When you publish a project to the public
Workshop, you grant other users a worldwide, non-exclusive, royalty-free
license to view, fork, and modify your project in the Workshop. You can
unpublish at any time, but copies forked before unpublishing remain with
the user who forked them. We don't claim ownership.

**Content rules:** don't publish content that infringes intellectual
property, contains malware, depicts illegal activity, or harasses other
users. We may remove content that violates these rules.

## 5. Payments and billing

- Prices are displayed on [kerf.sh/pricing](https://kerf.sh/pricing).
- The hosted service settles in your card's native currency via
  [Paystack](https://paystack.com). Displayed USD prices are converted
  at the FX rate active at billing time.
- Subscription tiers (Studio $9/mo, Pro $29/mo) bundle a monthly credit
  allowance for LLM tokens at our provider cost (no markup). Overage
  debits a wallet balance you top up via Paystack.
- **At-cost token pricing**: we charge the raw provider rate plus a 5%
  payment-processing fee on the overage portion. No hidden markup.
- **Storage overage**: $0.30/GB-month past your tier's included storage,
  prorated daily.
- **Worker compute overage**: $0.10/minute past your tier's free quota
  for FEM / topo / autoroute jobs.
- **Refunds**: we don't offer refunds for partial-month subscriptions or
  unused credits, but we'll work with you in good faith on edge cases
  (e.g. duplicate top-up, our outage during your subscription).
- **Cancellation**: you can cancel a subscription any time. Already-paid
  subscription periods stay active until they expire; we don't auto-renew
  if you cancel.

## 6. Data export and account deletion

- Every project has a "Download project" button that exports all your
  files as a zip.
- You can delete your account from `Profile → Delete Account`. Your
  account data, private projects, and chat history are wiped within 30
  days. Public Workshop publishes stay live unless you unpublish them
  first.

## 7. Service availability

We aim for high availability but don't guarantee it. The Service is
provided **"as is"** without uptime guarantees in the standard tier.
Enterprise customers can negotiate an SLA — contact
[hello@kerf.sh](mailto:hello@kerf.sh).

We may schedule downtime for maintenance and will give reasonable notice
where possible (email + status page).

## 8. Third-party providers

Kerf uses third-party services to deliver some features:

- **LLM providers** (Anthropic, OpenAI, Google, DeepSeek, MiniMax) —
  your chat content is sent to whichever you choose.
- **Paystack** — payment processing.
- **Resend** — transactional email.
- **Tigris** / **fly.io** — hosting and storage.
- **GitHub** (if you connect git sync) — your project code mirrors to
  the repo you authorize.

These third parties operate under their own terms. We've chosen each
based on privacy and reliability; full details in our
[Privacy Policy](./privacy.md).

## 9. Liability

To the maximum extent permitted by law:

- The Service is provided "as is" without warranties of any kind.
- We're not liable for indirect, incidental, special, consequential, or
  punitive damages, or lost profits, even if we've been advised of the
  possibility.
- Our total liability for any claim arising from the Service is limited
  to the amount you paid us in the 12 months before the claim, or
  USD 100, whichever is greater.

Nothing in these terms limits liability for fraud, gross negligence,
or other liability that can't be limited by law.

## 10. Changes to these terms

We may update these terms. If we make a change that materially affects
your rights or what we charge, we'll email you at the address on your
account and post a notice in the app at least 30 days before the change
takes effect. Continued use after that date means you accept the change.

Minor clarifications go in without notice; the change history is visible
on GitHub.

## 11. Governing law

These terms are governed by the laws of the Republic of South Africa.
Disputes are resolved in the courts of Durban, KwaZulu-Natal, unless
you're a consumer in a jurisdiction (EU, UK, etc.) where local consumer
law requires a different forum.

The South African Consumer Protection Act applies where relevant.

## 12. Contact

- **Support**: [support@kerf.sh](mailto:support@kerf.sh)
- **Privacy**: [privacy@kerf.sh](mailto:privacy@kerf.sh)
- **Security**: [security@kerf.sh](mailto:security@kerf.sh) (see
  [SECURITY.md](https://github.com/kerf-sh/kerf/blob/main/SECURITY.md))
- **Legal / business**: [hello@kerf.sh](mailto:hello@kerf.sh)

Postal address available on request.
