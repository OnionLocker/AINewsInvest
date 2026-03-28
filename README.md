# Alpha Vault

US & HK Stock AI Investment Research System.

A full-stack application featuring quantitative screening, multi-dimensional analysis, and AI-powered stock recommendations for US and Hong Kong markets.

## Architecture

```
AINewsInvest/
  api/              # FastAPI backend
    routes/         # auth, admin, recommendations, analysis, user
    server.py       # App entry, CORS, SPA hosting
    deps.py         # JWT auth, Pydantic models
  core/             # Infrastructure layer
    database.py     # SQLite operations (dual-table recommendations)
    data_source.py  # yfinance data fetching
    models.py       # Dataclass models
    user.py         # User management + admin bootstrap
  pipeline/         # Business logic pipeline
    config.py       # Typed config from config.yaml
    screening.py    # Quantitative pre-screening
    runner.py       # Full recommendation pipeline
  analysis/         # Analysis engines
    technical.py    # MA, MACD, RSI, Bollinger, KDJ, ATR
    fundamental.py  # 100-point scoring system
    valuation.py    # BVPS, DDM, FCF floor prices
    llm_client.py   # OpenAI-compatible LLM integration
    news_fetcher.py # News sentiment analysis
  web/              # React SPA (Vite + Tailwind CSS v4)
    src/
      pages/        # Dashboard, Recommendations, Screening, Analysis, Watchlist, Admin
      components/   # Layout, Card, Badge, Spinner, PriceChange
      context/      # AuthContext (JWT)
      api.js        # API client
  deploy/           # systemd service + cron scripts
  config.yaml       # Global configuration
  main.py           # CLI entry point
```

## Quick Start

### 1. Backend Setup

```bash
cd AINewsInvest
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration

Copy and edit the environment file:

```bash
cp .env.example .env
# Edit .env with your settings:
#   JWT_SECRET=your-secret-key
#   OPENAI_API_KEY=your-api-key (optional, for LLM features)
```

Edit `config.yaml` for pipeline parameters, LLM settings, and stock pool configuration.

### 3. Bootstrap Admin

```bash
python main.py bootstrap --username admin --password your-password
```

### 4. Frontend Build

```bash
cd web
npm install
npm run build
cd ..
```

### 5. Start Server

```bash
# Development
python main.py serve

# Production
uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 2
```

Visit `http://localhost:8000` for the web interface.

### 6. Frontend Development

```bash
cd web
npm run dev
# Vite dev server at http://localhost:5173
# API requests proxied to http://localhost:8000
```

## CLI Commands

```bash
python main.py serve              # Start API server
python main.py bootstrap          # Create admin user
python main.py screen             # Run stock screening
python main.py build-pool         # Rebuild stock pool from index components
```

## Stock Pool

Stocks are sourced from major index components:

- **US**: S&P 500, Nasdaq 100
- **HK**: Hang Seng Index, Hang Seng Tech

Run `python main.py build-pool` to refresh the stock pool.

## API Overview

| Endpoint Group | Prefix | Auth |
|---|---|---|
| Authentication | `/api/auth/*` | No (except `/me`) |
| Market & Stocks | `/api/market-overview`, `/api/stock-query` | JWT |
| Recommendations | `/api/recommendations/*` | JWT |
| Screening | `/api/screen/*` | JWT |
| Deep Analysis | `/api/deep-analysis*` | JWT |
| Watchlist | `/api/watchlist*` | JWT |
| Admin | `/api/admin/*` | JWT + Admin |

## Deployment

```bash
# Install systemd service
sudo cp deploy/alphavault.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alphavault

# Install cron jobs
crontab deploy/crontab.example
```

## Tech Stack

- **Backend**: FastAPI, SQLite, yfinance, Pandas
- **Frontend**: React 19, Vite, Tailwind CSS v4, Lucide Icons
- **Auth**: JWT (python-jose)
- **AI**: OpenAI-compatible API (optional)
