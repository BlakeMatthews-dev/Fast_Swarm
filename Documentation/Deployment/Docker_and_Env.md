# Deployment Guide

## Prerequisites
*   **Docker**: Required for the PostgreSQL database.
*   **Python 3.10+**: Required for the application.

## 1. Local Development (Windows)

1.  **Start Database**:
    ```powershell
    cd local-utilities
    docker-compose up -d
    ```

2.  **Environment Setup**:
    Ensure `.env` exists in the root `Coinswarm-1/` directory.
    ```
    POSTGRES_PASSWORD=coinswarm_dev_2024
    ```

3.  **Run Server**:
    ```powershell
    uvicorn Fast_Swarm.Main:app --reload
    ```

## 2. Production (Linux/Cloud)

*   **Reverse Proxy**: Use Nginx or Caddy to proxy requests to port 8000.
*   **Process Management**: Use `systemd` or `Supervisor` to keep `uvicorn` running.
*   **Database**: Managed PostgreSQL (AWS RDS, DigitalOcean) is recommended over Docker for production persistence.

## 3. Docker Deployment (Application)
(Coming Soon) - A `Dockerfile` for the FastAPI app will allow full containerization.
