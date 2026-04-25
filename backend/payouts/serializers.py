from rest_framework import serializers
from .models import Merchant, Transaction, BankAccount, Payout


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ['id', 'name', 'email', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'merchant', 'txn_type', 'amount_paise', 'description', 'created_at']


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ['id', 'account_number', 'ifsc_code', 'account_holder_name', 'is_active', 'created_at']


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = [
            'id', 'merchant', 'bank_account', 'amount_paise', 'status',
            'idempotency_key', 'attempt_count', 'failure_reason',
            'processing_started_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'attempt_count', 'failure_reason',
            'processing_started_at', 'created_at', 'updated_at'
        ]
