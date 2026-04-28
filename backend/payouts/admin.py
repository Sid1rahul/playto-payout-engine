from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Merchant, Transaction, BankAccount, Payout, IdempotencyRecord


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'balance_display', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'email', 'id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'balance_display')
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'email')
        }),
        ('Balance', {
            'fields': ('balance_display',),
            'description': 'Balance is calculated from transactions and held payouts'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def balance_display(self, obj):
        available = obj.get_available_balance()
        held = obj.get_held_balance()
        total = available + held
        return f"Available: ₹{available/100:.2f} | Held: ₹{held/100:.2f} | Total: ₹{total/100:.2f}"
    balance_display.short_description = 'Balance Summary'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'merchant_link', 'txn_type_badge', 'amount_display', 'description', 'created_at')
    list_filter = ('txn_type', 'created_at')
    search_fields = ('merchant__name', 'merchant__email', 'id', 'description')
    readonly_fields = ('id', 'merchant', 'payout', 'created_at', 'amount_display')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'merchant', 'txn_type', 'amount_display', 'description')
        }),
        ('Payout Reference', {
            'fields': ('payout',),
            'description': 'Link to associated payout (if any)'
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def txn_type_badge(self, obj):
        if obj.txn_type == 'credit':
            color = 'green'
            label = '✓ CREDIT'
        else:
            color = 'red'
            label = '✗ DEBIT'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 6px; border-radius: 3px;">{}</span>',
            color, label
        )
    txn_type_badge.short_description = 'Type'

    def merchant_link(self, obj):
        url = reverse('admin:payouts_merchant_change', args=[obj.merchant.id])
        return format_html('<a href="{}">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def amount_display(self, obj):
        return f"₹{obj.amount_paise/100:.2f} ({obj.amount_paise} paise)"
    amount_display.short_description = 'Amount'


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('account_holder_name', 'account_number_masked', 'ifsc_code', 'merchant_link', 'status_badge', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('merchant__name', 'account_holder_name', 'account_number', 'id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Account Details', {
            'fields': ('id', 'merchant', 'account_holder_name', 'account_number', 'ifsc_code')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def account_number_masked(self, obj):
        if len(obj.account_number) > 4:
            return f"****{obj.account_number[-4:]}"
        return "****"
    account_number_masked.short_description = 'Account Number'

    def merchant_link(self, obj):
        url = reverse('admin:payouts_merchant_change', args=[obj.merchant.id])
        return format_html('<a href="{}">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def status_badge(self, obj):
        color = 'green' if obj.is_active else 'red'
        status = 'ACTIVE' if obj.is_active else 'INACTIVE'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 6px; border-radius: 3px;">{}</span>',
            color, status
        )
    status_badge.short_description = 'Status'


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'merchant_link', 'amount_display', 'status_badge', 'attempt_count', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('merchant__name', 'merchant__email', 'id', 'idempotency_key')
    readonly_fields = ('id', 'created_at', 'updated_at', 'amount_display', 'transaction_count')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Payout Information', {
            'fields': ('id', 'merchant', 'bank_account', 'amount_display', 'status_badge')
        }),
        ('Processing Details', {
            'fields': ('attempt_count', 'processing_started_at', 'failure_reason', 'transaction_count')
        }),
        ('Idempotency', {
            'fields': ('idempotency_key',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def merchant_link(self, obj):
        url = reverse('admin:payouts_merchant_change', args=[obj.merchant.id])
        return format_html('<a href="{}">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def amount_display(self, obj):
        return f"₹{obj.amount_paise/100:.2f} ({obj.amount_paise} paise)"
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        colors = {
            'pending': '#ffc107',
            'processing': '#17a2b8',
            'completed': '#28a745',
            'failed': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 6px; border-radius: 3px; text-transform: uppercase;">{}</span>',
            color, obj.status
        )
    status_badge.short_description = 'Status'

    def transaction_count(self, obj):
        count = obj.transactions.count()
        return f"{count} transaction(s)"
    transaction_count.short_description = 'Transactions'


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ('merchant_link', 'key_display', 'response_status', 'expires_at_display', 'created_at')
    list_filter = ('response_status', 'created_at', 'expires_at')
    search_fields = ('merchant__name', 'merchant__email', 'key')
    readonly_fields = ('id', 'key', 'merchant', 'response_body_formatted', 'created_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Idempotency Information', {
            'fields': ('id', 'merchant', 'key')
        }),
        ('Cached Response', {
            'fields': ('response_status', 'response_body_formatted'),
            'classes': ('wide',)
        }),
        ('Expiration', {
            'fields': ('expires_at_display',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def merchant_link(self, obj):
        url = reverse('admin:payouts_merchant_change', args=[obj.merchant.id])
        return format_html('<a href="{}">{}</a>', url, obj.merchant.name)
    merchant_link.short_description = 'Merchant'

    def key_display(self, obj):
        return f"{obj.key[:8]}...{obj.key[-8:]}"
    key_display.short_description = 'Idempotency Key'

    def expires_at_display(self, obj):
        from django.utils import timezone
        now = timezone.now()
        if obj.expires_at < now:
            return format_html(
                '<span style="color: red;">Expired ({} ago)</span>',
                obj.expires_at
            )
        return obj.expires_at
    expires_at_display.short_description = 'Expires At'

    def response_body_formatted(self, obj):
        import json
        try:
            formatted = json.dumps(obj.response_body, indent=2)
            return format_html(
                '<pre style="background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto;">{}</pre>',
                formatted
            )
        except:
            return str(obj.response_body)
    response_body_formatted.short_description = 'Response Body'
