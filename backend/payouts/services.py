"""
Core business logic for payouts.
All balance operations, state transitions, and fund holds happen here.
"""

from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from .models import Merchant, Payout, Transaction, IdempotencyRecord, BankAccount


def _serialize_payout(payout: Payout) -> dict:
    """Serialize a payout to JSON-serializable dict."""
    return {
        "id": str(payout.id),
        "merchant_id": str(payout.merchant_id),
        "amount_paise": payout.amount_paise,
        "status": payout.status,
        "bank_account_id": str(payout.bank_account_id),
        "created_at": payout.created_at.isoformat(),
        "updated_at": payout.updated_at.isoformat(),
    }


def create_payout(merchant: Merchant, amount_paise: int,
                  bank_account_id: str, idempotency_key: str) -> dict:
    """
    Create a new payout with idempotency and balance checking.

    Step 1: Check idempotency BEFORE acquiring any lock.
    Step 2: Validate bank account belongs to this merchant.
    Step 3: Atomic balance check + fund hold (with select_for_update lock).
    Step 4: Create IdempotencyRecord outside the transaction.
    Step 5: Enqueue background processing outside the transaction.

    Returns:
        dict with keys:
            - data: serialized payout response
            - status: HTTP status code (201 or 200)
            - cached: boolean indicating if this was a cached response
    """

    # Step 1: Check idempotency BEFORE acquiring any lock
    record = IdempotencyRecord.objects.filter(
        merchant=merchant,
        key=idempotency_key,
        expires_at__gt=timezone.now(),
    ).select_related("payout").first()

    if record:
        return {
            "data": record.response_body,
            "status": record.response_status,
            "cached": True
        }

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

    return {
        "data": response_body,
        "status": response_status,
        "cached": False
    }


def transition_payout(payout: Payout, new_status: str,
                       failure_reason: str = "") -> Payout:
    """
    The ONLY place where payout status changes.
    Validates against VALID_TRANSITIONS before any write.

    This function:
    1. Validates the transition is legal
    2. Acquires a lock on the payout row
    3. Re-validates after lock (status may have changed concurrently)
    4. Updates status and failure_reason
    5. If failed: creates a CREDIT transaction (refund) atomically
    6. If completed: creates a DEBIT transaction (settlement) atomically

    Args:
        payout: The Payout instance
        new_status: The target status (pending, processing, completed, failed)
        failure_reason: Optional explanation if transitioning to failed

    Returns:
        The updated Payout instance

    Raises:
        ValueError: If the transition is illegal
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
