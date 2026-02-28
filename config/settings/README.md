# Django Settings Configuration

This directory contains the split settings configuration for the Django backend project.

## Settings Files

- **`base.py`** - Shared settings across all environments (database config, installed apps, middleware, etc.)
- **`dev.py`** - Development settings (DEBUG=True, SQLite fallback, console email backend, etc.)
- **`staging.py`** - Staging environment settings (production-like with some relaxed constraints)
- **`prod.py`** - Production settings (DEBUG=False, strict security, Redis cache, etc.)
- **`__init__.py`** - Automatic settings loader with fallback logic

## How Settings Are Selected

The project uses a **multi-layer approach** to ensure the correct settings are always loaded:

### 1. Explicit Environment Variable (Highest Priority)

Set `DJANGO_SETTINGS_MODULE` to explicitly specify which settings to use:

```bash
# Development
export DJANGO_SETTINGS_MODULE=config.settings.dev

# Production
export DJANGO_SETTINGS_MODULE=config.settings.prod

# Staging
export DJANGO_SETTINGS_MODULE=config.settings.staging
```

### 2. Environment Detection via DJANGO_ENV or NODE_ENV

If `DJANGO_SETTINGS_MODULE` is not set, the system falls back to checking `DJANGO_ENV` or `NODE_ENV`:

```bash
# These will load production settings
export DJANGO_ENV=production
export DJANGO_ENV=prod

# These will load staging settings
export DJANGO_ENV=staging
export DJANGO_ENV=stage

# These will load development settings
export DJANGO_ENV=development
export DJANGO_ENV=dev
```

### 3. Context-Based Defaults

If no environment variables are set, the system uses safe defaults based on context:

- **`manage.py`** → Defaults to `dev` (safe for local development)
- **`wsgi.py`** → Defaults to `prod` (safe for production deployment)
- **`asgi.py`** → Defaults to `prod` (safe for production deployment)

## Configuration Examples

### Local Development

```bash
# Option 1: Explicit (recommended)
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py runserver

# Option 2: Via DJANGO_ENV
export DJANGO_ENV=development
python manage.py runserver

# Option 3: No environment variables (uses manage.py default → dev)
python manage.py runserver
```

### Docker Development (docker-compose.dev.yml)

```yaml
environment:
  - DJANGO_SETTINGS_MODULE=config.settings.dev
```

### Docker Production (docker-compose.yml)

```yaml
environment:
  - DJANGO_SETTINGS_MODULE=config.settings.prod
```

### CI/CD Pipeline

```yaml
env:
  DJANGO_SETTINGS_MODULE: config.settings.dev # For tests
```

### Production Deployment

```bash
# Set explicitly in your deployment configuration
export DJANGO_SETTINGS_MODULE=config.settings.prod
gunicorn config.wsgi:application
```

## Verification

You can verify which settings are being used:

```bash
# Check which settings module is loaded
python manage.py diffsettings | grep SETTINGS_MODULE

# Or use Django shell
python manage.py shell
>>> from django.conf import settings
>>> print(settings.SETTINGS_MODULE)
```

## Safety Guarantees

### Development Safety

- `manage.py` defaults to `dev` to prevent accidental production commands locally
- Development settings allow `DEBUG=True`, SQLite fallback, and relaxed CORS

### Production Safety

- `wsgi.py` and `asgi.py` default to `prod` to ensure production deployments are secure
- Production settings enforce `DEBUG=False`, require PostgreSQL, and strict security headers
- Docker containers explicitly set `DJANGO_SETTINGS_MODULE` in docker-compose files
- CI/CD explicitly sets `DJANGO_SETTINGS_MODULE` for consistency

### Multi-Layer Protection

1. **Explicit wins**: `DJANGO_SETTINGS_MODULE` always takes precedence
2. **Environment detection**: `DJANGO_ENV`/`NODE_ENV` provide flexibility
3. **Context-aware defaults**: Different defaults for different entry points
4. **Docker enforcement**: Container environments always explicitly set the module

## Best Practices

1. **Always set `DJANGO_SETTINGS_MODULE` explicitly in production** - Don't rely on defaults
2. **Use docker-compose environment variables** - Make settings explicit in containers
3. **Set in CI/CD pipelines** - Always specify the test settings module
4. **Document environment variables** - Keep `.env.example` up to date
5. **Test settings selection** - Verify the correct settings load in each environment

## Troubleshooting

### Wrong settings loaded?

```bash
# Check current settings
python -c "import os; print(os.environ.get('DJANGO_SETTINGS_MODULE', 'Not set'))"

# Or check in Django
python manage.py shell
>>> from django.conf import settings
>>> print(settings.DEBUG)  # Should be False in production, True in dev
```

### Settings import error?

Make sure you're using one of:

- `config.settings.dev`
- `config.settings.prod`
- `config.settings.staging`

Never use just `config.settings` - it's a package, not a module.

## Summary

The settings configuration is designed with **defense in depth**:

- ✅ Explicit configuration always wins
- ✅ Environment detection provides flexibility
- ✅ Safe defaults prevent accidents
- ✅ Multi-layer approach ensures correctness
- ✅ Docker and CI/CD use explicit configuration
