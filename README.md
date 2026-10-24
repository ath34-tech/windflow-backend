# WindScope Backend — FastAPI & Elexon BMRS Service

> High-performance Python backend for WindScope, analysing UK national wind generation forecasts (WINDFOR) and actual outturn (FUELHH) across January 2026 for day-ahead electricity trading decisions.

---

## 1. Quick Start (Local Development)

### Prerequisites
- Python 3.12+ (or 3.10+)
- pip / venv

### Installation & Run
```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Uvicorn development server (Port 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Health Check**: `http://localhost:8000/api/health`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc API Documentation**: `http://localhost:8000/redoc`

---

## 2. Deploying to Render (Step-by-Step)

You can deploy this standalone backend to **Render** in two ways:

### Method A: Connect GitHub Repository (Standard)
1. Push this `backend` folder to your GitHub repository (e.g. `windscope-backend`).
2. Log into [Render Dashboard](https://dashboard.render.com/) and click **New +** $\rightarrow$ **Web Service**.
3. Connect your GitHub repository.
4. Configure the Web Service settings:
   - **Name**: `windscope-backend`
   - **Region**: Frankfurt (EU) or Oregon (US)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`
5. In **Advanced**:
   - **Health Check Path**: `/api/health`
6. Click **Create Web Service**. Render will install requirements, pre-load the cached January dataset, and provide your public URL (e.g. `https://windscope-backend.onrender.com`).

### Method B: Deploy using Docker on Render
If you select **Docker** runtime on Render:
- Render will automatically detect the `Dockerfile`.
- Render supplies `$PORT`, which our Dockerfile dynamically forwards to Uvicorn.
- **Health Check Path**: `/api/health`.

### Method C: Render Blueprint (`render.yaml`)
This repository contains a pre-configured [`render.yaml`](./render.yaml). You can click **New +** $\rightarrow$ **Blueprint** on Render to automatically deploy with all production settings configured.

---

## 3. Running with Docker / Docker Compose

### Run Standalone Docker Container
```bash
docker build -t windscope-backend .
docker run -p 8000:8000 windscope-backend
```

### Run with Docker Compose
```bash
docker compose up --build
```
The healthcheck will ping `http://localhost:8000/api/health` every 15 seconds.

---

## 4. Architecture & Data Ingestion

```text
Elexon BMRS API v1 (FUELHH / WINDFOR)
            │ (Bounded 7-day chunking retrieval)
            ▼
   DataLoader Singleton
   ├── Local Disk Cache: data/jan2026_cache.json (1,488 actuals, 19,272 forecasts)
   └── In-Memory Store: Instant cold starts (<10ms)
            │
   Cutoff-Aware Forecast Selection (Matching on startTime)
   ├── Strict Elimination of Post-Cutoff Look-Ahead Bias
   └── Full Publication Lineage Retained
            │
   FastAPI Endpoints (/api/overview, /api/intervals, /api/cutoff-sensitivity)
            ▲
            │ (Wildcard CORS: All origins allowed)
   React Frontend (Vercel / Localhost)
```

- **Actuals (FUELHH)**: Filtered strictly to `fuelType = "WIND"`.
- **Forecasts (WINDFOR)**: Retains all published revisions for each half-hour delivery window.
- **Cutoff Selection**: For any delivery interval $T$, only forecasts published at or before the cutoff (e.g. D-1 12:00 GMT) are eligible for decision-time metrics.
- **Error Metric Convention**: $\text{error} = \text{forecast} - \text{actual}$. Positive error means overforecast (under-procurement risk). Negative error means underforecast.
- **CORS**: Configured with wildcard/all-origin support (`allow_origins=["*"]`) so any deployed frontend (Vercel, custom domain, localhost) connects without preflight issues.

---

## 5. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Healthcheck, version, and preloaded record counts. |
| `GET` | `/api/dates` | List of supported delivery dates (2026-01-01 to 2026-01-31). |
| `GET` | `/api/overview` | Primary payload: intervals, metrics, KPIs, daily trends for specified scope. |
| `GET` | `/api/intervals` | Multi-dimensional filter query (time-of-day, wind band, weekend, error direction, min threshold). |
| `GET` | `/api/cutoff-sensitivity` | Evaluates MAE and bias across candidate cutoffs from 06:00 to 18:00 on D-1. |
| `GET` | `/api/intervals/{startTime}/forecast-history` | Audit trail of all publications for a given half-hour. |
| `GET` | `/api/metrics` | Recomputed MAE, RMSE, and bias over matched pairs. |
| `POST` | `/api/refresh` | Triggers a fresh retrieval from live Elexon BMRS API. |

---

## 6. Automated Tests

Run the complete 20-test pytest suite:
```bash
python -m pytest tests -v
```

Verifies:
- Cutoff-aware forecast selection and exclusion of post-cutoff revisions
- Known-answer check: Forecasts `[110, 90]` vs Actuals `[100, 100]` $\rightarrow$ MAE: 10, RMSE: 10, Bias: 0, $n=2$
- Positive and negative bias conventions
- Missing data exclusion without zero-filling
- Null returns when sample count $n=0$
- Elexon client exponential backoff and transient retry logic
- Rejection of out-of-bounds delivery dates (HTTP 400)
