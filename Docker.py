"""
Docker.py - Auto-start Docker Desktop and PostgreSQL container

Called during Fast_Swarm lifespan startup to ensure database is available.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Timeouts
DOCKER_STARTUP_TIMEOUT = 60  # seconds to wait for Docker Desktop
POSTGRES_STARTUP_TIMEOUT = 30  # seconds to wait for PostgreSQL healthy


def is_docker_running() -> bool:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def start_docker_desktop() -> bool:
    """Start Docker Desktop on Windows. Returns True if started."""
    if sys.platform != "win32":
        print("[Docker] Not on Windows, skipping Docker Desktop auto-start")
        return False

    # Common Docker Desktop paths on Windows
    paths = [
        r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
        os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Docker\Docker Desktop.exe"),
    ]

    for path in paths:
        if os.path.exists(path):
            print(f"[Docker] Starting Docker Desktop from {path}")
            subprocess.Popen([path], creationflags=subprocess.DETACHED_PROCESS)
            return True

    print("[Docker] Docker Desktop not found. Please install from https://docker.com/products/docker-desktop")
    return False


async def wait_for_docker(timeout: int = DOCKER_STARTUP_TIMEOUT) -> bool:
    """Wait for Docker daemon to become ready."""
    print(f"[Docker] Waiting for Docker daemon (up to {timeout}s)...")
    for i in range(timeout):
        if is_docker_running():
            print(f"[Docker] Docker daemon ready after {i}s")
            return True
        await asyncio.sleep(1)
    return False


def is_container_running(container_name: str = "coinswarm-postgres") -> bool:
    """Check if a specific container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "Up" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def start_postgres_container() -> bool:
    """Start PostgreSQL container using docker-compose."""
    # Find docker-compose.yml relative to this file
    compose_file = Path(__file__).parent / "docker-compose.yml"

    if not compose_file.exists():
        print(f"[Docker] docker-compose.yml not found at {compose_file}")
        return False

    print(f"[Docker] Starting PostgreSQL container from {compose_file}")

    try:
        result = subprocess.run(
            ["docker-compose", "-f", str(compose_file), "up", "-d"], capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            # Try docker compose (v2) instead of docker-compose
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "up", "-d"], capture_output=True, text=True, timeout=60
            )

        if result.returncode == 0:
            print("[Docker] PostgreSQL container started")
            return True
        else:
            print(f"[Docker] Failed to start container: {result.stderr}")
            return False

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"[Docker] Error starting container: {e}")
        return False


async def wait_for_postgres(timeout: int = POSTGRES_STARTUP_TIMEOUT) -> bool:
    """Wait for PostgreSQL to be healthy and accepting connections."""
    print(f"[Docker] Waiting for PostgreSQL to be ready (up to {timeout}s)...")

    for i in range(timeout):
        try:
            result = subprocess.run(
                ["docker", "exec", "coinswarm-postgres", "pg_isready", "-U", "coinswarm"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                print(f"[Docker] PostgreSQL ready after {i}s")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        await asyncio.sleep(1)

    return False


async def ensure_database() -> bool:
    """
    Ensure Docker and PostgreSQL are running before the app connects.

    This is called during FastAPI lifespan startup.
    Returns True if database is ready, raises exception on failure.
    """
    # When running inside Docker Compose, PostgreSQL is managed externally
    if os.getenv("SKIP_DOCKER_CHECK", "").lower() in ("1", "true", "yes"):
        print("[Docker] SKIP_DOCKER_CHECK set — assuming database is managed externally")
        return True

    print("[Docker] Ensuring database is available...")

    # Step 1: Check if Docker is running
    if not is_docker_running():
        print("[Docker] Docker daemon not running")

        # Try to start Docker Desktop
        if not start_docker_desktop():
            raise RuntimeError(
                "Docker Desktop is not installed or not found. "
                "Please install from https://docker.com/products/docker-desktop"
            )

        # Wait for Docker to start
        if not await wait_for_docker():
            raise RuntimeError(
                f"Docker Desktop failed to start within {DOCKER_STARTUP_TIMEOUT}s. "
                "Please start Docker Desktop manually."
            )

    # Step 2: Check if PostgreSQL container is running
    if not is_container_running("coinswarm-postgres"):
        print("[Docker] PostgreSQL container not running")

        # Start the container
        if not start_postgres_container():
            raise RuntimeError("Failed to start PostgreSQL container. Check docker-compose.yml and Docker logs.")

    # Step 3: Wait for PostgreSQL to be healthy
    if not await wait_for_postgres():
        raise RuntimeError(
            f"PostgreSQL failed to become healthy within {POSTGRES_STARTUP_TIMEOUT}s. "
            "Check container logs: docker logs coinswarm-postgres"
        )

    print("[Docker] Database is ready!")
    return True
