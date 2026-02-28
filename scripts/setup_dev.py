#!/usr/bin/env python
"""
Development environment setup script.
Run this after cloning the repository.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and handle errors."""
    print(f"\n→ {description}...")
    try:
        subprocess.run(cmd, check=True, shell=True)
        print(f"✓ {description} completed")
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        return False
    return True


def main():
    """Main setup function."""
    print("=" * 50)
    print("Backend Development Environment Setup")
    print("=" * 50)

    # Check if .env exists
    env_file = Path(".env")
    env_example = Path(".env.example")

    if not env_file.exists() and env_example.exists():
        print("\n→ Creating .env file from .env.example...")
        env_file.write_text(env_example.read_text())
        print("✓ .env file created (please update with your values)")
    elif env_file.exists():
        print("\n✓ .env file already exists")

    # Install dependencies
    if not run_command("pip install -r requirements/dev.txt", "Installing Python dependencies"):
        sys.exit(1)

    # Start database
    if not run_command("docker compose up db -d", "Starting PostgreSQL database"):
        print("⚠ Warning: Could not start database container")

    # Wait for database
    print("\n→ Waiting for database to be ready...")
    import time

    time.sleep(3)

    # Run migrations
    if not run_command("python manage.py migrate", "Running database migrations"):
        print("⚠ Warning: Could not run migrations")

    print("\n" + "=" * 50)
    print("✓ Setup complete!")
    print("=" * 50)
    print("\nNext steps:")
    print("1. Update .env with your configuration")
    print("2. Create a superuser: python manage.py createsuperuser")
    print("3. Start the server: python manage.py runserver")
    print("\nAccess the API at: http://localhost:8000/api/docs/")


if __name__ == "__main__":
    main()
