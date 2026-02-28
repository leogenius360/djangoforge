# Contributing to Backend

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork the repository** and clone your fork
2. **Set up your development environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements/dev.txt
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### 1. Code Style

- Follow PEP 8 guidelines
- Use Ruff for linting and formatting
- Maximum line length: 100 characters
- Use meaningful variable and function names

Run linting before committing:

```bash
ruff check .
ruff format .
```

### 2. Writing Code

- **Keep it simple**: Prefer clarity over cleverness
- **Write docstrings**: Document all public functions and classes
- **Type hints**: Use type hints for function parameters and returns
- **Error handling**: Handle exceptions appropriately

Example:

```python
def process_data(input_data: dict) -> dict:
    """
    Process incoming data and return formatted result.

    Args:
        input_data: Raw data dictionary

    Returns:
        Processed data dictionary

    Raises:
        ValueError: If input_data is invalid
    """
    if not input_data:
        raise ValueError("Input data cannot be empty")

    # Processing logic here
    return processed_data
```

### 3. Testing

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for >80% code coverage

Run tests:

```bash
pytest
pytest --cov=apps --cov-report=html  # With coverage
```

### 4. Database Changes

- Create migrations for model changes:
  ```bash
  python manage.py makemigrations
  python manage.py migrate
  ```
- Test migrations in both directions (up and down)
- Include migration files in your PR

### 5. Committing Changes

**Commit Message Format:**

```
<type>: <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Example:**

```
feat: add user profile endpoint

- Create ProfileViewSet with CRUD operations
- Add serializer for user profile
- Include tests for all endpoints

Closes #123
```

## Pull Request Process

1. **Update documentation** if needed
2. **Add tests** for new functionality
3. **Ensure all tests pass**:
   ```bash
   pytest
   python manage.py check
   ```
4. **Run linting**:
   ```bash
   ruff check .
   ```
5. **Create Pull Request** with:
   - Clear title and description
   - Reference to related issues
   - Screenshots (if UI changes)
   - Test results

### PR Review Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] No merge conflicts
- [ ] Migrations included (if applicable)
- [ ] Environment variables documented (if added)

## Code Review Guidelines

### As a Reviewer:

- Be constructive and respectful
- Focus on code quality, not personal preferences
- Suggest improvements, don't demand them
- Approve once satisfied

### As an Author:

- Respond to all comments
- Be open to feedback
- Make requested changes or discuss alternatives
- Keep PRs focused and reasonably sized

## Project Structure

```
backend/
├── apps/
│   ├── accounts/      # User authentication
│   └── core/          # Core functionality
├── config/
│   ├── settings/      # Django settings
│   └── urls.py        # URL routing
├── requirements/
│   ├── base.txt       # Base dependencies
│   ├── dev.txt        # Development dependencies
│   └── prod.txt       # Production dependencies
└── tests/             # Project-wide tests
```

## Common Tasks

### Add a New Django App

```bash
python manage.py startapp app_name apps/app_name
```

Then:

1. Add to `INSTALLED_APPS` in `config/settings/base.py`
2. Create models, views, serializers
3. Add URL routing
4. Write tests

### Add a New Dependency

```bash
pip install package-name
pip freeze | grep package-name >> requirements/base.txt
```

For dev-only dependencies, add to `requirements/dev.txt`

### Create Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

## Getting Help

- **Questions?** Open a discussion
- **Bug found?** Create an issue
- **Feature idea?** Open an issue for discussion

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive criticism
- Assume good intentions

---

Thank you for contributing! 🎉
