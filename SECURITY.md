# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability, please send an email to security@brainboxresearch.com with:

1. **Description** of the vulnerability
2. **Steps to reproduce** the issue
3. **Potential impact** assessment
4. **Suggested fix** (if you have one)

You should receive a response within 48 hours. We'll keep you updated on the progress.

## Security Best Practices

### For Developers

#### 1. Environment Variables
- **Never commit** `.env` files
- Use strong, unique values for:
  - `SECRET_KEY` (50+ characters)
  - `DATABASE_URL` passwords
- Rotate secrets regularly

#### 2. Database Security
- Use strong database passwords
- Enable SSL connections in production
- Regular backups with encryption
- Limit database user permissions

#### 3. Authentication
- JWT tokens expire in 60 minutes (access) / 7 days (refresh)
- Use HTTPS only in production
- Implement rate limiting on auth endpoints
- Strong password requirements enforced

#### 4. API Security
- CORS configured for specific origins only
- CSRF protection enabled
- Request size limits enforced
- Input validation on all endpoints

#### 5. Dependencies
- Regularly update dependencies:
  ```bash
  pip list --outdated
  pip install --upgrade package-name
  ```
- Review security advisories
- Use `pip-audit` for vulnerability scanning:
  ```bash
  pip install pip-audit
  pip-audit
  ```

### For Production Deployments

#### Required Settings
```python
# config/settings/production.py
DEBUG = False
SECRET_KEY = env('SECRET_KEY')  # Strong, unique key
ALLOWED_HOSTS = ['your-domain.com']

# Security Headers
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

#### Database
- Use managed database service (e.g., Digital Ocean Managed PostgreSQL)
- Enable SSL/TLS connections
- Regular automated backups
- Restrict network access

#### Server
- Keep OS and packages updated
- Use firewall (ufw, iptables)
- Disable root SSH login
- Use SSH keys, not passwords
- Enable fail2ban for brute force protection

#### Monitoring
- Monitor for unusual activity
- Set up error notifications
- Regular security audits
- Log security events

## Known Security Considerations

### Current Implementation

1. **JWT Authentication**
   - Access tokens: 60 minute expiration
   - Refresh tokens: 7 day expiration
   - Tokens not revoked on logout (stateless)
   - Consider token blacklist for critical applications

2. **CORS**
   - Configured for specific origins
   - Update `CORS_ALLOWED_ORIGINS` in production

3. **Rate Limiting**
   - Not currently implemented
   - Consider adding for production (e.g., django-ratelimit)

4. **File Uploads**
   - Not currently implemented
   - When added, validate file types and sizes
   - Scan for malware
   - Store outside web root

## Security Checklist for Production

Before deploying to production:

- [ ] `DEBUG = False`
- [ ] Strong `SECRET_KEY` set
- [ ] `ALLOWED_HOSTS` configured
- [ ] Database using SSL/TLS
- [ ] HTTPS enforced
- [ ] Security headers enabled
- [ ] CORS properly configured
- [ ] Dependencies up to date
- [ ] Database backups enabled
- [ ] Monitoring and logging configured
- [ ] Firewall rules in place
- [ ] SSH access secured
- [ ] Environment variables secured

## Vulnerability Disclosure Timeline

1. **Day 0**: Vulnerability reported
2. **Day 1-2**: Initial response and acknowledgment
3. **Day 3-7**: Vulnerability assessment and fix development
4. **Day 7-14**: Testing and validation
5. **Day 14**: Security update released
6. **Day 30**: Public disclosure (if applicable)

## Contact

For security concerns: security@brainboxresearch.com

## Attribution

We appreciate responsible disclosure and will acknowledge security researchers who report vulnerabilities.

---

Last updated: January 17, 2026
