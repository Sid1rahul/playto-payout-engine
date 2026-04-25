# Playto Payout Engine — Detailed Implementation Plan

> **Stack:** Django + DRF · PostgreSQL · Celery · React + Tailwind  
> **Timeline:** 5 days · ~10–15 hours of focused work

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Environment & Tooling Setup](#2-environment--tooling-setup)
3. [Database Models](#3-database-models)
4. [Seed Script](#4-seed-script)
5. [Core Backend Logic](#5-core-backend-logic)
6. [API Endpoints (DRF)](#6-api-endpoints-drf)
7. [Celery Background Worker](#7-celery-background-worker)
8. [React Frontend](#8-react-frontend)
9. [Tests](#9-tests)
10. [Deployment](#10-deployment)
11. [EXPLAINER.md Answers](#11-explainermd-answers)
12. [Checklist Before Submission](#12-checklist-before-submission)

---

## 1. Project Structure

```
playto-payout/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── celery.py
│   │   └── wsgi.py
│   └── payouts/
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── tasks.py
│       ├── services.py        ← all business logic lives here
│       ├── admin.py
│       └── tests/
│           ├── test_concurrency.py
│           └── test_idempotency.py
├── frontend/
│   ├── package.json
│   ├── tailwind.config.js
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/
│           ├── Dashboard.jsx
│           ├── BalanceCard.jsx
│           ├── PayoutForm.jsx
│           ├── TransactionTable.jsx
│           └── PayoutHistory.jsx
├── docker-compose.yml         ← optional bonus
├── README.md
└── EXPLAINER.md
```

---

## 2. Environment & Tooling Setup

### 2.1 Python / Django

```
Python 3.11+
Django 4.2
djangorestframework
psycopg2-binary
celery[redis]
django-redis
python-dotenv
uuid
```

**`requirements.txt`** — pin exact versions for reproducibility.

### 2.2 PostgreSQL

- Use a local PostgreSQL 15 instance (or Railway/Render Postgres add-on in prod).
- Create a dedicated DB and user. Never use the default `postgres` superuser in app config.
- Set `CONN_MAX_AGE = 60` in Django `DATABASES` setting to reuse connections.

### 2.3 Redis (for Celery broker)

- Local: `redis-server` or Docker `redis:7-alpine`.
- Prod: Upstash free tier or Railway Redis add-on.

### 2.4 Celery config (`config/celery.py`)

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("playto")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

Add to `settings.py`:
```python
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
```

### 2.5 Frontend

```
node 20+
React 18
Vite (not CRA — faster)
Tailwind CSS 3
axios
```

---

## 3. Database Models

This is the most critical section. Every design decision here has correctness consequences.

### 3.1 `Merchant`

```python
class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_available_balance(self):
        """
        Derived from ledger. Never stored as a column.
        Uses DB-level aggregation — no Python arithmetic on fetched rows.
        """
        from django.db.models import Sum, Value
        from django.db.models.functions import Coalesce

        credits = self.transactions.filter(
            txn_type=Transaction.CREDIT
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

        debits = self.transactions.filter(
            txn_type=Transaction.DEBIT
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

        return credits - debits

    def get_held_balance(self):
        from django.db.models import Sum, Value
        from django.db.models.functions import Coalesce
        return self.payouts.filter(
            status__in=[Payout.PENDING, Payout.PROCESSING]
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]
```

**Why no `balance` column?** A stored balance column requires you to keep it in sync across all code paths. A derived balance from the ledger is always correct by construction. The tradeoff is a slightly more expensive read query — acceptable at this scale, and the correct default for a money system.

### 3.2 `Transaction` (Ledger)

```python
class Transaction(models.Model):
    CREDIT = "credit"
    DEBIT = "debit"
    TXN_TYPES = [(CREDIT, "Credit"), (DEBIT, "Debit")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT,
                                  related_name="transactions")
    txn_type = models.CharField(max_length=10, choices=TXN_TYPES)
    amount_paise = models.BigIntegerField()          # ← ALWAYS BigIntegerField
    description = models.CharField(max_length=255)
    payout = models.ForeignKey("Payout", null=True, blank=True,
                                on_delete=models.PROTECT,
                                related_name="ledger_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["merchant", "created_at"]),
            models.Index(fields=["merchant", "txn_type"]),
        ]
```

**Why `BigIntegerField` and not `DecimalField`?**
- Floats are IEEE 754 binary and cannot represent 0.1 exactly → never use for money.
- `DecimalField` is safer than float but still introduces decimal-to-binary conversion and ORM overhead.
- Storing paise as an integer means all arithmetic is exact integer arithmetic with no rounding at any layer.
- Rule: display layer divides by 100 to show rupees. Storage layer never does.

### 3.3 `BankAccount`

```python
class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT,
                                  related_name="bank_accounts")
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### 3.4 `Payout` (State Machine)

```python
class Payout(models.Model):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    # Legal state transitions — used in service layer validation
    VALID_TRANSITIONS = {
        PENDING: [PROCESSING],
        PROCESSING: [COMPLETED, FAILED],
        COMPLETED: [],          # terminal — no transitions allowed
        FAILED: [],             # terminal — no transitions allowed
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT,
                                  related_name="payouts")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                               default=PENDING)
    idempotency_key = models.CharField(max_length=255, db_index=True)
    attempt_count = models.IntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Scoped idempotency: same key cannot be reused by same merchant
        unique_together = [("merchant", "idempotency_key")]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["merchant", "status"]),
        ]
```

### 3.5 `IdempotencyRecord`

```python
class IdempotencyRecord(models.Model):
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    response_body = models.JSONField()       # cached serialized response
    response_status = models.IntegerField()
    payout = models.ForeignKey(Payout, null=True, blank=True,
                                on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()      # created_at + 24 hours

    class Meta:
        unique_together = [("merchant", "key")]
        indexes = [
            models.Index(fields=["expires_at"]),
        ]
```

**Why a separate table?**  
- The `Payout.unique_together` prevents duplicate rows, but doesn't store the serialized HTTP response.  
- The response must be byte-for-byte identical on replay — status code included.  
- Storing the response in a separate record lets you replay it without re-serializing, avoiding drift if serializer logic changes.

---

## 4. Seed Script

**`backend/payouts/management/commands/seed.py`**

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from payouts.models import Merchant, BankAccount, Transaction
import uuid

class Command(BaseCommand):
    help = "Seed merchants with credit history"

    def handle(self, *args, **options):
        merchants_data = [
            {"name": "Acme Design Studio", "email": "acme@example.com",
             "credits": [500000, 250000, 100000]},  # 8500 INR total
            {"name": "Pixel Labs", "email": "pixel@example.com",
             "credits": [1000000, 500000]},          # 15000 INR total
            {"name": "WebForge Co", "email": "webforge@example.com",
             "credits": [750000, 300000, 200000]},   # 12500 INR total
        ]

        for data in merchants_data:
            merchant, _ = Merchant.objects.get_or_create(email=data["email"],
                                                          defaults={"name": data["name"]})
            BankAccount.objects.get_or_create(
                merchant=merchant,
                defaults={
                    "account_number": "1234567890",
                    "ifsc_code": "HDFC0001234",
                    "account_holder_name": data["name"],
                }
            )
            for amount in data["credits"]:
                Transaction.objects.create(
                    merchant=merchant,
                    txn_type=Transaction.CREDIT,
                    amount_paise=amount,
                    description="Simulated customer payment",
                )
            self.stdout.write(f"Seeded {merchant.name}")
```

Run with: `python manage.py seed`

---

## 5. Core Backend Logic

All business logic goes in `payouts/services.py`. Views stay thin — they parse input and call services.

### 5.1 Balance Check + Fund Hold (The Critical Section)

```python
# payouts/services.py
from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from .models import Merchant, Payout, Transaction, IdempotencyRecord, BankAccount

def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> dict:

    # Step 1: Check idempotency BEFORE acquiring any lock
    record = IdempotencyRecord.objects.filter(
        merchant=merchant,
        key=idempotency_key,
        expires_at__gt=timezone.now(),
    ).select_related("payout").first()

    if record:
        return {"data": record.response_body,
                "status": record.response_status,
                "cached": True}

    # Step 2: Validate bank account belongs to this merchant
    try:
        bank_account = BankAccount.objects.get(
            id=bank_account_id, merchant=merchant, is_active=True
        )
    except BankAccount.DoesNotExist:
        raise ValueError("Invalid bank account")

    # Step 3: Atomic balance check + fund hold
    # select_for_update() acquires a row-level lock on the merchant row.
    # This serializes all payout requests for the same merchant.
    # WITHOUT this lock: two concurrent requests both read balance=100,
    # both see 100 >= 60, both proceed → overdraft.
    with transaction.atomic():
        merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)

        # Calculate balance inside the transaction, after lock is held.
        # aggregate() runs a single SQL SUM — no Python arithmetic on fetched rows.
        credits = merchant_locked.transactions.filter(
            txn_type=Transaction.CREDIT
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

        debits = merchant_locked.transactions.filter(
            txn_type=Transaction.DEBIT
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

        held = merchant_locked.payouts.filter(
            status__in=[Payout.PENDING, Payout.PROCESSING]
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

        available = credits - debits - held

        if available < amount_paise:
            raise ValueError(
                f"Insufficient balance. Available: {available} paise, "
                f"Requested: {amount_paise} paise"
            )

        # Funds are "held" implicitly: any pending/processing payout
        # is excluded from available balance in future calculations.
        payout = Payout.objects.create(
            merchant=merchant_locked,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.PENDING,
            idempotency_key=idempotency_key,
        )

        response_body = _serialize_payout(payout)
        response_status = 201

        IdempotencyRecord.objects.create(
            merchant=merchant,
            key=idempotency_key,
            response_body=response_body,
            response_status=response_status,
            payout=payout,
            expires_at=timezone.now() + timedelta(hours=24),
        )

    # Enqueue background processing OUTSIDE the transaction
    # (if the task fires before the txn commits, it won't find the payout)
    from .tasks import process_payout
    process_payout.apply_async(args=[str(payout.id)], countdown=2)

    return {"data": response_body, "status": response_status, "cached": False}
```

### 5.2 State Machine Transition

```python
def transition_payout(payout: Payout, new_status: str,
                       failure_reason: str = "") -> Payout:
    """
    The ONLY place where payout status changes.
    Validates against VALID_TRANSITIONS before any write.
    """
    if new_status not in Payout.VALID_TRANSITIONS.get(payout.status, []):
        raise ValueError(
            f"Illegal transition: {payout.status} → {new_status}"
        )

    with transaction.atomic():
        # Re-fetch with lock to prevent concurrent status changes
        payout = Payout.objects.select_for_update().get(pk=payout.pk)

        # Re-validate after lock (status may have changed between
        # the first fetch and acquiring the lock)
        if new_status not in Payout.VALID_TRANSITIONS.get(payout.status, []):
            raise ValueError(
                f"Illegal transition after lock: {payout.status} → {new_status}"
            )

        payout.status = new_status
        payout.failure_reason = failure_reason
        payout.save(update_fields=["status", "failure_reason", "updated_at"])

        if new_status == Payout.FAILED:
            # Return held funds ATOMICALLY with the status transition.
            # This is inside the same transaction — either both succeed or both roll back.
            Transaction.objects.create(
                merchant=payout.merchant,
                txn_type=Transaction.CREDIT,
                amount_paise=payout.amount_paise,
                description=f"Refund for failed payout {payout.id}",
                payout=payout,
            )

        if new_status == Payout.COMPLETED:
            # Finalize the debit when payout actually completes
            Transaction.objects.create(
                merchant=payout.merchant,
                txn_type=Transaction.DEBIT,
                amount_paise=payout.amount_paise,
                description=f"Payout to bank account {payout.bank_account_id}",
                payout=payout,
            )

    return payout
```

**Why write the DEBIT on completion, not on payout creation?**  
- Writing a DEBIT at creation would reduce the available balance twice (once via the held calculation, once via the debit). Funds are "held" by being in a pending/processing payout. The DEBIT is recorded only when the payout actually settles.

---

## 6. API Endpoints (DRF)

### 6.1 URL Configuration

```
GET  /api/v1/merchants/{id}/balance/
GET  /api/v1/merchants/{id}/transactions/
GET  /api/v1/merchants/{id}/payouts/
POST /api/v1/payouts/
GET  /api/v1/payouts/{id}/
```

### 6.2 Payout Create View

```python
# payouts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import create_payout
from .models import Merchant
import uuid

class PayoutCreateView(APIView):
    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")

        # Validate idempotency key presence and format
        if not idempotency_key:
            return Response(
                {"error": "Idempotency-Key header is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            return Response(
                {"error": "Idempotency-Key must be a valid UUID"},
                status=status.HTTP_400_BAD_REQUEST
            )

        merchant_id = request.data.get("merchant_id")
        amount_paise = request.data.get("amount_paise")
        bank_account_id = request.data.get("bank_account_id")

        # Input validation
        if not all([merchant_id, amount_paise, bank_account_id]):
            return Response({"error": "Missing required fields"},
                             status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(amount_paise, int) or amount_paise <= 0:
            return Response({"error": "amount_paise must be a positive integer"},
                             status=status.HTTP_400_BAD_REQUEST)

        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant not found"},
                             status=status.HTTP_404_NOT_FOUND)

        try:
            result = create_payout(
                merchant=merchant,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=idempotency_key,
            )
            return Response(result["data"], status=result["status"])

        except ValueError as e:
            return Response({"error": str(e)},
                             status=status.HTTP_422_UNPROCESSABLE_ENTITY)
```

### 6.3 Balance View

```python
class MerchantBalanceView(APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        return Response({
            "merchant_id": str(merchant.id),
            "merchant_name": merchant.name,
            "available_balance_paise": merchant.get_available_balance(),
            "held_balance_paise": merchant.get_held_balance(),
        })
```

### 6.4 CORS

Add `django-cors-headers` and configure for the React frontend origin.

---

## 7. Celery Background Worker

### 7.1 Payout Processor Task

```python
# payouts/tasks.py
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta
import random

logger = get_task_logger(__name__)

MAX_ATTEMPTS = 3
STUCK_THRESHOLD_SECONDS = 30

@shared_task(bind=True, max_retries=MAX_ATTEMPTS)
def process_payout(self, payout_id: str):
    from .models import Payout
    from .services import transition_payout

    try:
        payout = Payout.objects.select_for_update().get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found")
        return

    # Guard: only process pending payouts
    if payout.status != Payout.PENDING:
        logger.info(f"Payout {payout_id} is {payout.status}, skipping")
        return

    # Move to PROCESSING
    payout.status = Payout.PROCESSING
    payout.processing_started_at = timezone.now()
    payout.attempt_count += 1
    payout.save(update_fields=["status", "processing_started_at",
                                "attempt_count", "updated_at"])

    # Simulate bank API call
    # 70% success, 20% failure, 10% hang (timeout)
    outcome = random.choices(
        ["success", "failure", "hang"],
        weights=[70, 20, 10]
    )[0]

    if outcome == "success":
        transition_payout(payout, Payout.COMPLETED)
        logger.info(f"Payout {payout_id} completed")

    elif outcome == "failure":
        transition_payout(payout, Payout.FAILED,
                          failure_reason="Bank rejected the transfer")
        logger.warning(f"Payout {payout_id} failed")

    elif outcome == "hang":
        # Don't transition — the retry task will pick it up
        logger.warning(f"Payout {payout_id} hanging in processing")


@shared_task
def retry_stuck_payouts():
    """
    Periodic task: find payouts stuck in PROCESSING > 30 seconds.
    Uses exponential backoff. After MAX_ATTEMPTS, moves to failed.
    """
    from .models import Payout
    from .services import transition_payout

    threshold = timezone.now() - timedelta(seconds=STUCK_THRESHOLD_SECONDS)

    stuck_payouts = Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__lt=threshold,
    )

    for payout in stuck_payouts:
        if payout.attempt_count >= MAX_ATTEMPTS:
            transition_payout(payout, Payout.FAILED,
                              failure_reason="Max retry attempts exceeded")
            logger.error(f"Payout {payout.id} exhausted retries → failed")
        else:
            # Exponential backoff: 2^attempt_count seconds
            backoff = 2 ** payout.attempt_count
            # Reset to pending so process_payout can pick it up
            payout.status = Payout.PENDING
            payout.save(update_fields=["status", "updated_at"])
            process_payout.apply_async(args=[str(payout.id)], countdown=backoff)
            logger.info(
                f"Payout {payout.id} retrying in {backoff}s "
                f"(attempt {payout.attempt_count + 1}/{MAX_ATTEMPTS})"
            )
```

### 7.2 Celery Beat Schedule (Periodic Tasks)

```python
# config/settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "retry-stuck-payouts": {
        "task": "payouts.tasks.retry_stuck_payouts",
        "schedule": 30.0,  # Every 30 seconds
    },
}
```

Run beat: `celery -A config beat -l info`  
Run worker: `celery -A config worker -l info`

---

## 8. React Frontend

### 8.1 API Client (`src/api.js`)

```javascript
import axios from "axios";
import { v4 as uuidv4 } from "uuid";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

export const getBalance = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/balance/`);

export const getTransactions = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/transactions/`);

export const getPayouts = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/payouts/`);

export const createPayout = (merchantId, amountPaise, bankAccountId) =>
  api.post(
    "/api/v1/payouts/",
    { merchant_id: merchantId, amount_paise: amountPaise, bank_account_id: bankAccountId },
    { headers: { "Idempotency-Key": uuidv4() } }
  );
```

### 8.2 Dashboard Component Structure

```
App
└── Dashboard
    ├── BalanceCard          ← available + held balance in INR
    ├── PayoutForm           ← amount input + bank account selector + submit
    ├── TransactionTable     ← recent credits & debits
    └── PayoutHistory        ← payout list with live status polling
```

### 8.3 Live Status Updates

Use polling (every 5 seconds) on the PayoutHistory table. Check if any payout is in `pending` or `processing` state — if yes, keep polling. Once all are terminal, stop.

```javascript
useEffect(() => {
  const hasActive = payouts.some(
    (p) => p.status === "pending" || p.status === "processing"
  );
  if (!hasActive) return;

  const interval = setInterval(() => {
    fetchPayouts();
  }, 5000);

  return () => clearInterval(interval);
}, [payouts]);
```

### 8.4 Status Badge Colors (Tailwind)

```javascript
const STATUS_COLORS = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};
```

### 8.5 Amount Display Utility

```javascript
// Always convert paise → INR at the display layer only
export const formatINR = (paise) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
  }).format(paise / 100);
```

---

## 9. Tests

### 9.1 Concurrency Test (`test_concurrency.py`)

```python
from django.test import TestCase, TransactionTestCase
from concurrent.futures import ThreadPoolExecutor
from payouts.models import Merchant, BankAccount, Transaction, Payout
from payouts.services import create_payout
import threading

class ConcurrencyTest(TransactionTestCase):
    """
    Use TransactionTestCase (not TestCase) because TestCase wraps everything
    in a transaction that never commits — select_for_update won't behave
    correctly across threads without actual commits.
    """

    def setUp(self):
        self.merchant = Merchant.objects.create(
            name="Test Merchant", email="test@test.com"
        )
        self.bank_account = BankAccount.objects.create(
            merchant=self.merchant,
            account_number="1234567890",
            ifsc_code="HDFC0001234",
            account_holder_name="Test",
        )
        # Seed 100 INR = 10000 paise
        Transaction.objects.create(
            merchant=self.merchant,
            txn_type=Transaction.CREDIT,
            amount_paise=10000,
            description="Seed",
        )

    def test_two_concurrent_60_rupee_payouts(self):
        """
        With 100 INR balance, two simultaneous 60 INR payout requests.
        Exactly one must succeed, the other must raise ValueError.
        """
        results = []
        errors = []
        lock = threading.Lock()

        def attempt_payout(key):
            try:
                result = create_payout(
                    merchant=self.merchant,
                    amount_paise=6000,
                    bank_account_id=str(self.bank_account.id),
                    idempotency_key=key,
                )
                with lock:
                    results.append(result)
            except ValueError as e:
                with lock:
                    errors.append(str(e))

        import uuid
        keys = [str(uuid.uuid4()), str(uuid.uuid4())]

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(attempt_payout, keys))

        # Exactly one success, one failure
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)

        # Balance integrity check
        available = self.merchant.get_available_balance()
        held = self.merchant.get_held_balance()
        self.assertEqual(available + held, 10000)

        # Database-level invariant: sum(credits) - sum(debits) == balance + held
        total_credits = Transaction.objects.filter(
            merchant=self.merchant, txn_type=Transaction.CREDIT
        ).aggregate(t=Sum("amount_paise"))["t"] or 0
        total_debits = Transaction.objects.filter(
            merchant=self.merchant, txn_type=Transaction.DEBIT
        ).aggregate(t=Sum("amount_paise"))["t"] or 0

        self.assertEqual(total_credits - total_debits, available)
```

### 9.2 Idempotency Test (`test_idempotency.py`)

```python
class IdempotencyTest(TestCase):

    def test_same_key_returns_same_response(self):
        key = str(uuid.uuid4())
        result1 = create_payout(self.merchant, 1000,
                                 str(self.bank_account.id), key)
        result2 = create_payout(self.merchant, 1000,
                                 str(self.bank_account.id), key)

        # Same payout ID
        self.assertEqual(result1["data"]["id"], result2["data"]["id"])
        # Second call is served from cache
        self.assertFalse(result1["cached"])
        self.assertTrue(result2["cached"])
        # Only one Payout row created
        self.assertEqual(Payout.objects.filter(merchant=self.merchant).count(), 1)

    def test_different_keys_create_different_payouts(self):
        result1 = create_payout(self.merchant, 1000,
                                 str(self.bank_account.id), str(uuid.uuid4()))
        result2 = create_payout(self.merchant, 1000,
                                 str(self.bank_account.id), str(uuid.uuid4()))
        self.assertNotEqual(result1["data"]["id"], result2["data"]["id"])

    def test_key_scoped_per_merchant(self):
        # Same key used by two different merchants — both should succeed
        key = str(uuid.uuid4())
        result1 = create_payout(self.merchant1, 1000,
                                  str(self.bank_account1.id), key)
        result2 = create_payout(self.merchant2, 1000,
                                  str(self.bank_account2.id), key)
        self.assertNotEqual(result1["data"]["id"], result2["data"]["id"])
```

---

## 10. Deployment

### 10.1 Recommended: Railway

1. Push to GitHub.
2. Create a Railway project → add a PostgreSQL plugin and a Redis plugin.
3. Create two services from the same repo: `web` and `worker`.
4. Set environment variables: `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.
5. `web` start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
6. `worker` start command: `celery -A config worker -B -l info` (`-B` runs beat in the same process; split for production)
7. Run `python manage.py migrate && python manage.py seed` via Railway's shell or a one-off command.

### 10.2 Frontend

Deploy to Vercel. Set `VITE_API_URL` to your Railway backend URL.

---

## 11. EXPLAINER.md Answers

Use these as a starting framework. Fill in with your actual code once written.

### 1. The Ledger

> Paste your balance calculation query. Why did you model credits and debits this way?

```python
credits = merchant.transactions.filter(
    txn_type=Transaction.CREDIT
).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

debits = merchant.transactions.filter(
    txn_type=Transaction.DEBIT
).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

available = credits - debits - held
```

I modeled the ledger as immutable append-only records (no updates, no deletes) because every money event is a fact. Storing balance as a derived value means it is always self-consistent with the transaction history. A stored balance column would require careful synchronization across payout creation, completion, and failure — three separate code paths where a bug could corrupt it silently.

### 2. The Lock

> Paste the exact code that prevents two concurrent payouts from overdrawing. Explain what database primitive it relies on.

```python
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
    # ... balance calculation and payout creation inside the same transaction
```

`select_for_update()` translates to `SELECT ... FOR UPDATE` in PostgreSQL. This acquires a row-level exclusive lock on the merchant row. Any other transaction attempting `SELECT ... FOR UPDATE` on the same row will block until the first transaction commits or rolls back. This serializes all balance-check-then-deduct operations for the same merchant at the database level, not just the Python level. Python-level threading locks (`threading.Lock`) would not protect against concurrent requests handled by multiple Gunicorn workers.

### 3. The Idempotency

> How does your system know it has seen a key before? What happens if the first request is in flight when the second arrives?

The system checks `IdempotencyRecord` for a matching `(merchant, key)` before acquiring any lock. If found and not expired, it returns the cached response immediately.

If the first request is in flight when the second arrives: the `unique_together` constraint on `IdempotencyRecord(merchant, key)` means the second request will either find the record (if the first committed) or get a `IntegrityError` on insert (if the first is still in its transaction). The second path should be handled by catching the integrity error and retrying the lookup — the first request will have committed by then.

### 4. The State Machine

> Where in the code is failed-to-completed blocked? Show the check.

```python
# In services.py — transition_payout()
VALID_TRANSITIONS = {
    "pending": ["processing"],
    "processing": ["completed", "failed"],
    "completed": [],    # terminal
    "failed": [],       # terminal
}

if new_status not in Payout.VALID_TRANSITIONS.get(payout.status, []):
    raise ValueError(f"Illegal transition: {payout.status} → {new_status}")
```

`completed` and `failed` map to empty lists, so any attempted transition from either raises a `ValueError`. The check runs twice: once before acquiring the lock (fast fail), and once after (correctness guarantee).

### 5. The AI Audit

Document one specific example where the AI gave you subtly wrong code and what you fixed. Common areas to watch:

- AI often suggests `select_for_update()` without putting the balance calculation inside the same `atomic()` block — the lock is useless if you release it before the write.
- AI often calculates balance by fetching rows and summing in Python (`sum(t.amount_paise for t in transactions)`) instead of using `aggregate()` — this is a TOCTOU race.
- AI sometimes writes `DecimalField` for money because it "sounds safer" than integers.

---

## 12. Checklist Before Submission

### Backend
- [ ] All amounts stored as `BigIntegerField` in paise
- [ ] No `FloatField` or `DecimalField` used for amounts
- [ ] Balance derived from aggregation, never from Python arithmetic on fetched rows
- [ ] `select_for_update()` used for concurrency control
- [ ] Balance calculation inside the same `atomic()` block as payout creation
- [ ] `IdempotencyRecord` table created with `expires_at`
- [ ] Idempotency check happens before the lock
- [ ] State machine enforces `VALID_TRANSITIONS`
- [ ] Failed payout fund return is atomic with status transition
- [ ] Completed payout DEBIT is atomic with status transition
- [ ] Celery worker actually runs (not faked with sync code)
- [ ] `retry_stuck_payouts` periodic task configured in Celery Beat
- [ ] Exponential backoff implemented
- [ ] Max 3 retry attempts, then FAILED

### Database
- [ ] `unique_together = [("merchant", "idempotency_key")]` on `Payout`
- [ ] `unique_together = [("merchant", "key")]` on `IdempotencyRecord`
- [ ] Indexes on `status`, `created_at`, `expires_at`
- [ ] Migrations committed to repo

### API
- [ ] `POST /api/v1/payouts/` requires `Idempotency-Key` header
- [ ] Returns `422` for insufficient balance (not `400`)
- [ ] Returns identical response on key replay
- [ ] CORS configured for frontend origin

### Frontend
- [ ] Available balance shown in INR (paise / 100)
- [ ] Held balance shown separately
- [ ] Payout form validates amount > 0 before submit
- [ ] Payout history polls for live updates
- [ ] Status badges clearly differentiated by color

### Testing
- [ ] Concurrency test uses `TransactionTestCase` (not `TestCase`)
- [ ] Concurrency test verifies exactly 1 success + 1 failure
- [ ] Ledger invariant verified in concurrency test
- [ ] Idempotency test verifies same payout ID on replay
- [ ] All tests pass: `python manage.py test`

### Repo & Deployment
- [ ] Clean commit history (not one giant commit)
- [ ] `README.md` with local setup steps
- [ ] Seed script works: `python manage.py seed`
- [ ] Live deployment seeded with test data
- [ ] `EXPLAINER.md` with all 5 questions answered with actual code snippets

---

## Day-by-Day Schedule Suggestion

| Day | Focus |
|-----|-------|
| 1 | Django project setup, models, migrations, seed script |
| 2 | Services layer (balance, locking, idempotency, state machine), API views |
| 3 | Celery tasks (processor + retry), integration tests |
| 4 | React frontend — dashboard, payout form, live polling |
| 5 | Deployment, EXPLAINER.md, final review |

---

*Good luck. The EXPLAINER.md is where this is won or lost — write it as you build, not after.*
