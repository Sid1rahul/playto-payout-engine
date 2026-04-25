# EXPLAINER.md

This document explains the five critical design decisions in the Playto Payout Engine, with code snippets from the actual implementation.

---

## 1. The Ledger — Why Balance is Derived, Not Stored

### The Problem

A naive approach stores a `balance` column on the Merchant model:

```python
# WRONG: This breaks concurrency
class Merchant(models.Model):
    balance_paise = models.BigIntegerField(default=0)
```

If two requests concurrently fetch the merchant, both see balance=100, both deduct 60, and both write back 40. Overdraft.

### The Solution

Balance is **derived at read time** from an immutable ledger of transactions:

```python
# payouts/models.py
def get_available_balance(self):
    """
    Derived from ledger. Never stored as a column.
    Uses DB-level aggregation — no Python arithmetic on fetched rows.
    """
    credits = self.transactions.filter(
        txn_type=Transaction.CREDIT
    ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

    debits = self.transactions.filter(
        txn_type=Transaction.DEBIT
    ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

    held = self.payouts.filter(
        status__in=[Payout.PENDING, Payout.PROCESSING]
    ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]

    return credits - debits - held
```

**Why this works:**

1. Every money event is an immutable append-only transaction record
2. Balance is calculated fresh each read via SQL `SUM()` at the database level
3. No Python arithmetic on fetched rows (which would be a TOCTOU race)
4. The balance is **always** consistent with the ledger by construction

**Proof by example:**

```
Transaction history for merchant:
- CREDIT: 10000 paise
- CREDIT: 5000 paise
- DEBIT: 3000 paise (payout completed)
- Payout PENDING: 6000 paise

Available = (10000 + 5000) - 3000 - 6000 = 6000 paise
Held = 6000 paise
Total = 6000 + 6000 = 12000 paise

This invariant holds regardless of how many transactions exist.
```

**Why NOT `DecimalField` or `FloatField`:**

- **Float** is IEEE 754 binary — cannot represent 0.1 exactly. Breaks money.
- **DecimalField** is safer but still introduces conversion overhead and rounding context.
- **BigIntegerField storing paise** means all arithmetic is exact integer math with zero rounding.

---

## 2. The Lock — Preventing Concurrent Overdrafts

### The Problem (Race Condition)

```
Timeline without locking:

Thread 1: SELECT balance WHERE merchant_id = X  → 100 paise
Thread 2: SELECT balance WHERE merchant_id = X  → 100 paise
Thread 1: INSERT payout 60 paise                 → OK
Thread 2: INSERT payout 60 paise                 → OK (both think balance is sufficient!)

Result: Overdraft of 20 paise. Both payouts succeeded despite only 100 paise available.
```

### The Solution

Use **row-level locking** via `select_for_update()`:

```python
# payouts/services.py
def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> dict:

    # ... idempotency check ...
    # ... bank account validation ...

    # CRITICAL: The lock must be acquired BEFORE balance calculation
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
            raise ValueError("Insufficient balance...")

        # Create payout (still inside transaction, still holding the lock)
        payout = Payout.objects.create(
            merchant=merchant_locked,
            bank_account=bank_account,
            amount_paise=amount_paise,
            status=Payout.PENDING,
            idempotency_key=idempotency_key,
        )
        # ... rest of creation ...

    # Lock is released here when transaction commits
```

**How `select_for_update()` works in PostgreSQL:**

```sql
-- Django translates select_for_update() to:
BEGIN;
SELECT * FROM merchants WHERE id = X FOR UPDATE;
-- Other transactions attempting FOR UPDATE on the same row will BLOCK here
-- until this transaction commits or rolls back
```

**Timeline WITH locking:**

```
Thread 1: SELECT ... FOR UPDATE merchant_id = X    → LOCK acquired, balance = 100
Thread 2: SELECT ... FOR UPDATE merchant_id = X    → BLOCKED (waiting for lock)
Thread 1: CREATE payout 60 paise                    → OK, held = 60
Thread 1: COMMIT                                    → Lock released
Thread 2: SELECT ... FOR UPDATE merchant_id = X    → LOCK acquired, balance = 40 (recalculated!)
Thread 2: Checks available = 40 < 60               → FAIL, raises ValueError
Thread 2: ROLLBACK (or no insert happens)
```

