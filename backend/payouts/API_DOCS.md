"""
API Documentation for Playto Payout Engine

All endpoints return JSON with the following structure:

Success Response (200/201):
{
    "success": true,
    "data": { ... },
    "timestamp": "2026-04-28T10:30:00Z",
    "message": "Optional message"
}

Error Response (4xx/5xx):
{
    "success": false,
    "error": "Error description",
    "code": "error_code",
    "timestamp": "2026-04-28T10:30:00Z",
    "message": "Optional additional details"
}

BASE URL: http://localhost:8000/api/v1

====================================================================
ENDPOINTS
====================================================================

1. GET /merchants/{merchant_id}/balance/
   -------
   Get the current balance for a merchant.
   
   Parameters:
     - merchant_id (path): UUID of the merchant
   
   Response 200:
   {
     "success": true,
     "data": {
       "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
       "merchant_name": "Acme Design Studio",
       "available_balance_paise": 500000,
       "held_balance_paise": 100000
     },
     "timestamp": "2026-04-28T10:30:00Z"
   }
   
   Response 404:
   {
     "success": false,
     "error": "Merchant not found",
     "code": "not_found",
     "timestamp": "2026-04-28T10:30:00Z"
   }


2. GET /merchants/{merchant_id}/transactions/?limit=100
   -------
   Get transaction history for a merchant.
   
   Parameters:
     - merchant_id (path): UUID of the merchant
     - limit (query, optional): Max results (default: 100, max: 1000)
   
   Response 200:
   {
     "success": true,
     "data": {
       "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
       "count": 3,
       "transactions": [
         {
           "id": "f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f1f1f1",
           "txn_type": "credit",
           "amount_paise": 500000,
           "description": "Customer payment",
           "created_at": "2026-04-28T10:00:00Z"
         },
         ...
       ]
     },
     "timestamp": "2026-04-28T10:30:00Z"
   }


3. GET /merchants/{merchant_id}/payouts/?status=pending&limit=100
   -------
   Get payout history for a merchant with optional filtering.
   
   Parameters:
     - merchant_id (path): UUID of the merchant
     - status (query, optional): Filter by status (pending, processing, completed, failed)
     - limit (query, optional): Max results (default: 100, max: 1000)
   
   Response 200:
   {
     "success": true,
     "data": {
       "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
       "count": 2,
       "payouts": [
         {
           "id": "a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0",
           "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
           "bank_account_id": "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1",
           "amount_paise": 300000,
           "status": "pending",
           "idempotency_key": "550e8400-e29b-41d4-a716-446655440001",
           "attempt_count": 0,
           "failure_reason": null,
           "processing_started_at": null,
           "created_at": "2026-04-28T10:00:00Z",
           "updated_at": "2026-04-28T10:00:00Z"
         },
         ...
       ]
     },
     "timestamp": "2026-04-28T10:30:00Z"
   }


4. POST /payouts/
   -------
   Create a new payout request. REQUIRES Idempotency-Key header.
   
   Headers (required):
     - Idempotency-Key: UUID (for safe retries)
   
   Request Body:
   {
     "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
     "amount_paise": 300000,
     "bank_account_id": "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1"
   }
   
   Response 201 (New payout created):
   {
     "success": true,
     "data": {
       "id": "a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0",
       "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
       "bank_account_id": "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1",
       "amount_paise": 300000,
       "status": "pending",
       "idempotency_key": "550e8400-e29b-41d4-a716-446655440002",
       "attempt_count": 0,
       "failure_reason": null,
       "processing_started_at": null,
       "created_at": "2026-04-28T10:30:00Z",
       "updated_at": "2026-04-28T10:30:00Z"
     },
     "timestamp": "2026-04-28T10:30:00Z"
   }
   
   Response 200 (Duplicate - same Idempotency-Key):
   {
     "success": true,
     "data": {
       "id": "a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0",
       ... (same as above)
     },
     "timestamp": "2026-04-28T10:30:00Z"
   }
   
   Response 400 (Bad Request):
   {
     "success": false,
     "error": "Idempotency-Key header is required",
     "code": "missing_field",
     "timestamp": "2026-04-28T10:30:00Z"
   }
   
   Response 404 (Merchant or Bank Account not found):
   {
     "success": false,
     "error": "Merchant not found",
     "code": "not_found",
     "timestamp": "2026-04-28T10:30:00Z"
   }
   
   Response 422 (Insufficient balance):
   {
     "success": false,
     "error": "Insufficient balance. Available: 100000 paise, Requested: 300000 paise",
     "code": "insufficient_balance",
     "timestamp": "2026-04-28T10:30:00Z"
   }


5. GET /payouts/{payout_id}/
   -------
   Retrieve details for a specific payout.
   
   Parameters:
     - payout_id (path): UUID of the payout
   
   Response 200:
   {
     "success": true,
     "data": {
       "id": "a0a0a0a0-a0a0-a0a0-a0a0-a0a0a0a0a0a0",
       "merchant_id": "550e8400-e29b-41d4-a716-446655440000",
       "bank_account_id": "b1b1b1b1-b1b1-b1b1-b1b1-b1b1b1b1b1b1",
       "amount_paise": 300000,
       "status": "processing",
       "idempotency_key": "550e8400-e29b-41d4-a716-446655440002",
       "attempt_count": 1,
       "failure_reason": null,
       "processing_started_at": "2026-04-28T10:30:00Z",
       "created_at": "2026-04-28T10:30:00Z",
       "updated_at": "2026-04-28T10:32:00Z"
     },
     "timestamp": "2026-04-28T10:32:00Z"
   }
   
   Response 404:
   {
     "success": false,
     "error": "Payout not found",
     "code": "not_found",
     "timestamp": "2026-04-28T10:32:00Z"
   }


====================================================================
ERROR CODES
====================================================================

- missing_field: Required field is missing
- invalid_type: Invalid data type
- invalid_uuid: Invalid UUID format
- not_found: Resource not found
- insufficient_balance: Merchant has insufficient available balance
- invalid_bank_account: Bank account does not belong to merchant or is inactive
- duplicate_request: Request is duplicate or already processed
- invalid_transition: Invalid state transition


====================================================================
IDEMPOTENCY
====================================================================

All requests to POST /payouts/ MUST include an "Idempotency-Key" header
with a unique UUID. This ensures that:

1. Retrying the same request returns the same payout ID
2. No duplicate payouts are created
3. The response status code may differ (201 on first request, 200 on retry)

Example:
  POST /payouts/
  Headers:
    - Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  Body:
    {
      "merchant_id": "...",
      "amount_paise": 300000,
      "bank_account_id": "..."
    }
  
  First request → 201 Created
  Second request (same Idempotency-Key) → 200 OK (same payout)
  Third request (same Idempotency-Key) → 200 OK (same payout)


====================================================================
BALANCE MODEL
====================================================================

Available Balance = Credits - Debits - Held

where:
  - Credits: Sum of all CREDIT transactions
  - Debits: Sum of all DEBIT transactions
  - Held: Sum of all PENDING or PROCESSING payouts

Held funds are released when:
  - Payout COMPLETES: DEBIT is recorded, funds are settled
  - Payout FAILS: CREDIT is recorded (refund), funds are returned

Example:
  Credits: 10000 paise
  Debits: 2000 paise
  Held (pending payout): 5000 paise
  
  Available Balance = 10000 - 2000 - 5000 = 3000 paise


====================================================================
PAYOUT LIFECYCLE
====================================================================

pending → processing → completed (with DEBIT transaction recorded)
                    ↓
                    failed (with CREDIT refund transaction recorded)

- PENDING: Payout created, waiting for background processing
- PROCESSING: Background worker is processing the payout
- COMPLETED: Payout has been successfully settled; DEBIT recorded
- FAILED: Payout failed; CREDIT refund recorded; funds returned to merchant

Automatic retry logic:
- Max 3 attempts to process a payout
- Exponential backoff: 2^attempt_count seconds
- After 3 failures, payout moves to FAILED state
"""
