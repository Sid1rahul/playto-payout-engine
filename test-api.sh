#!/bin/bash
# API Testing Script for Playto Payout Engine
# This script demonstrates API usage with curl

API_URL="http://localhost:8000/api/v1"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Playto Payout Engine - API Test${NC}"
echo -e "${BLUE}======================================${NC}\n"

# Step 1: Seed the database (optional, run once)
echo -e "${YELLOW}[Optional] Seed database with test merchants:${NC}"
echo "python manage.py seed"
echo ""

# Step 2: Get a merchant ID from the database
echo -e "${YELLOW}Note: Replace MERCHANT_ID with an actual merchant UUID from the database${NC}"
echo "Run: python manage.py shell"
echo "Then: Merchant.objects.first().id"
echo ""

# Define test variables
MERCHANT_ID="550e8400-e29b-41d4-a716-446655440000"  # Replace with actual ID
BANK_ACCOUNT_ID="a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"  # Replace with actual ID
IDEMPOTENCY_KEY=$(python -c "import uuid; print(uuid.uuid4())")

echo -e "${BLUE}Test Configuration:${NC}"
echo "API_URL: $API_URL"
echo "MERCHANT_ID: $MERCHANT_ID"
echo "BANK_ACCOUNT_ID: $BANK_ACCOUNT_ID"
echo "IDEMPOTENCY_KEY: $IDEMPOTENCY_KEY"
echo ""

# Test 1: Get merchant balance
echo -e "${GREEN}Test 1: Get Merchant Balance${NC}"
curl -s -X GET "$API_URL/merchants/$MERCHANT_ID/balance/" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

# Test 2: Get merchant transactions
echo -e "${GREEN}Test 2: Get Merchant Transactions${NC}"
curl -s -X GET "$API_URL/merchants/$MERCHANT_ID/transactions/?limit=5" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

# Test 3: Get merchant payouts
echo -e "${GREEN}Test 3: Get Merchant Payouts${NC}"
curl -s -X GET "$API_URL/merchants/$MERCHANT_ID/payouts/?limit=10" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

# Test 4: Create a payout (first request)
echo -e "${GREEN}Test 4: Create a Payout (First Request)${NC}"
PAYOUT_RESPONSE=$(curl -s -X POST "$API_URL/payouts/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d "{
    \"merchant_id\": \"$MERCHANT_ID\",
    \"amount_paise\": 100000,
    \"bank_account_id\": \"$BANK_ACCOUNT_ID\"
  }")
echo "$PAYOUT_RESPONSE" | python -m json.tool
PAYOUT_ID=$(echo "$PAYOUT_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['data']['id'])")
echo "PAYOUT_ID: $PAYOUT_ID"
echo ""

# Test 5: Create the same payout again (idempotency test)
echo -e "${GREEN}Test 5: Create Same Payout Again (Idempotency Check)${NC}"
curl -s -X POST "$API_URL/payouts/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d "{
    \"merchant_id\": \"$MERCHANT_ID\",
    \"amount_paise\": 100000,
    \"bank_account_id\": \"$BANK_ACCOUNT_ID\"
  }" | python -m json.tool
echo ""

# Test 6: Get payout details
echo -e "${GREEN}Test 6: Get Payout Details${NC}"
curl -s -X GET "$API_URL/payouts/$PAYOUT_ID/" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

# Test 7: Get payouts filtered by status
echo -e "${GREEN}Test 7: Get Pending Payouts for Merchant${NC}"
curl -s -X GET "$API_URL/merchants/$MERCHANT_ID/payouts/?status=pending&limit=10" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

# Test 8: Error case - Missing Idempotency-Key
echo -e "${GREEN}Test 8: Error Case - Missing Idempotency-Key${NC}"
curl -s -X POST "$API_URL/payouts/" \
  -H "Content-Type: application/json" \
  -d "{
    \"merchant_id\": \"$MERCHANT_ID\",
    \"amount_paise\": 50000,
    \"bank_account_id\": \"$BANK_ACCOUNT_ID\"
  }" | python -m json.tool
echo ""

# Test 9: Error case - Invalid merchant
echo -e "${GREEN}Test 9: Error Case - Invalid Merchant${NC}"
curl -s -X GET "$API_URL/merchants/00000000-0000-0000-0000-000000000000/balance/" \
  -H "Content-Type: application/json" | python -m json.tool
echo ""

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Tests Complete!${NC}"
echo -e "${BLUE}======================================${NC}"
