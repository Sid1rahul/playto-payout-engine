import uuid
from django.db import models
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

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

    def get_held_balance(self):
        """Get the total amount held in pending/processing payouts."""
        return self.payouts.filter(
            status__in=[Payout.PENDING, Payout.PROCESSING]
        ).aggregate(total=Coalesce(Sum("amount_paise"), Value(0)))["total"]


class Transaction(models.Model):
    CREDIT = "credit"
    DEBIT = "debit"
    TXN_TYPES = [(CREDIT, "Credit"), (DEBIT, "Debit")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT,
                                  related_name="transactions")
    txn_type = models.CharField(max_length=10, choices=TXN_TYPES)
    amount_paise = models.BigIntegerField()  # ALWAYS BigIntegerField for money
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

    def __str__(self):
        return f"{self.txn_type} {self.amount_paise} paise on {self.created_at}"


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT,
                                  related_name="bank_accounts")
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_holder_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_holder_name} - {self.account_number}"


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

    def __str__(self):
        return f"Payout {self.id} - {self.amount_paise} paise - {self.status}"


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

    def __str__(self):
        return f"Idempotency {self.key} - {self.response_status}"
