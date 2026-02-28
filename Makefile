.PHONY: help install migrate run test lint format clean docker-up docker-down ci smoke-test

# Default target
help:
	@echo "Available commands:"
	@echo "  make install            - Install dependencies"
	@echo "  make migrate            - Run database migrations"
	@echo "  make makemigrations     - Create new migrations"
	@echo "  make makemigrations-check - Check for missing migrations (CI)"
	@echo "  make run                - Start development server"
	@echo "  make test               - Run tests"
	@echo "  make lint               - Run linter (ruff)"
	@echo "  make format             - Format code (ruff)"
	@echo "  make fix                - Auto-fix linting issues"
	@echo "  make ci                 - Run all CI checks locally"
	@echo "  make smoke-test         - Run smoke tests"
	@echo "  make schema             - Generate OpenAPI schema"
	@echo "  make clean              - Clean cache files"
	@echo "  make docker-up          - Start Docker containers"
	@echo "  make docker-down        - Stop Docker containers"
	@echo "  make superuser          - Create superuser"
	@echo "  make superuser-auto     - Create superuser non-interactively"
	@echo "  make shell              - Open Django shell"
	@echo "  make check              - Run Django checks"

# Install dependencies
install:
	pip install -r requirements/dev.txt

# Run database migrations
migrate:
	python manage.py migrate

# Start development server
run:
	python manage.py runserver

# Run tests
test:
	pytest

# Run tests with coverage
coverage:
	pytest --cov=apps --cov-report=html --cov-report=term

# Run linter
lint:
	ruff check .

# Format code (using ruff, not black)
format:
	ruff format .

# Fix linting issues
fix:
	ruff check --fix .

# Check for missing migrations (fails if migrations needed)
makemigrations-check:
	python manage.py makemigrations --check --dry-run --noinput

# Run CI checks locally (exact CI parity)
ci: format lint makemigrations-check test
	@echo "All CI checks passed!"

# Clean cache files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/ .pytest_cache/ .ruff_cache/

# Start Docker containers
docker-up:
	docker compose up -d

# Stop Docker containers
docker-down:
	docker compose down

# Restart Docker containers
docker-restart:
	docker compose restart

# View Docker logs
docker-logs:
	docker compose logs -f

# Create superuser
superuser:
	python manage.py createsuperuser

# Create superuser non-interactively (for CI/automation)
superuser-auto:
	@echo "Creating superuser with default credentials (admin/admin)"
	@DJANGO_SUPERUSER_PASSWORD=admin python manage.py createsuperuser --noinput --username admin --email admin@example.com || true

# Open Django shell
shell:
	python manage.py shell

# Run Django checks
check:
	python manage.py check

# Create new migration
makemigrations:
	python manage.py makemigrations

# Show migrations
showmigrations:
	python manage.py showmigrations

# Validate environment
validate-env:
	python scripts/validate_env.py

# Setup development environment
setup:
	python scripts/setup_dev.py

# Collect static files
collectstatic:
	python manage.py collectstatic --noinput

# Database shell
dbshell:
	python manage.py dbshell

# Generate secret key
secret-key:
	python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Generate OpenAPI schema
schema:
	python manage.py spectacular --file schema.yaml
	@echo "Schema generated at schema.yaml"

# Run smoke tests
smoke-test:
	python scripts/smoke_test.py

# Run development setup (full setup)
dev-setup: install docker-up migrate
	@echo "Development environment ready!"
	@echo "Run 'make run' to start the server"

# Production build
prod-build:
	docker compose -f docker-compose.yml build

# All-in-one test suite (deprecated - use 'make ci')
test-all: ci
