from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from datetime import datetime
import logging
import uuid

from .models import Merchant, Payout, Transaction, BankAccount
from .services import create_payout
from .serializers import MerchantSerializer, TransactionSerializer, PayoutSerializer
from .utils import APIResponse, ValidationError

logger = logging.getLogger('payouts')


class DebugSeedDataView(APIView):
    """GET /api/v1/debug/seed-data/"""
    def get(self, request):
        merchants = [
            {
                "id": str(merchant.id),
                "name": merchant.name,
                "balance": merchant.get_available_balance(),
            }
            for merchant in Merchant.objects.all().order_by("name")
        ]

        bank_accounts = [
            {
                "id": str(bank_account.id),
                "merchant_id": str(bank_account.merchant_id),
            }
            for bank_account in BankAccount.objects.all().order_by("created_at")
        ]

        return Response({
            "merchants": merchants,
            "bank_accounts": bank_accounts,
        })


class MerchantBalanceView(APIView):
    """GET /api/v1/merchants/{id}/balance/
    
    Returns the current balance for a merchant, including available and held amounts.
    """
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            logger.warning(f"Merchant {merchant_id} not found")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Merchant not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        data = {
            "merchant_id": str(merchant.id),
            "merchant_name": merchant.name,
            "available_balance_paise": merchant.get_available_balance(),
            "held_balance_paise": merchant.get_held_balance(),
        }
        return APIResponse.success(data=data, status_code=200)


class MerchantTransactionsView(APIView):
    """GET /api/v1/merchants/{id}/transactions/?limit=100
    
    Returns the transaction history for a merchant.
    """
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            logger.warning(f"Merchant {merchant_id} not found")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Merchant not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        try:
            limit = int(request.query_params.get('limit', 100))
            if limit <= 0 or limit > 1000:
                limit = 100
        except (ValueError, TypeError):
            limit = 100

        transactions = merchant.transactions.all().order_by('-created_at')[:limit]
        serializer = TransactionSerializer(transactions, many=True)
        
        data = {
            "merchant_id": str(merchant.id),
            "count": len(transactions),
            "transactions": serializer.data
        }
        return APIResponse.success(data=data, status_code=200)


