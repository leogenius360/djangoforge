# Local Development Guide

## Quick Start

### Option 1: Using Setup Script (Recommended)

```bash
# Run the automated setup script
python3 scripts/setup_dev.py
```

This script will:
- Check prerequisites
- Create `.env` file from `.env.example`
- Set up Python virtual environment
- Install all dependencies
- Start database and Redis (via Docker)
- Run migrations
- Offer to create a superuser
- Install pre-commit hooks

### Option 2: Manual Setup

#### Prerequisites

- Python 3.12+
- PostgreSQL 16+ (or use Docker)
- Redis 7+ (or use Docker)
- Docker & Docker Compose (recommended)

#### Step-by-Step Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements/dev.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your local configuration
   ```

5. **Start database and Redis (using Docker)**
   ```bash
   docker compose -f docker-compose.dev.yml up -d db redis
   ```

   Or if you have local installations:
   - Ensure PostgreSQL is running on port 5432
   - Ensure Redis is running on port 6379
   - Update `DATABASE_URL` and `REDIS_URL` in `.env`

6. **Run migrations**
   ```bash
   python manage.py migrate
   ```

7. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

8. **Run development server**
   ```bash
   python manage.py runserver
   ```

9. **Access the application**
   - Application: http://localhost:8000/
   - Admin: http://localhost:8000/admin/
   - API Docs: http://localhost:8000/api/docs/
   - ReDoc: http://localhost:8000/api/redoc/

## Development with Docker

### Full Stack with Docker Compose

Start all services (web, database, Redis, Celery, MailHog):

```bash
docker compose -f docker-compose.dev.yml up
```

This starts:
- **Web Server**: http://localhost:8000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Celery Worker**: Background task processing
- **Celery Beat**: Scheduled task execution
- **MailHog**: Email testing at http://localhost:8025

### Useful Docker Commands

```bash
# Start services in background
docker compose -f docker-compose.dev.yml up -d

# View logs
docker compose -f docker-compose.dev.yml logs -f
docker compose -f docker-compose.dev.yml logs -f web

# Stop services
docker compose -f docker-compose.dev.yml down

# Rebuild images
docker compose -f docker-compose.dev.yml build

# Execute commands in running container
docker compose -f docker-compose.dev.yml exec web python manage.py shell
docker compose -f docker-compose.dev.yml exec web python manage.py migrate
docker compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Access database
docker compose -f docker-compose.dev.yml exec db psql -U backend_user -d backend_dev

# Access Redis CLI
docker compose -f docker-compose.dev.yml exec redis redis-cli
```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=apps --cov-report=html

# Run specific test file
pytest apps/core/tests.py

# Run tests in parallel
pytest -n auto

# Run only unit tests
pytest -m unit

# Watch mode (requires pytest-watch)
ptw
```

### Code Quality

```bash
# Format code
black apps config
isort apps config

# Check formatting
black --check apps config
isort --check-only apps config

# Linting
flake8 apps config

# Type checking
mypy apps config

# Run all quality checks
make lint  # or run all commands above
```

### Pre-commit Hooks

Pre-commit hooks automatically run quality checks before each commit.

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Skip hooks (not recommended)
git commit --no-verify
```

### Database Management

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations

# Rollback migration
python manage.py migrate <app_name> <migration_name>

# Create SQL for migration (without applying)
python manage.py sqlmigrate <app_name> <migration_number>

# Database shell
python manage.py dbshell
```

### Django Management Commands

```bash
# Interactive shell
python manage.py shell

# Enhanced shell (IPython)
python manage.py shell_plus

# Create superuser
python manage.py createsuperuser

# Change user password
python manage.py changepassword <username>

# Collect static files
python manage.py collectstatic

# Clear expired sessions
python manage.py clearsessions

# Check deployment readiness
python manage.py check --deploy

# Validate environment
python scripts/validate_env.py
```

### Working with Celery

```bash
# Start Celery worker (manual)
celery -A config worker -l info

# Start Celery beat (scheduler)
celery -A config beat -l info

# Monitor tasks
celery -A config inspect active
celery -A config inspect scheduled
celery -A config inspect stats

# Purge all tasks
celery -A config purge
```

### Email Testing

When using MailHog (included in docker-compose.dev.yml):

1. Configure `.env`:
   ```env
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=mailhog
   EMAIL_PORT=1025
   ```

2. Access MailHog UI at http://localhost:8025
3. Send test email:
   ```python
   from django.core.mail import send_mail
   send_mail('Test', 'This is a test', 'from@example.com', ['to@example.com'])
   ```

## Debugging

