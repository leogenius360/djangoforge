# Django Backend

Clean, minimal Django REST API with PostgreSQL and JWT authentication.

## Features

- Django 5.2 + Django REST Framework
- JWT Authentication
- PostgreSQL Database
- API Documentation (Swagger/OpenAPI)
- Docker Support
- Production Ready

## Quick Start

### 1. Start Database

```bash
docker compose up db -d
```

### 2. Setup Environment

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements/dev.txt

# Copy environment file
cp .env.example .env
```

### 3. Run Migrations

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Start Server

```bash
python manage.py runserver
```

**Access:**
- API: http://localhost:8000/api/
- Admin: http://localhost:8000/admin/
- Docs: http://localhost:8000/api/docs/

## Environment Variables

Create `.env` file:

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://backend_user:backend_password@localhost:5432/backend

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

## API Endpoints

### Authentication

The backend supports **dual authentication** - both JWT tokens and cookie-based sessions:

#### JWT Token Authentication (Recommended for APIs)
- `POST /api/auth/register/` - Register
- `POST /api/auth/login/` - Login (get JWT tokens)
- `POST /api/auth/token/refresh/` - Refresh token
- `GET /api/auth/me/` - Current user

Use JWT tokens in the `Authorization` header:
```
Authorization: Bearer <access_token>
```

#### Cookie-Based Session Authentication (Web Apps)
- Uses Django session cookies automatically
- Sessions tracked in `AuthSession` model
- Supports concurrent sessions across devices

#### Session Management
- `GET /api/sessions/` - List active sessions
- `DELETE /api/sessions/` - Terminate all other sessions
- `DELETE /api/sessions/{id}/` - Terminate specific session

### Documentation
- `/api/docs/` - Swagger UI
- `/api/schema/` - OpenAPI schema

## Project Structure

```
backend/
├── apps/
│   ├── accounts/      # User authentication & profiles
│   ├── authn/         # Authentication credentials (MFA, TOTP, WebAuthn)
│   ├── authz/         # Authorization & permissions
│   ├── sessions/      # Session management (enterprise multi-session)
│   └── core/          # Core functionality & base models
├── config/            # Django settings
├── docker/            # Docker files
├── requirements/      # Python dependencies
├── .env.example       # Environment template
└── manage.py          # Django CLI
```

## Authentication Architecture

The backend implements a **dual authentication system**:

1. **JWT Tokens** - Stateless API authentication
   - Access tokens (1 hour lifetime)
   - Refresh tokens (7 days lifetime)
   - Token rotation and blacklisting

2. **Cookie Sessions** - Stateful web authentication
   - Django session cookies
   - AuthSession model tracking
   - Multi-device session management

Both methods work with the same `AuthSession` model for unified session tracking, auditing, and security controls (lock, suspend, revoke).

## Development

```bash
# Run tests
pytest

# Format code (using ruff)
ruff format .

# Lint code
ruff check .

# Auto-fix linting issues
ruff check --fix .

# Run all CI checks locally
make ci

# Type check (if using mypy)
mypy apps/

# Database shell
python manage.py dbshell
```

## Docker

```bash
# Full stack (db + web)
docker compose --profile full up

# Database only
docker compose up db
```

## Production

1. Set environment variables:
```bash
SECRET_KEY=<generate-secure-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://user:pass@host:5432/db
```

2. Build and deploy:
```bash
docker compose build
docker compose up -d
```

3. Run migrations:
```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic
```

## Documentation

- [Deployment Guide](docs/DEPLOYMENT.md)
- [System Review](docs/SYSTEM_REVIEW.md)

## License

MIT
