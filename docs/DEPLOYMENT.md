# Deployment Guide

## Quick Deploy to Production

### Prerequisites
- PostgreSQL database
- Python 3.12+
- Domain name (optional)

### 1. Environment Setup

Create `.env`:

```bash
SECRET_KEY=<generate-with-python-get-random-secret-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://user:password@host:5432/database
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

### 2. Install Dependencies

```bash
pip install -r requirements/prod.txt
```

### 3. Database Setup

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

### 4. Run with Gunicorn

```bash
gunicorn --bind 0.0.0.0:8000 --workers 4 config.wsgi:application
```

## Docker Deployment

### Build and Run

```bash
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## Digital Ocean

1. Create Droplet (Ubuntu 22.04, 2GB RAM minimum)
2. Create Managed PostgreSQL Database
3. SSH into droplet and clone repository
4. Set environment variables in `.env`
5. Run Docker deployment steps above

## Health Check

Verify deployment:
```bash
curl https://yourdomain.com/api/health/
```

## SSL/HTTPS

Use Let's Encrypt:
```bash
sudo apt install certbot
sudo certbot --nginx -d yourdomain.com
```

## Troubleshooting

**502 Bad Gateway**: Check if gunicorn is running on port 8000
**Database errors**: Verify DATABASE_URL is correct
**Static files 404**: Run `collectstatic` command