### Django Debug Toolbar

Enabled automatically in development mode (`DEBUG=True`).

Access at: http://localhost:8000/__debug__/

### VS Code Configuration

`.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Django",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/manage.py",
            "args": ["runserver"],
            "django": true,
            "justMyCode": false
        },
        {
            "name": "Django Tests",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["-v"],
            "django": true,
            "justMyCode": false
        }
    ]
}
```

### PyCharm Configuration

1. **Run Configuration**:
   - Script path: `manage.py`
   - Parameters: `runserver`
   - Environment variables: Load from `.env`

2. **Test Configuration**:
   - Target: `Custom`
   - Additional arguments: `--reuse-db`

### Logging

Check logs in development:

```bash
# Application logs
tail -f logs/django.log

# Docker logs
docker compose -f docker-compose.dev.yml logs -f web

# Access logs with request IDs
grep "request_id" logs/django.log
```

## API Development

### Testing API Endpoints

Using curl:
```bash
# Health check
curl http://localhost:8000/api/health/

# Get JWT token
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}'

# Use token
curl http://localhost:8000/api/protected/ \
  -H "Authorization: Bearer <your-token>"
```

Using HTTPie:
```bash
# Install
pip install httpie

# Health check
http GET localhost:8000/api/health/

# Get token
http POST localhost:8000/api/token/ username=admin password=password

# Use token
http GET localhost:8000/api/protected/ "Authorization: Bearer <token>"
```

### API Documentation

- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **OpenAPI Schema**: http://localhost:8000/api/schema/

## Performance Profiling

### Django Debug Toolbar

Includes panels for:
- SQL queries
- Templates
- Cache operations
- Signals
- Request/Response headers

### Custom Profiling

```python
# In views.py
from django.utils.decorators import method_decorator
from django.views.decorators.debug import profile

@method_decorator(profile, name='dispatch')
class MyView(APIView):
    pass
```

### Query Debugging

```python
from django.db import connection
from django.test.utils import override_settings

# Log all SQL queries
with override_settings(DEBUG=True):
    # Your code here
    print(len(connection.queries))
    for query in connection.queries:
        print(query['sql'])
```

## Common Issues

### Port Already in Use

```bash
# Find process using port 8000
lsof -ti:8000

# Kill process
kill -9 $(lsof -ti:8000)

# Or use different port
python manage.py runserver 0.0.0.0:8001
```

### Database Connection Issues

```bash
# Check if database is running
docker compose -f docker-compose.dev.yml ps db

# Restart database
docker compose -f docker-compose.dev.yml restart db

# Reset database
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d db
python manage.py migrate
```

### Redis Connection Issues

```bash
# Check if Redis is running
docker compose -f docker-compose.dev.yml ps redis

# Test connection
docker compose -f docker-compose.dev.yml exec redis redis-cli ping

# Clear Redis cache
docker compose -f docker-compose.dev.yml exec redis redis-cli FLUSHALL
```

### Migration Conflicts

```bash
# List migrations
python manage.py showmigrations

# Fake migration (if already applied manually)
python manage.py migrate --fake <app_name> <migration_name>

# Merge migrations
python manage.py makemigrations --merge
```

## Environment Variables

### Required Variables

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://backend_user:backend_password@localhost:5432/backend_dev
REDIS_URL=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/0
```

### Optional Variables

```env
# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Email (MailHog)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=localhost
EMAIL_PORT=1025

# Sentry (optional)
# SENTRY_DSN=https://your-sentry-dsn
```

## Best Practices

### Code Organization

- Keep views thin, move logic to models/services
- Use serializers for data validation
- Write tests for all new code
- Document complex logic
- Follow PEP 8 and project conventions

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes and commit
git add .
git commit -m "Description of changes"

# Run tests before pushing
pytest

# Push and create PR
git push origin feature/my-feature
```

### Testing

- Write unit tests for models and utilities
- Write integration tests for APIs
- Aim for >80% code coverage
- Use factories for test data
- Mock external services

## Resources

### Documentation

- [Django Documentation](https://docs.djangoproject.com/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### Tools

- [Django Debug Toolbar](https://django-debug-toolbar.readthedocs.io/)
- [Django Extensions](https://django-extensions.readthedocs.io/)
- [ipdb](https://pypi.org/project/ipdb/) - Enhanced Python debugger

### Community

- Django Discord
- Django Forum
- Stack Overflow - [django] tag
- GitHub Discussions

## Getting Help

1. Check this documentation
2. Search existing issues
3. Ask in team chat
4. Create a GitHub issue

---

**Last Updated**: 2026-01-16