class MerchantPayoutsView(APIView):
    """GET /api/v1/merchants/{id}/payouts/?status=pending&limit=100
    
    Returns the payout history for a merchant with optional filtering by status.
    Query parameters:
        - status: Filter by payout status (pending, processing, completed, failed)
        - limit: Maximum number of results (1-1000, default 100)
    """
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            logger.warning(f"Merchant {merchant_id} not found")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Merchant not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        # Build queryset with optional filtering
        queryset = merchant.payouts.all()
        
        # Filter by status if provided
        status_filter = request.query_params.get('status')
        if status_filter:
            valid_statuses = [choice[0] for choice in Payout.STATUS_CHOICES]
            if status_filter not in valid_statuses:
                logger.warning(f"Invalid status filter: {status_filter}")
                code, message = ValidationError.INVALID_TYPE
                return APIResponse.error(
                    error=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
                    code=code,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(status=status_filter)
            logger.debug(f"Filtering payouts for merchant {merchant_id} by status {status_filter}")
        
        # Pagination with limit parameter
        try:
            limit = int(request.query_params.get('limit', 100))
            if limit <= 0 or limit > 1000:
                limit = 100
        except (ValueError, TypeError):
            limit = 100
        
        payouts = queryset.order_by('-created_at')[:limit]
        serializer = PayoutSerializer(payouts, many=True)
        
        data = {
            "merchant_id": str(merchant.id),
            "count": len(payouts),
            "payouts": serializer.data
        }
        logger.debug(f"Returned {len(payouts)} payouts for merchant {merchant_id}")
        return APIResponse.success(data=data, status_code=200)


class PayoutCreateView(APIView):
    """POST /api/v1/payouts/ and GET /api/v1/payouts/?merchant_id=...
    
    Create a new payout request. Requires Idempotency-Key header for safe retries.
    
    Request body:
    {
        "merchant_id": "<uuid>",
        "amount_paise": <integer>,
        "bank_account_id": "<uuid>"
    }
    
    Headers:
        Idempotency-Key: <uuid> (required, for idempotency)
    
    Returns:
        201 Created: Payout was successfully created
        200 OK: Duplicate request with same Idempotency-Key
        400 Bad Request: Invalid input
        404 Not Found: Merchant or bank account not found
        422 Unprocessable Entity: Validation error (e.g., insufficient balance)
    """
    def get(self, request):
        merchant_id = request.query_params.get("merchant_id")
        if not merchant_id:
            logger.warning("Payout list request missing merchant_id query parameter")
            code, message = ValidationError.MISSING_FIELD
            return APIResponse.error(
                error="merchant_id query parameter is required",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            merchant_uuid = uuid.UUID(merchant_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid merchant_id format in payout list: {merchant_id}")
            code, message = ValidationError.INVALID_UUID
            return APIResponse.error(
                error="merchant_id must be a valid UUID",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            merchant = Merchant.objects.get(pk=merchant_uuid)
        except Merchant.DoesNotExist:
            logger.warning(f"Merchant {merchant_id} not found in payout list")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Merchant not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        queryset = Payout.objects.select_related(
            "merchant", "bank_account"
        ).filter(merchant=merchant)

        status_filter = request.query_params.get("status")
        if status_filter:
            valid_statuses = [choice[0] for choice in Payout.STATUS_CHOICES]
            if status_filter not in valid_statuses:
                logger.warning(f"Invalid status filter: {status_filter}")
                code, message = ValidationError.INVALID_TYPE
                return APIResponse.error(
                    error=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
                    code=code,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            queryset = queryset.filter(status=status_filter)

        try:
            limit = int(request.query_params.get("limit", 100))
            if limit <= 0 or limit > 1000:
                limit = 100
        except (ValueError, TypeError):
            limit = 100

        payouts = queryset.order_by("-created_at")[:limit]
        serializer = PayoutSerializer(payouts, many=True)
        data = {
            "merchant_id": str(merchant.id),
            "count": len(payouts),
            "payouts": serializer.data,
        }
        logger.debug(f"Returned {len(payouts)} payouts for merchant {merchant_id}")
        return APIResponse.success(data=data, status_code=200)

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")

        # Validate idempotency key presence and format
        if not idempotency_key:
            logger.warning("Payout creation request missing Idempotency-Key header")
            code, message = ValidationError.MISSING_FIELD
            return APIResponse.error(
                error="Idempotency-Key header is required",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )
        try:
            uuid.UUID(idempotency_key)
        except ValueError:
            logger.warning(f"Invalid Idempotency-Key format: {idempotency_key}")
            code, message = ValidationError.INVALID_UUID
            return APIResponse.error(
                error="Idempotency-Key must be a valid UUID",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        merchant_id = request.data.get("merchant_id")
        amount_paise = request.data.get("amount_paise")
        bank_account_id = request.data.get("bank_account_id")

        # Input validation
        if not all([merchant_id, amount_paise, bank_account_id]):
            logger.warning("Payout creation request missing required fields")
            code, message = ValidationError.MISSING_FIELD
            return APIResponse.error(
                error="Missing required fields: merchant_id, amount_paise, bank_account_id",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(amount_paise, int) or amount_paise <= 0:
            logger.warning(f"Invalid amount_paise: {amount_paise}")
            code, message = ValidationError.INVALID_TYPE
            return APIResponse.error(
                error="amount_paise must be a positive integer",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            merchant = Merchant.objects.get(pk=merchant_id)
        except Merchant.DoesNotExist:
            logger.warning(f"Merchant {merchant_id} not found in payout creation")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Merchant not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        try:
            result = create_payout(
                merchant=merchant,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=idempotency_key,
            )
            # For idempotent responses, return 200 OK; for new payouts, return 201 Created
            return Response(result["data"], status=result["status"])

        except ValueError as e:
            error_msg = str(e)
            logger.warning(f"Payout creation validation error: {error_msg}")
            
            # Determine error code based on message
            if "Insufficient balance" in error_msg:
                code = ValidationError.INSUFFICIENT_BALANCE[0]
            elif "Invalid bank account" in error_msg:
                code = ValidationError.INVALID_BANK_ACCOUNT[0]
            else:
                code = ValidationError.INVALID_TYPE[0]
            
            return APIResponse.error(
                error=error_msg,
                code=code,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )


class PayoutDetailView(APIView):
    """GET /api/v1/payouts/{id}/
    
    Retrieve details for a specific payout by its ID.
    
    Returns:
        200 OK: Payout details
        404 Not Found: Payout ID not found
    """
    def get(self, request, payout_id):
        try:
            payout_uuid = uuid.UUID(payout_id)
        except (ValueError, TypeError):
            logger.warning(f"Invalid payout_id format: {payout_id}")
            code, message = ValidationError.INVALID_UUID
            return APIResponse.error(
                error="payout_id must be a valid UUID",
                code=code,
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            payout = Payout.objects.select_related(
                "merchant", "bank_account"
            ).get(pk=payout_uuid)
        except (Payout.DoesNotExist, DjangoValidationError):
            logger.warning(f"Payout {payout_id} not found")
            code, message = ValidationError.NOT_FOUND
            return APIResponse.error(
                error="Payout not found",
                code=code,
                status_code=status.HTTP_404_NOT_FOUND
            )

        serializer = PayoutSerializer(payout)
        logger.debug(f"Retrieved payout {payout_id}")
        return APIResponse.success(data=serializer.data, status_code=200)
