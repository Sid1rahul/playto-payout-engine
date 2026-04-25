import React, { useState } from "react";
import { createPayout } from "../api";
import { formatINR } from "../utils";

export function PayoutForm({ merchantId, bankAccounts, onSuccess, onError }) {
  const [amount, setAmount] = useState("");
  const [bankAccountId, setBankAccountId] = useState("");
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setValidationError("");

    // Validate amount
    const amountPaise = parseInt(amount) * 100;
    if (!amount || amountPaise <= 0) {
      setValidationError("Amount must be a positive number");
      return;
    }

    if (!bankAccountId) {
      setValidationError("Please select a bank account");
      return;
    }

    setLoading(true);
    try {
      const response = await createPayout(merchantId, amountPaise, bankAccountId);
      onSuccess(response.data);
      setAmount("");
      setBankAccountId("");
    } catch (error) {
      const errorMsg = error.response?.data?.error || "Failed to create payout";
      onError(errorMsg);
      setValidationError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 className="text-2xl font-bold mb-4">Request Payout</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-gray-700 font-semibold mb-2">
            Bank Account
          </label>
          <select
            value={bankAccountId}
            onChange={(e) => setBankAccountId(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={bankAccounts.length === 0}
          >
            <option value="">Select a bank account</option>
            {bankAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_holder_name} - {account.account_number}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-gray-700 font-semibold mb-2">
            Amount (INR)
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Enter amount in rupees"
            className="w-full px-4 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {validationError && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {validationError}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded transition"
        >
          {loading ? "Processing..." : "Request Payout"}
        </button>
      </form>
    </div>
  );
}

export default PayoutForm;
