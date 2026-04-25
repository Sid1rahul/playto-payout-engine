from django.contrib import admin
from .models import Merchant, Transaction, BankAccount, Payout, IdempotencyRecord


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'created_at']
    search_fields = ['name', 'email']
    readonly_fields = ['id', 'created_at']


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'txn_type', 'amount_paise', 'created_at']
    list_filter = ['txn_type', 'created_at']
    search_fields = ['merchant__name']
    readonly_fields = ['id', 'created_at']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['account_holder_name', 'merchant', 'account_number', 'is_active']
    list_filter = ['is_active']
    search_fields = ['account_holder_name', 'merchant__name']
    readonly_fields = ['id', 'created_at']


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ['id', 'merchant', 'amount_paise', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['merchant__name', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ['merchant', 'key', 'response_status', 'created_at']
    list_filter = ['response_status', 'created_at']
    search_fields = ['merchant__name', 'key']
    readonly_fields = ['created_at']
