from django.urls import path
from .views import (
    DebugSeedDataView,
    MerchantBalanceView,
    MerchantTransactionsView,
    MerchantPayoutsView,
    PayoutCreateView,
    PayoutDetailView,
)

urlpatterns = [
    path('debug/seed-data/', DebugSeedDataView.as_view(), name='debug-seed-data'),
    path('merchants/<str:merchant_id>/balance/', MerchantBalanceView.as_view(), name='merchant-balance'),
    path('merchants/<str:merchant_id>/transactions/', MerchantTransactionsView.as_view(), name='merchant-transactions'),
    path('merchants/<str:merchant_id>/payouts/', MerchantPayoutsView.as_view(), name='merchant-payouts'),
    path('payouts/', PayoutCreateView.as_view(), name='payout-create'),
    path('payouts/<str:payout_id>/', PayoutDetailView.as_view(), name='payout-detail'),
]