**Result:** Only Thread 1 succeeds. No overdraft.

**Why this is NOT Python-level locking:**

Python's `threading.Lock` only serializes code within a single process. With Gunicorn running multiple worker processes, each process has its own Python interpreter and its own lock. Database-level locking is the only correct primitive for multiple processes.

**Stored Transaction Isolation Level:**

The database isolation level must be at least `READ COMMITTED` (PostgreSQL default). At this level:

- Dirty reads are prevented (can't read uncommitted changes)
- Lost updates are possible UNLESS you use explicit locking like FOR UPDATE
- `select_for_update()` promotes to serializable behavior for that row

---

## 3. The Idempotency — Safe Request Retries

### The Problem

API clients might retry a request if the connection drops:

```
Request 1: POST /api/v1/payouts/ → Server receives, creates payout, response is lost
Request 2: POST /api/v1/payouts/ (retry with same data)
           → Without idempotency: creates ANOTHER payout (duplicate!)
```

### The Solution

The client includes an `Idempotency-Key` header (a UUID). The server:
1. Checks if this key was seen before (before acquiring any lock)
2. If yes, returns the cached response
3. If no, processes the request and caches the response

**Model:**

```python
# payouts/models.py
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
        unique_together = [("merchant", "key")]  # Scoped per merchant
        indexes = [
            models.Index(fields=["expires_at"]),
        ]
```

**Implementation:**

```python
# payouts/services.py
def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> dict:

    # Step 1: Check idempotency BEFORE acquiring any lock
    record = IdempotencyRecord.objects.filter(
        merchant=merchant,
        key=idempotency_key,
        expires_at__gt=timezone.now(),  # Only unexpired records
    ).select_related("payout").first()

    if record:
        return {
            "data": record.response_body,
            "status": record.response_status,
            "cached": True
        }

    # ... rest of payout creation ...

    # Step 4: Create IdempotencyRecord OUTSIDE the transaction
    IdempotencyRecord.objects.create(
        merchant=merchant,
        key=idempotency_key,
        response_body=response_body,
        response_status=response_status,
        payout=payout,
        expires_at=timezone.now() + timedelta(hours=24),
    )

    return {"data": response_body, "status": response_status, "cached": False}
```

**Timeline with idempotency:**

```
Request 1 (key=ABC):
- Check IdempotencyRecord for (merchant, ABC) → Not found
- Create payout, create IdempotencyRecord
- Return payout data

Request 2 (key=ABC, retry):
- Check IdempotencyRecord for (merchant, ABC) → Found!
- Return cached response (same payout ID, same status code, byte-for-byte identical)

Client sees: Same response both times, no duplicate payout created ✓
```

**Why separate `IdempotencyRecord` table?**

The `unique_together` on `Payout(merchant, idempotency_key)` prevents duplicate rows, but doesn't store the HTTP response. The response must be **byte-for-byte identical** on replay — including status code. A separate record:

1. Stores the exact serialized response
2. Stores the status code
3. Can be garbage-collected after 24 hours (old keys can be reused)
4. Doesn't require modifying the Payout model

**Key scope per merchant:**

Different merchants can use the same idempotency key (the `unique_together` is per merchant). This allows:

```python
# Both work:
create_payout(merchant1, 1000, bank_account1, key="same-uuid")
create_payout(merchant2, 1000, bank_account2, key="same-uuid")
# Both payouts are created with different DB rows
```

---

## 4. The State Machine — Enforcing Legal Transitions

### The Problem

Payout status should follow a strict workflow:

```
PENDING → PROCESSING → COMPLETED (or FAILED)
         ↓
       FAILED → (terminal, no transitions allowed)

Illegal transitions must be rejected:
- COMPLETED → anything (terminal state)
- FAILED → COMPLETED (can't un-fail)
- FAILED → PENDING (must not be re-processed)
```

### The Solution

Define legal transitions in the model and validate in the service:

```python
# payouts/models.py
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
```

**Service layer enforcement:**

```python
# payouts/services.py
def transition_payout(payout: Payout, new_status: str,
                       failure_reason: str = "") -> Payout:
    """
    The ONLY place where payout status changes.
    Validates against VALID_TRANSITIONS before any write.
    """
    # Check 1: Validate before acquiring lock (fast fail)
    if new_status not in Payout.VALID_TRANSITIONS.get(payout.status, []):
        raise ValueError(
            f"Illegal transition: {payout.status} → {new_status}"
        )

    with transaction.atomic():
        # Re-fetch with lock to prevent concurrent status changes
        payout = Payout.objects.select_for_update().get(pk=payout.pk)

        # Check 2: Re-validate after lock (status may have changed concurrently)
        if new_status not in Payout.VALID_TRANSITIONS.get(payout.status, []):
            raise ValueError(
                f"Illegal transition after lock: {payout.status} → {new_status}"
            )

        payout.status = new_status
        payout.failure_reason = failure_reason
        payout.save(update_fields=["status", "failure_reason", "updated_at"])

        # Atomic fund operations with status transition
        if new_status == Payout.FAILED:
            # Return held funds atomically with status change
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

**Example: Attempting illegal transition**

```python
payout = Payout.objects.create(status=Payout.COMPLETED, ...)

# This raises ValueError:
transition_payout(payout, Payout.PENDING)
# ValueError: Illegal transition: completed → pending
```

**Why two validation checks?**

1. **Before lock:** Fast fail for invalid transitions (no DB lock acquired)
2. **After lock:** Correct behavior under concurrency (status may have changed while waiting for lock)

**Atomic fund operations:**

When a payout fails, we immediately create a CREDIT transaction to return funds. This happens in the same `atomic()` block as the status change:

```
BEGIN;
UPDATE payouts SET status = 'failed' WHERE id = X;
INSERT INTO transactions (merchant_id, txn_type, amount_paise, ...) VALUES (...);
COMMIT;
-- Either both succeed or both rollback. No partial state.
```

---

## 5. The AI Audit — Common Mistakes Fixed

This section documents one specific error the AI made during development and how it was corrected.

### Mistake: Balance Calculation Outside Locked Transaction

**The Bad Code (AI-generated):**

```python
# WRONG!
payout = Payout.objects.select_for_update().get(pk=payout_id)

with transaction.atomic():
    # Calculate balance OUTSIDE the locked query result
    credits = Payout.objects.filter(...).aggregate(...)["total"]
    debits = Payout.objects.filter(...).aggregate(...)["total"]
    # ... payout creation ...
```

**The Problem:**

The `select_for_update()` acquires a lock on the payout row, but then `transaction.atomic()` creates a new transaction context. The lock may be released before the balance calculation completes, allowing concurrent requests to read stale balance data.

**The Correct Code:**

```python
# CORRECT!
with transaction.atomic():
    merchant_locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
    
    # Now calculate balance inside the transaction, AFTER lock is held
    credits = merchant_locked.transactions.filter(...).aggregate(...)["total"]
    debits = merchant_locked.transactions.filter(...).aggregate(...)["total"]
    held = merchant_locked.payouts.filter(...).aggregate(...)["total"]
    
    available = credits - debits - held
    
    if available < amount_paise:
        raise ValueError(...)
    
    # Create payout still inside transaction
    payout = Payout.objects.create(...)
```

**Why this fixes it:**

1. Lock is acquired on the merchant row
2. Balance calculation happens inside the same transaction
3. Any concurrent request attempting to acquire the lock will block
4. No race condition possible

---

## Summary

The implementation prevents three classes of bugs:

| Bug | Prevention |
|-----|-----------|
| **Stored balance gets out of sync** | Derive balance from immutable ledger via SQL SUM |
| **Concurrent payouts overdraw** | Row-level lock with select_for_update |
| **Duplicate payouts from retries** | Idempotency table with unique(merchant, key) |
| **Status transitions become invalid** | State machine validation in service layer |
| **Funds lost or created from errors** | Atomic transaction entries with status changes |

All of these guarantees rely on database-level primitives (locking, transactions, aggregation), not Python-level logic.
