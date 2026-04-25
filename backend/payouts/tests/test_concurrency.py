"""
Concurrency tests for payout processing.

These tests verify that the locking mechanism (select_for_update)
prevents overdraft scenarios where two concurrent requests could both
succeed despite insufficient balance.
"""

from django.test import TransactionTestCase
from concurrent.futures import ThreadPoolExecutor
from django.db.models import Sum
from payouts.models import Merchant, BankAccount, Transaction, Payout
from payouts.services import create_payout
import uuid
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

        This test verifies:
        1. The locking mechanism prevents double-spending
        2. Ledger invariant is maintained (credits - debits == balance + held)
        3. Only one payout is created
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

        keys = [str(uuid.uuid4()), str(uuid.uuid4())]

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(attempt_payout, keys))

        # Exactly one success, one failure
        self.assertEqual(len(results), 1, "Expected exactly one successful payout")
        self.assertEqual(len(errors), 1, "Expected exactly one failed payout")
        self.assertIn("Insufficient balance", errors[0])

        # Verify only one payout was created
        payout_count = Payout.objects.filter(merchant=self.merchant).count()
        self.assertEqual(payout_count, 1, "Expected exactly one payout in database")

        # Balance integrity check
        available = self.merchant.get_available_balance()
        held = self.merchant.get_held_balance()
        total_balance = available + held

        # Should be 10000 - 6000 = 4000 available, 6000 held
        self.assertEqual(available, 4000, "Available balance incorrect")
        self.assertEqual(held, 6000, "Held balance incorrect")
        self.assertEqual(total_balance, 10000, "Total balance invariant violated")

        # Database-level invariant: sum(credits) - sum(debits) == balance + held
        total_credits = (
            Transaction.objects.filter(
                merchant=self.merchant, txn_type=Transaction.CREDIT
            ).aggregate(t=Sum("amount_paise"))["t"]
            or 0
        )
        total_debits = (
            Transaction.objects.filter(
                merchant=self.merchant, txn_type=Transaction.DEBIT
            ).aggregate(t=Sum("amount_paise"))["t"]
            or 0
        )

        ledger_sum = total_credits - total_debits
        self.assertEqual(ledger_sum, total_balance, "Ledger invariant violated")

    def test_three_concurrent_requests_partial_success(self):
        """
        With 100 INR balance, three simultaneous 40 INR payout requests.
        Only the first should succeed, the other two should fail.
        """
        results = []
        errors = []
        lock = threading.Lock()

        def attempt_payout(key):
            try:
                result = create_payout(
                    merchant=self.merchant,
                    amount_paise=4000,
                    bank_account_id=str(self.bank_account.id),
                    idempotency_key=key,
                )
                with lock:
                    results.append(result)
            except ValueError as e:
                with lock:
                    errors.append(str(e))

        keys = [str(uuid.uuid4()) for _ in range(3)]

        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(attempt_payout, keys))

        # Exactly one success, two failures
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 2)

        # Verify ledger invariant
        available = self.merchant.get_available_balance()
        held = self.merchant.get_held_balance()
        self.assertEqual(available + held, 10000)
