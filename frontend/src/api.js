import axios from "axios";
import { v4 as uuidv4 } from "uuid";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

export const getBalance = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/balance/`);

export const getTransactions = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/transactions/`);

export const getPayouts = (merchantId) =>
  api.get(`/api/v1/merchants/${merchantId}/payouts/`);

export const getPayout = (payoutId) =>
  api.get(`/api/v1/payouts/${payoutId}/`);

export const createPayout = (merchantId, amountPaise, bankAccountId) =>
  api.post(
    "/api/v1/payouts/",
    {
      merchant_id: merchantId,
      amount_paise: amountPaise,
      bank_account_id: bankAccountId,
    },
    {
      headers: {
        "Idempotency-Key": uuidv4(),
      },
    }
  );

export default api;
