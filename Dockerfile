FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg (libpq), Pillow, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Core: FastAPI + uvicorn + psycopg3 + SQLModel + async DB
# Data: numpy, pandas, polars, yfinance, ccxt
# Web: httpx, aiohttp, websockets, requests
# Other: pillow, pyyaml, quantstats, python-dotenv, hypothesis (tests)
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    sqlmodel "sqlalchemy[asyncio]" "psycopg[binary]" \
    python-dotenv httpx aiohttp websockets requests \
    pydantic numpy pandas polars \
    yfinance ccxt quantstats \
    pillow pyyaml python-multipart \
    hypothesis pytest pytest-asyncio

# Copy the full repo
COPY . .

# The package lives in src/Fast_Swarm, and top-level Main.py etc. also import from it
ENV PYTHONPATH=/app/src:/app

EXPOSE 8080

CMD ["uvicorn", "Fast_Swarm.Main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "asyncio"]
