# Security Policy

BabbleBeaver is an open-source, provider-agnostic runtime for portable AI services and agents. Because it sits between applications and one or more LLM providers — often carrying API keys, user prompts, and provider credentials — its security posture matters more than a typical internal tool. This document describes how to report vulnerabilities, what's already been hardened, and what's still a known gap.

## Reporting a vulnerability

Please report security issues privately rather than opening a public GitHub issue.

- Email: **team@open.build**
- Include: a description of the issue, steps to reproduce, affected version/commit, and potential impact.
- We aim to acknowledge reports within 5 business days.

Do not include real credentials, customer data, or other sensitive material in a report — describe the issue and, if needed, provide redacted or synthetic examples.

## Supported versions

Security fixes are made against the `main` branch. There is no formal LTS/backport policy yet; if you're running a pinned older version, plan to track `main` or tagged releases for security-relevant updates.

## Secrets and credentials

- **Never commit real credentials, API keys, private keys, or certificates to this repository**, including in `.env`-style files, Dockerfiles, or scratch/test files. `.env`, `.env.prod.do`, and similar are gitignored — verify this before adding new environment files.
- **Never fetch credentials from a public or unauthenticated URL at build or runtime.** Provision service-account keys, tokens, and certs through your own secret store (DigitalOcean App Platform env vars, GCP Secret Manager, HashiCorp Vault, etc.) and inject them via environment variables or mounted secrets.
- If you discover credentials in this repository's history, report it immediately (see above) rather than opening a public issue that names the exposure.
- If a secret does leak into git history, treat it as compromised: rotate it at the source (cloud provider/console) first, then coordinate a history rewrite (`git filter-repo`) and force-push. A history rewrite alone does not un-expose a credential that was ever pushed publicly.

### Known historical exposure (resolved)

Earlier commits (added ~September 2025) included live Postgres client TLS credentials (`credentials/client-key.pem`, `client-cert.pem`, `server-ca.pem`) and a Dockerfile step that fetched a GCP service-account JSON from a public, unauthenticated `storage.googleapis.com` URL. Both have been remediated:

- The affected certificate/key was rotated at the database.
- The `.pem` files were purged from all branches' git history via `git filter-repo` and force-pushed.
- The Dockerfile no longer fetches any credentials at build time; GCP credentials are provided at runtime only, via `GOOGLE_APPLICATION_CREDENTIALS` or the authenticated `/upload_credentials` flow.

If you have an older local clone or fork, re-clone rather than pulling — the rewritten history is incompatible with the old commit graph.

## Authentication model

- **Admin routes** (`/admin/*`) require a bearer token, checked against `API_KEY` (env var) or a database-backed token via `token_manager`. Use `Authorization: Bearer <token>`.
- **`/chatbot`** (the primary inference endpoint) supports the same bearer-token check, gated by `REQUIRE_CHATBOT_AUTH` (default `false` for backward compatibility with existing integrations). **Operators should set `REQUIRE_CHATBOT_AUTH=true` once their calling application sends a valid token** — running it open in production is a known-risk default kept only for migration purposes. Track your rollout and flip this on; don't leave it permanently disabled.
- Admin login (`/admin/login`) compares username/password with plain `==`, which is not constant-time, and has no rate limiting or lockout. Treat the admin password as high-value, rotate it periodically, and consider putting `/admin/*` behind a network-level restriction (VPN, IP allowlist, or a reverse-proxy auth layer) in addition to the built-in check.
- A successful admin login currently returns the same shared, long-lived `API_KEY` as the session token rather than a scoped/expiring one. Anyone who obtains it (e.g. via browser storage or XSS on an admin page) has full API access until it's rotated.

## Data handling and provider calls

- `/chatbot` accepts free-form prompts and forwards them to whichever LLM provider is configured (locally, in your infrastructure, or a third-party API) — treat the content of prompts and responses as potentially sensitive, since it leaves your infrastructure whenever an external provider is enabled.
- There is no built-in payload size limit on `/chatbot`. Combined with unauthenticated access (if `REQUIRE_CHATBOT_AUTH` is left off), this can be used to drive up usage/cost against paid providers. If you enable a paid provider, set `REQUIRE_CHATBOT_AUTH=true` and consider a reverse-proxy rate limit.
- Review `CORS_ALLOWED_DOMAINS` before deploying: leaving it unset falls back to localhost-only origins (safe default), but setting it incorrectly (e.g. to `*`) combined with `allow_credentials=True` is a real CORS misconfiguration risk. Set it explicitly to your known frontend origin(s) in production.

## Dependency hygiene

`requirements.txt` pins several dependencies to specific versions. Some (e.g. `python-multipart`, `Jinja2`) are older than the latest patched releases in their lines. Run `pip-audit` or `safety check` periodically and before releases, and keep dependencies current — especially anything involved in parsing untrusted input (multipart form parsing, template rendering, JSON/YAML parsing).

## Deployment hardening checklist

- [ ] `DEBUG` unset or `false` in production (stack traces are otherwise returned to clients on unhandled errors).
- [ ] `CORS_ALLOWED_DOMAINS` set explicitly to known origins.
- [ ] `REQUIRE_CHATBOT_AUTH=true` once your integration sends tokens.
- [ ] `ADMIN_PASSWORD` and `API_KEY` rotated from defaults/placeholders, stored only in your secret manager or platform env vars — never in a committed file.
- [ ] `/admin/*` additionally restricted at the network layer where possible.
- [ ] Dependency versions checked against known CVEs before each release.

## Scope

This policy covers the BabbleBeaver application code in this repository. It does not cover the security posture of third-party LLM providers you choose to configure (OpenAI, Google, DigitalOcean, self-hosted models, etc.) — consult each provider's own security documentation for that.
