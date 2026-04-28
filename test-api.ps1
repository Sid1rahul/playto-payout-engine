# API Testing Script for Playto Payout Engine (PowerShell)
# This script demonstrates API usage with Invoke-RestMethod

$API_URL = "http://localhost:8000/api/v1"
$Headers = @{
    "Content-Type" = "application/json"
}

Write-Host "======================================" -ForegroundColor Blue
Write-Host "Playto Payout Engine - API Test" -ForegroundColor Blue
Write-Host "======================================`n" -ForegroundColor Blue

# Define test variables
$MERCHANT_ID = "550e8400-e29b-41d4-a716-446655440000"  # Replace with actual ID
$BANK_ACCOUNT_ID = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"  # Replace with actual ID
$IDEMPOTENCY_KEY = [guid]::NewGuid().ToString()

Write-Host "Test Configuration:" -ForegroundColor Blue
Write-Host "API_URL: $API_URL"
Write-Host "MERCHANT_ID: $MERCHANT_ID"
Write-Host "BANK_ACCOUNT_ID: $BANK_ACCOUNT_ID"
Write-Host "IDEMPOTENCY_KEY: $IDEMPOTENCY_KEY`n"

# Test 1: Get merchant balance
Write-Host "Test 1: Get Merchant Balance" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/merchants/$MERCHANT_ID/balance/" `
        -Method Get -Headers $Headers
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 2: Get merchant transactions
Write-Host "Test 2: Get Merchant Transactions" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/merchants/$MERCHANT_ID/transactions/?limit=5" `
        -Method Get -Headers $Headers
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 3: Get merchant payouts
Write-Host "Test 3: Get Merchant Payouts" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/merchants/$MERCHANT_ID/payouts/?limit=10" `
        -Method Get -Headers $Headers
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 4: Create a payout (first request)
Write-Host "Test 4: Create a Payout (First Request)" -ForegroundColor Green
$payoutBody = @{
    merchant_id = $MERCHANT_ID
    amount_paise = 100000
    bank_account_id = $BANK_ACCOUNT_ID
} | ConvertTo-Json

$payoutHeaders = $Headers.Clone()
$payoutHeaders["Idempotency-Key"] = $IDEMPOTENCY_KEY

try {
    $response = Invoke-RestMethod -Uri "$API_URL/payouts/" `
        -Method Post -Headers $payoutHeaders -Body $payoutBody
    $response | ConvertTo-Json -Depth 10
    $PAYOUT_ID = $response.data.id
    Write-Host "PAYOUT_ID: $PAYOUT_ID" -ForegroundColor Yellow
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 5: Create the same payout again (idempotency test)
Write-Host "Test 5: Create Same Payout Again (Idempotency Check)" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/payouts/" `
        -Method Post -Headers $payoutHeaders -Body $payoutBody
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 6: Get payout details (if PAYOUT_ID was set)
if ($PAYOUT_ID) {
    Write-Host "Test 6: Get Payout Details" -ForegroundColor Green
    try {
        $response = Invoke-RestMethod -Uri "$API_URL/payouts/$PAYOUT_ID/" `
            -Method Get -Headers $Headers
        $response | ConvertTo-Json -Depth 10
    } catch {
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Test 7: Get payouts filtered by status
Write-Host "Test 7: Get Pending Payouts for Merchant" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/merchants/$MERCHANT_ID/payouts/?status=pending&limit=10" `
        -Method Get -Headers $Headers
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# Test 8: Error case - Missing Idempotency-Key
Write-Host "Test 8: Error Case - Missing Idempotency-Key" -ForegroundColor Green
$errorBody = @{
    merchant_id = $MERCHANT_ID
    amount_paise = 50000
    bank_account_id = $BANK_ACCOUNT_ID
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$API_URL/payouts/" `
        -Method Post -Headers $Headers -Body $errorBody
    $response | ConvertTo-Json -Depth 10
} catch {
    $_.Exception.Response | ConvertTo-Json -Depth 10
}
Write-Host ""

# Test 9: Error case - Invalid merchant
Write-Host "Test 9: Error Case - Invalid Merchant" -ForegroundColor Green
try {
    $response = Invoke-RestMethod -Uri "$API_URL/merchants/00000000-0000-0000-0000-000000000000/balance/" `
        -Method Get -Headers $Headers
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "Error (Expected): Merchant not found" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "======================================" -ForegroundColor Blue
Write-Host "Tests Complete!" -ForegroundColor Blue
Write-Host "======================================" -ForegroundColor Blue
