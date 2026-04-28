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
    merchant_id = serializers.CharField(source='merchant.id', read_only=True)
    bank_account_id = serializers.CharField(source='bank_account.id', read_only=True)
    failure_reason = serializers.SerializerMethodField()

    def get_failure_reason(self, obj):
        return obj.failure_reason or None
    
    class Meta:
        model = Payout
        fields = [
            'id', 'merchant_id', 'bank_account_id', 'amount_paise', 'status',
            'idempotency_key', 'attempt_count', 'failure_reason',
            'processing_started_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'attempt_count', 'failure_reason',
            'processing_started_at', 'created_at', 'updated_at'
        ]
