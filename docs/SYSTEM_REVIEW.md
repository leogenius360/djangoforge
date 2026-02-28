# System Review

## Scope

This review summarizes the current backend system architecture, runtime components, data flow, security posture, and operational considerations based on repository configuration and code as of January 2026.

## Architecture Overview

- **Framework**: Django 5.2 with Django REST Framework (DRF) and drf-spectacular for OpenAPI.
- **Runtime**: WSGI (Gunicorn) and ASGI entrypoints under `config/`.
- **Application Structure**: Modular apps under `apps/` for clear separation of concerns:
  - `core`: shared utilities, base models, monitoring/health endpoints.
  - `accounts`: user identity and account lifecycle.
  - `authn`: authentication flows and credential types (MFA, WebAuthn, passwordless).
  - `authz`: authorization placeholder (roles/permissions planned).
  - `sessions`: session state, device/risk modeling.

## Key Components

### Configuration (`config/`)

- **Settings modules**: `base.py` provides shared settings; `dev.py`, `staging.py`, and `prod.py` override security, database, cache, and logging.
- **URL routing**:
  - Global endpoints in `config/urls.py` include admin, JWT, social auth, and Swagger.
  - API v1 endpoints in `config/api_urls.py` include health probes, metrics, and accounts.

### Core Platform (`apps/core`)

- **Health checks**: `HealthCheckView`, `LivenessProbeView`, `ReadinessProbeView`, `StartupProbeView`.
- **Monitoring**: `SystemMetricsView` (JSON metrics), optional Prometheus integration (`MetricsView`).

### Identity & Authentication

- **Accounts (`apps/accounts`)**: custom user model, profile, audit logging, and account lifecycle.
- **Authn (`apps/authn`)**: credential models (password, TOTP, WebAuthn, backup codes) and MFA flows.
- **Sessions (`apps/sessions`)**: session lifecycle, device tracking, and risk scoring.
- **Authz (`apps/authz`)**: placeholders for policy/roles.

### Infrastructure & Deployment

- **Docker**: `docker/Dockerfile` builds a Python 3.12 image, installs prod dependencies, collects static files, and runs Gunicorn.
- **Compose**: `docker-compose.yml` defines Postgres, optional Redis, and a web service.
- **CI**: GitHub Actions pipeline enforces linting, formatting, migrations, tests, and a Docker build on main.

## Data Flow Highlights

### Authentication & Session Flow

1. **Registration/Login**: `apps/accounts` provides registration and login endpoints; JWT issuance is handled via SimpleJWT endpoints in `config/urls.py`.
2. **MFA**: `apps/authn` manages MFA setup/verification (TOTP, WebAuthn, backup codes).
3. **Sessions**: session data is managed via `apps/sessions` and exposed through accounts session endpoints.
4. **Token Refresh**: refresh and verification endpoints are routed under `/api/auth/token/*`.

### Health & Monitoring

- **Health probes**: `/api/health/`, `/api/health/live/`, `/api/health/ready/`, `/api/health/startup/`.
- **Metrics**: `/api/metrics/` returns JSON metrics if `psutil` is installed. `/api/metrics/` exposes Prometheus metrics if `prometheus-client` is installed.

## Security Posture

- **Password hashing**: Argon2 preferred with PBKDF2/Bcrypt fallbacks.
- **JWT**: SimpleJWT configured with rotation and blacklist, 60-minute access tokens, 7-day refresh tokens.
- **Security headers**: HSTS, X-Frame-Options, and secure cookies enabled in production.
- **Auth backends**: Email/username/phone/passwordless plus social providers (Google, GitHub, Microsoft, Apple).
- **CORS**: configurable via environment variables; permissive in dev.

## Operational Considerations

- **Database**: Postgres in staging/production; SQLite default in development settings.
- **Caching**: local memory cache by default, Redis in staging if configured.
- **Logging**: console logging by default; file logging enabled for staging.
- **Static assets**: collected at build time, served via WhiteNoise in production.
- **Migrations**: CI runs `makemigrations --noinput` and `migrate --noinput`.

## Observability

- **Health endpoints** for uptime and readiness probes.
- **Metrics endpoints** for system and Prometheus-compatible metrics (optional dependencies).
- **Logs**: configured in `config/settings/base.py` with structured formatting.

## Risks & Gaps (Current State)

- **Authorization**: `apps/authz` is a placeholder; fine-grained authorization is not yet implemented.
- **Metrics dependencies**: Prometheus and system metrics rely on optional packages (`prometheus-client`, `psutil`).
- **Environment variance**: `dev.py` defaults to SQLite; ensure parity with Postgres-based staging/production for data-sensitive features.

## Recommendations

1. **Define authz policies**: Formalize role/permission models in `apps/authz`.
2. **Standardize metrics**: Decide on Prometheus vs JSON metrics and document required dependencies.
3. **Operational runbooks**: Expand deployment documentation with backup/restore procedures and incident playbooks.

## References

- `docs/ARCHITECTURE.md`
- `docs/PROJECT_SUMMARY.md`
- `docs/DEPLOYMENT.md`
- `docs/LOCAL_DEVELOPMENT.md`
