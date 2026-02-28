# GitHub Copilot Coding Agent Instructions (BBRI Backend)

You are working in a Django REST API backend (Django 5.x + DRF) with PostgreSQL, JWT auth, Docker support, and CI that enforces formatting, linting, and tests.

The project includes **DjangoForge** (`djangoforge/`), an enterprise extension layer that provides a Forge API Contract, DRF/Ninja adapters, an outbox-based event system, auth policy layer, observability middleware, and CI-enforceable checks.

## Prime directive

**Every change must keep CI green.** Before finishing any task, ensure:

- formatting passes
- linting passes (Ruff)
- tests pass (pytest)
- typing passes if CI runs mypy
- migrations are correct (if models changed)

If anything fails, fix it before concluding.

---

## Read these first (local repo files)

Always inspect and follow the project’s canonical configuration:

1. `pyproject.toml` (tool config: ruff/black/mypy/pytest/etc.)
2. `.github/workflows/ci.yml` (the source of truth for what CI runs)
3. `README.md` (local dev commands, env vars, Docker usage)
4. `config/` Django settings (especially test/prod differences)
5. `apps/` conventions and architecture
6. `djangoforge/` package (Forge API contract, adapters, events, auth, middleware, checks)

Do not guess versions/flags when they are defined in these files.

---

## CI parity (run what CI runs)

### Required local checks (run in this order)

Use the exact commands and options from CI if present. If CI doesn’t specify exact commands, default to these:

1. **Format**

- If the repo uses Ruff formatter:
  - `ruff format .`
- If the repo uses Black:
  - `black .`

2. **Lint**

- `ruff check .`
- If CI expects autofix in dev, apply it and re-run:
  - `ruff check --fix .`

3. **Tests**

- `pytest`

4. **Type check** (only if CI includes it)

- `mypy apps/`

### Definition of done

A task is not done until **all applicable checks** pass locally in the same way CI runs them.

---

## Python/Django engineering standards

### Code style

- Follow `pyproject.toml` settings (line length, target version, select/ignore rules).
- Prefer small, readable functions.
- Add docstrings for public modules/classes/methods when it improves clarity (this project values documentation).

### Imports

- Keep imports sorted as configured (Ruff will enforce).
- Avoid circular imports; prefer local imports inside functions when needed.

### Type hints

- Add type hints where practical, especially in reusable utilities, querysets/managers, service functions.
- Don’t add noisy types that reduce readability; follow mypy strictness as configured.

---

## Django project conventions (must-follow)

### App boundaries

- Respect the layered app structure under `apps/`:
  - `apps/accounts/` for user/account domain
  - `apps/authn/`, `apps/authz/`, `apps/sessions/` if present (security platform layer)
  - `apps/core/` for shared utilities (base models, managers, querysets, mixins)
- Avoid leaking domain logic into `core` unless it’s truly cross-cutting.

### DjangoForge package (`djangoforge/`)

- **Forge API Contract** (`djangoforge/api/`): framework-agnostic types (RequestContext, ProblemDetail, PaginationSpec, FilterSpec, SortSpec, ApiResponse) and policy hooks (AuthPolicy, PermissionPolicy, RateLimitPolicy, IdempotencyPolicy).
- **DRF adapter** (`djangoforge/adapters/drf/`): ForgeAPIView, ForgeViewSet, ForgeSerializer, ProblemDetail exception handler, ForgeAuthentication.
- **Ninja adapter** (`djangoforge/adapters/ninja/`): forge_router, ForgeNinjaAuth, ProblemDetail exception handler.
- **Events / Outbox** (`djangoforge/events/`): OutboxEvent model, EventBus, DomainEvent (CloudEvents envelope), broker backends.
- **Auth** (`djangoforge/auth/`): ForgeAuthPolicy reads trusted proxy headers and produces RequestContext/Principal.
- **Middleware** (`djangoforge/middleware/`): CorrelationIdMiddleware, SecurityHeadersMiddleware.
- **Checks** (`djangoforge/checks/`): Django checks framework integration (forge.W001-W004).
- **Settings** (`djangoforge/settings.py`): FORGE dict in Django settings with validated defaults.
- **Management commands**: `forge_check`, `publish_outbox`.

When building new API endpoints:
- Prefer using Forge contract types (RequestContext, ProblemDetail) for consistency.
- Use the outbox pattern for domain events: write OutboxEvent in the same transaction as state changes.
- Register endpoint metadata with SchemaRegistry for OpenAPI enforcement.

### Models & database

- If you change models, you must:
  - create migrations (`python manage.py makemigrations`)
  - ensure they apply cleanly (`python manage.py migrate`)
  - update indexes/constraints when needed for correctness and query performance
- If you introduce timestamps/status fields, keep them consistent and enforce invariants with:
  - model constraints (DB-level when possible)
  - `save()` maintenance only when safe (avoid surprising side effects)
  - queryset helpers for bulk operations (ensure bulk updates preserve invariants)

### Managers/QuerySets

- Prefer centralized base querysets/managers from `apps/core/models/` (or equivalent).
- If soft delete exists, ensure `.with_deleted()` / `.hard_delete()` / `.restore()` behaviors are consistent across all models.

### DRF & API

- Keep endpoints under `/api/v1/...` as per routing conventions.
- Use serializers for validation; avoid “manual dict validation” in views.
- Prefer ViewSets + routers where consistent with the codebase.
- Ensure authentication/permissions align with JWT auth setup.
- If you add/modify endpoints, update OpenAPI/Swagger integration if required by the project.
- For new endpoints, emit ProblemDetail-shaped errors and register with SchemaRegistry.

---

## Security and JWT rules

- Never log secrets, tokens, passwords, or raw credentials.
- Use Django’s password hashing and DRF best practices.
- Validate permissions carefully on any user-scoped resource.
- If you change auth/session behavior, add/adjust tests for:
  - token issuance/refresh
  - revocation/logout semantics
  - protected route access

---

## Testing rules (pytest + Django)

- Add tests for any new behavior and bug fixes.
- Prefer API-level tests (DRF client) for endpoints.
- Keep tests deterministic:
  - no reliance on external services
  - freeze time when needed
- Use factories/fixtures if the repo already has them; don’t introduce a new framework unless necessary.
- Tests for `djangoforge/` are in `djangoforge/tests/` and discovered via `pytest.ini` testpaths.

---

## Environment & Docker

- Respect `.env.example` keys.
- Do not hardcode environment-specific values.
- If Dockerfiles/compose are updated, ensure:
  - `docker compose up db -d` still works
  - full stack profile still boots if configured

---

## Documentation & maintainability

- If you introduce new commands, env vars, or setup steps, update `README.md`.
- Keep docstrings up to date when changing behavior (especially in base models/managers).

---

## Output expectations for the agent

When delivering a change:

1. Summarize what changed and why.
2. List the exact commands you ran (format/lint/test/typecheck) and their status.
3. Mention any migrations added.
4. Call out any follow-up work explicitly (only if truly optional).

**Do not claim CI passes unless you ran the same checks CI runs.**
