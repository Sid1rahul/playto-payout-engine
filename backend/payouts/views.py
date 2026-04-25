from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Merchant, Payout, Transaction, BankAccount
from .services import create_payout
from .serializers import MerchantSerializer, TransactionSerializer, PayoutSerializer
import uuid


class MerchantBalanceView(APIView):
    """GET /api/v1/merchants/{id}/balance/"""
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "merchant_id": str(merchant.id),
            "merchant_name": merchant.name,
            "available_balance_paise": merchant.get_available_balance(),
            "held_balance_paise": merchant.get_held_balance(),
        })


class MerchantTransactionsView(APIView):
    """GET /api/v1/merchants/{id}/transactions/"""
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

        transactions = merchant.transactions.all().order_by('-created_at')[:100]
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)


class MerchantPayoutsView(APIView):
    """GET /api/v1/merchants/{id}/payouts/"""
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant not found"}, status=status.HTTP_404_NOT_FOUND)

        payouts = merchant.payouts.all().order_by('-created_at')[:100]
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)


class PayoutCreateView(APIView):
    """POST /api/v1/payouts/"""
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


class PayoutDetailView(APIView):
    """GET /api/v1/payouts/{id}/"""
    def get(self, request, payout_id):
        try:
            payout = Payout.objects.get(pk=payout_id)
        except Payout.DoesNotExist:
            return Response({"error": "Payout not found"},
                             status=status.HTTP_404_NOT_FOUND)

        serializer = PayoutSerializer(payout)
        return Response(serializer.data)
