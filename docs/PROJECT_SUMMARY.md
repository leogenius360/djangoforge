# Project Summary

## Overview

**Project Name:** Brainbox Research Institute Backend  
**Type:** Django REST API  
**Purpose:** Backend API for research institute management  
**Status:** Development  
**Last Updated:** January 17, 2026

## Technology Stack

### Core Framework
- **Django 5.2** - Web framework
- **Django REST Framework 3.16** - API framework
- **Python 3.12.3** - Programming language

### Database
- **PostgreSQL 16** - Primary database
- **psycopg[binary]** - PostgreSQL adapter

### Authentication
- **djangorestframework-simplejwt** - JWT authentication
- Access tokens: 5 minutes
- Refresh tokens: 7 days

### Infrastructure
- **Docker & Docker Compose** - Containerization
- **Gunicorn** - WSGI server for production
- **WhiteNoise** - Static file serving

### Development Tools
- **Ruff** - Linting and formatting
- **pytest** - Testing framework
- **python-dotenv** - Environment management

## Project Structure

```
backend/
├── apps/                      # Django applications
│   ├── accounts/              # User authentication & management
│   │   ├── models.py          # UserAccount model
│   │   ├── views.py           # Auth endpoints
│   │   ├── admin.py           # Admin interface
│   │   └── migrations/        # Database migrations
│   └── core/                  # Core utilities
│       ├── models.py          # Base models
│       ├── views.py           # Health checks
│       └── management/        # Management commands
│
├── config/                    # Project configuration
│   ├── settings/
│   │   ├── base.py            # Shared settings
│   │   ├── development.py     # Dev settings
│   │   └── production.py      # Prod settings
│   ├── urls.py                # URL routing
│   ├── wsgi.py                # WSGI config
│   └── asgi.py                # ASGI config
│
├── docker/                    # Docker configuration
│   ├── Dockerfile             # Docker image
│   └── entrypoint.sh          # Container entrypoint
│
├── docs/                      # Documentation
│   ├── DEPLOYMENT.md          # Deployment guide
│   ├── LOCAL_DEVELOPMENT.md   # Local setup guide
│   └── PROJECT_SUMMARY.md     # This file
│
├── requirements/              # Python dependencies
│   ├── base.txt               # Core dependencies
│   ├── dev.txt                # Development tools
│   └── prod.txt               # Production packages
│
├── scripts/                   # Utility scripts
│   ├── setup_dev.py           # Dev environment setup
│   └── validate_env.py        # Environment validation
│
├── .env                       # Environment variables (local)
├── .env.example               # Environment template
├── docker-compose.yml         # Docker orchestration
├── manage.py                  # Django management
├── pyproject.toml             # Ruff configuration
└── pytest.ini                 # Pytest configuration
```

## Applications

### 1. Accounts (`apps/accounts/`)
**Purpose:** User authentication and account management

**Features:**
- Custom UserAccount model
- JWT-based authentication
- User registration/login
- Password reset functionality
- User profile management

**API Endpoints:**
- `/api/auth/register/` - User registration
- `/api/auth/login/` - User login (JWT)
- `/api/auth/logout/` - User logout
- `/api/auth/refresh/` - Refresh JWT token
- `/api/auth/me/` - Current user profile

### 2. Core (`apps/core/`)
**Purpose:** Shared utilities and base functionality

**Features:**
- Base model classes
- Health check endpoints
- Common utilities
- Management commands

**API Endpoints:**
- `/api/health/` - Health check
- `/api/docs/` - API documentation (Swagger)

## Configuration

### Environment Variables

**Required:**
- `SECRET_KEY` - Django secret key (50+ characters)
- `DATABASE_URL` - PostgreSQL connection string
- `DJANGO_SETTINGS_MODULE` - Settings module to use

**Optional:**
- `DEBUG` - Debug mode (default: False)
- `ALLOWED_HOSTS` - Allowed hostnames (comma-separated)
- `CORS_ALLOWED_ORIGINS` - CORS allowed origins

### Settings Modules

1. **base.py** - Shared settings for all environments
2. **development.py** - Local development settings
3. **production.py** - Production deployment settings

## Development Workflow

### Initial Setup
```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements/dev.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your values

# 4. Start database
docker compose up db -d

# 5. Run migrations
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser

# 7. Start development server
python manage.py runserver
```

### Common Commands

```bash
# Run development server
python manage.py runserver

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Run tests
pytest

# Format code
ruff format .

# Lint code
ruff check .

# Create superuser
python manage.py createsuperuser
```

## API Documentation

- **Swagger UI:** http://localhost:8000/api/docs/
- **ReDoc:** http://localhost:8000/api/redoc/
- **Admin Panel:** http://localhost:8000/admin/

## Database Schema

### User Model
```
accounts_user
├── id (UUID, Primary Key)
├── email (EmailField, Unique)
├── username (CharField, Optional)
├── phone_number (CharField, Optional)
├── status (CharField) - ACTIVE, INACTIVE, SUSPENDED, etc.
├── display_name (CharField) - Cached from profile
├── is_superuser (BooleanField)
├── is_staff (BooleanField, Property)
├── is_active (BooleanField, Property)
├── date_joined (DateTimeField, Property)
├── last_login (DateTimeField)
├── last_activity_at (DateTimeField)
├── email_verified_at (DateTimeField)
├── phone_verified_at (DateTimeField)
├── passwordless_enabled (BooleanField)
└── profile (OneToOne → UserProfile)
    ├── given_name (CharField)
    ├── family_name (CharField)
    ├── middle_name (CharField, Optional)
    ├── nickname (CharField, Optional)
    └── bio (TextField, Optional)
```

## Security Features

- JWT authentication with short-lived tokens
- HTTPS enforcement in production
- CORS configuration
- CSRF protection
- Secure password hashing (PBKDF2)
- Security headers (HSTS, X-Content-Type-Options, etc.)
- SQL injection protection (ORM)
- XSS protection

## Performance Considerations

- Database connection pooling
- Static file compression (WhiteNoise)
- Gunicorn with multiple workers
- Database query optimization
- Pagination for list endpoints

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apps --cov-report=html

# Run specific test file
pytest apps/accounts/tests.py

# Run specific test
pytest apps/accounts/tests.py::TestUserModel::test_create_user
```

## Deployment

### Production Checklist
- [ ] Set `DEBUG=False`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set strong `SECRET_KEY`
- [ ] Use managed PostgreSQL
- [ ] Enable HTTPS
- [ ] Configure CORS
- [ ] Set up monitoring
- [ ] Configure backups
- [ ] Update dependencies

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

## Monitoring

**Health Check:** `/api/health/`
- Returns 200 OK when system is healthy
- Checks database connectivity
- Can be used for load balancer health checks

## Future Enhancements

- [ ] Rate limiting on API endpoints
- [ ] Celery for async tasks
- [ ] Redis for caching
- [ ] Email notifications
- [ ] File upload handling
- [ ] Advanced search capabilities
- [ ] API versioning
- [ ] WebSocket support (if needed)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.

## License

Proprietary - Brainbox Research Institute Ltd

## Contact

**Organization:** Brainbox Research Institute Ltd  
**Repository:** https://github.com/Brainbox-Research-Institute-Ltd/backend

---

*This document is automatically generated and should be updated when significant changes are made to the project.*
