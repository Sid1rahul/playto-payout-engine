"""
Utility functions for API responses, validation, and formatting.
"""

from rest_framework.response import Response
from rest_framework import status as http_status
from django.utils import timezone
from datetime import datetime


class APIResponse:
    """Standardized API response wrapper with metadata."""

    @staticmethod
    def success(data=None, message=None, status_code=200):
        """Return a successful response."""
        response_data = {
            "success": True,
            "data": data or {},
            "timestamp": timezone.now().isoformat(),
        }
        if message:
            response_data["message"] = message
        return Response(response_data, status=status_code)

    @staticmethod
    def error(error=None, message=None, code=None, status_code=400):
        """Return an error response."""
        response_data = {
            "success": False,
            "error": error or "An error occurred",
            "timestamp": timezone.now().isoformat(),
        }
        if message:
            response_data["message"] = message
        if code:
            response_data["code"] = code
        return Response(response_data, status=status_code)


class ValidationError:
    """Validation error codes and messages."""

    MISSING_FIELD = ("missing_field", "Required field is missing")
    INVALID_TYPE = ("invalid_type", "Invalid data type")
    INVALID_UUID = ("invalid_uuid", "Invalid UUID format")
    NOT_FOUND = ("not_found", "Resource not found")
    INSUFFICIENT_BALANCE = ("insufficient_balance", "Insufficient balance")
    INVALID_BANK_ACCOUNT = ("invalid_bank_account", "Invalid bank account")
    DUPLICATE_REQUEST = ("duplicate_request", "Request is duplicate or already processed")
    INVALID_TRANSITION = ("invalid_transition", "Invalid state transition")


def validate_uuid(value):
    """Validate UUID format."""
    try:
        import uuid
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def validate_positive_integer(value):
    """Validate positive integer."""
    try:
        return isinstance(value, int) and value > 0
    except (TypeError, ValueError):
        return False


def validate_merchant_exists(merchant_id):
    """Check if merchant exists."""
    from .models import Merchant
    try:
        return Merchant.objects.get(pk=merchant_id)
    except Merchant.DoesNotExist:
        return None


def format_currency(paise, decimals=2):
    """Format paise amount as INR string (for logging)."""
    rupees = paise / 100
    return f"₹{rupees:,.{decimals}f}"
