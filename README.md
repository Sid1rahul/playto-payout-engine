<<<<<<< HEAD
# Playto Payout Engine

A production-ready payout system built with Django, DRF, Celery, PostgreSQL, and React.

**Stack:** Django 4.2 · DRF · PostgreSQL · Celery · Redis · React 18 · Tailwind CSS

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Local Setup](#local-setup)
- [Running the System](#running-the-system)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Features

✅ **Ledger-based Balance Tracking** — Immutable append-only transaction records  
✅ **Concurrency Control** — Row-level locking with `select_for_update()` prevents overdrafts  
✅ **Idempotent Payout Creation** — Same request key returns same response  
✅ **State Machine Validation** — Legal transitions enforced at DB level  
✅ **Background Processing** — Celery + Redis for asynchronous payout settlement  
✅ **Retry with Exponential Backoff** — Auto-retry stuck payouts up to 3 attempts  
✅ **Atomic Fund Refunds** — Failed payouts return funds instantly  
✅ **Live Frontend Updates** — Real-time payout status polling  

---

## Architecture

```
playto-payout/
├── backend/                     # Django REST API
│   ├── config/                  # Django settings, Celery config
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── wsgi.py
│   ├── payouts/                 # Payout app
│   │   ├── models.py            # Merchant, Transaction, Payout, etc.
│   │   ├── services.py          # Business logic (locking, balance, state machine)
│   │   ├── views.py             # API endpoints
│   │   ├── urls.py
│   │   ├── tasks.py             # Celery tasks
│   │   ├── serializers.py
│   │   ├── admin.py
│   │   └── tests/               # Concurrency & idempotency tests
│   ├── manage.py
│   └── requirements.txt
│
├── frontend/                    # React + Vite + Tailwind
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── BalanceCard.jsx
│   │   │   ├── PayoutForm.jsx
│   │   │   ├── TransactionTable.jsx
│   │   │   └── PayoutHistory.jsx
│   │   ├── api.js
│   │   ├── utils.js
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
└── README.md
```

---

## Local Setup

### Prerequisites

- **Python 3.11+**
- **Node.js 20+**
- **PostgreSQL 15+**
- **Redis 7+**

### 1. Backend Setup

#### Install PostgreSQL

On Windows, download from [postgresql.org](https://www.postgresql.org/download/windows/) and install.

After installation, create a database:

```bash
# Using psql
psql -U postgres
CREATE DATABASE playto;
CREATE USER playto_user WITH PASSWORD 'playto_password';
ALTER ROLE playto_user SET client_encoding TO 'utf8';
ALTER ROLE playto_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE playto_user SET default_transaction_deferrable TO on;
GRANT ALL PRIVILEGES ON DATABASE playto TO playto_user;
\q
```

Update `.env` with your database credentials:

```env
DB_NAME=playto
DB_USER=playto_user
DB_PASSWORD=playto_password
DB_HOST=localhost
DB_PORT=5432
```

#### Install Redis

On Windows:
- Download from [redis.io](https://redis.io/download)
- Or use Windows Subsystem for Linux (WSL):

```bash
# In WSL
sudo apt-get install redis-server
redis-server
```

#### Install Python Dependencies

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

#### Create Migrations & Seed Database

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py seed
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

---

## Running the System

### Start PostgreSQL (if not running as service)

```bash
# On Windows, if installed as service, it should already be running
# To verify:
psql -U postgres -c "SELECT 1"
```

### Start Redis

```bash
# Windows (if using redis-server.exe)
redis-server

# WSL
redis-server
```

### Start Django Backend

```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
python manage.py runserver
```

Backend will be available at `http://localhost:8000`

### Start Celery Worker

In a new terminal:

```bash
cd backend
source venv/bin/activate
celery -A config worker -l info
```

### Start Celery Beat (Periodic Tasks)

In another new terminal:

```bash
cd backend
source venv/bin/activate
celery -A config beat -l info
```

### Start React Frontend

In another new terminal:

```bash
cd frontend
npm run dev
```

Frontend will be available at `http://localhost:5173`

---

## API Endpoints

All endpoints require proper request structure and authentication (in production).

### Balance Endpoints

**GET /api/v1/merchants/{merchant_id}/balance/**

```bash
curl http://localhost:8000/api/v1/merchants/c8e8c8f8-1234-5678-9012-3456789012ab/balance/
```

Response:

```json
{
  "merchant_id": "c8e8c8f8-1234-5678-9012-3456789012ab",
  "merchant_name": "Acme Design Studio",
  "available_balance_paise": 10000,
  "held_balance_paise": 6000
}
```

### Payout Endpoints

**POST /api/v1/payouts/**

Create a new payout. Requires `Idempotency-Key` header.

```bash
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "merchant_id": "c8e8c8f8-1234-5678-9012-3456789012ab",
    "amount_paise": 500000,
    "bank_account_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6"
  }'
```

Response (201 Created):

```json
{
  "id": "f9e8d7c6-b5a4-3210-9876-543210fedcba",
  "merchant_id": "c8e8c8f8-1234-5678-9012-3456789012ab",
  "amount_paise": 500000,
  "status": "pending",
  "bank_account_id": "a1b2c3d4-e5f6-47g8-h9i0-j1k2l3m4n5o6",
  "created_at": "2026-04-25T10:30:00Z",
  "updated_at": "2026-04-25T10:30:00Z"
}
```

**GET /api/v1/payouts/{payout_id}/**

Get payout details:

```bash
curl http://localhost:8000/api/v1/payouts/f9e8d7c6-b5a4-3210-9876-543210fedcba/
```

### Transaction Endpoints

**GET /api/v1/merchants/{merchant_id}/transactions/**

List all transactions (credits and debits):

```bash
curl http://localhost:8000/api/v1/merchants/c8e8c8f8-1234-5678-9012-3456789012ab/transactions/
```

### Payout History

**GET /api/v1/merchants/{merchant_id}/payouts/**

List all payouts for a merchant:

```bash
curl http://localhost:8000/api/v1/merchants/c8e8c8f8-1234-5678-9012-3456789012ab/payouts/
```

---

## Testing

### Run All Tests

```bash
cd backend
python manage.py test
```

### Run Specific Test Class

```bash
python manage.py test payouts.tests.test_concurrency.ConcurrencyTest
python manage.py test payouts.tests.test_idempotency.IdempotencyTest
```

### Run with Verbose Output

```bash
python manage.py test --verbosity=2
```

#### What the Tests Verify

**Concurrency Tests** (`test_concurrency.py`):
- Two simultaneous 60 INR payouts with 100 INR balance → one succeeds, one fails
- Three simultaneous 40 INR payouts with 100 INR balance → one succeeds, two fail
- Ledger invariant maintained: `credits - debits == available_balance + held_balance`
- Uses `TransactionTestCase` with actual database transactions (not test transactions)

**Idempotency Tests** (`test_idempotency.py`):
- Same key returns same payout ID and cached response
- Different keys create different payouts
- Keys are scoped per merchant (different merchants can use same key)
- Only one DB row created per unique key

---

## Deployment

### Option 1: Railway.app (Recommended)

1. Push code to GitHub
2. Create Railway project
3. Add PostgreSQL plugin
4. Add Redis plugin
5. Create two services: `web` and `worker`

**Web Service:**

```bash
Start command: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
Environment: DATABASE_URL, REDIS_URL, SECRET_KEY
```

**Worker Service:**

```bash
Start command: celery -A config worker -B -l info
Environment: DATABASE_URL, REDIS_URL
```

6. Run migrations:

```bash
python manage.py migrate && python manage.py seed
```

### Option 2: Docker Compose

```bash
docker-compose up
```

See `docker-compose.yml` for configuration.

---

## Troubleshooting

### "psycopg2: could not connect to server"

- Verify PostgreSQL is running
- Check `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` in `.env`
- On Windows: Services > PostgreSQL > Ensure running

### "ConnectionError: Error 111 connecting to localhost:6379"

- Redis is not running
- Start with `redis-server` or check Redis service on Windows

### "ModuleNotFoundError: No module named 'payouts'"

- Ensure Django is installed: `pip install -r requirements.txt`
- Run from the `backend/` directory

### "Port 8000 already in use"

```bash
# Kill process using port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :8000
kill -9 <PID>
```

---

## Key Design Decisions

See [EXPLAINER.md](EXPLAINER.md) for detailed explanations of:

1. **The Ledger** — Why balance is derived, not stored
2. **The Lock** — How `select_for_update()` prevents overdrafts
3. **Idempotency** — How request keys ensure safe retries
4. **State Machine** — How legal transitions are enforced
5. **AI Audit** — Common mistakes the AI made and how they were fixed

---

## License

MIT
=======
# playto-payout-engine
Production-grade payout engine simulating real-world fintech systems with strong guarantees on money integrity, concurrency control, idempotency, and state transitions.  Built with Django, PostgreSQL, Celery, and React. Implements ledger-based balance tracking, atomic transactions, and retry-safe payout processing.
>>>>>>> 78cd4f4031644ee456234d2b0207600663df19d0
