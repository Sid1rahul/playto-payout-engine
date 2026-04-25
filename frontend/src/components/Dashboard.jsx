import React, { useEffect, useState } from "react";
import {
  getBalance,
  getTransactions,
  getPayouts,
  getPayout,
} from "../api";
import BalanceCard from "./BalanceCard";
import PayoutForm from "./PayoutForm";
import TransactionTable from "./TransactionTable";
import PayoutHistory from "./PayoutHistory";

export function Dashboard({ merchantId, bankAccounts }) {
  const [balance, setBalance] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState("");

  const fetchData = async () => {
    try {
      setError(null);
      const [balanceRes, transactionsRes, payoutsRes] = await Promise.all([
        getBalance(merchantId),
        getTransactions(merchantId),
        getPayouts(merchantId),
      ]);

      setBalance(balanceRes.data);
      setTransactions(transactionsRes.data);
      setPayouts(payoutsRes.data);
    } catch (err) {
      setError(err.response?.data?.error || "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [merchantId]);

  const handlePayoutSuccess = (payoutData) => {
    setSuccessMessage(`Payout created successfully: ${payoutData.id}`);
    setTimeout(() => setSuccessMessage(""), 5000);
    fetchData();
  };

  const handlePayoutError = (errorMsg) => {
    setError(errorMsg);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-600 text-lg">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">Playto Payout Engine</h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded mb-6">
            {error}
          </div>
        )}

        {successMessage && (
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded mb-6">
            {successMessage}
          </div>
        )}

        {balance && (
          <BalanceCard
            availableBalance={balance.available_balance_paise}
            heldBalance={balance.held_balance_paise}
          />
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <div className="lg:col-span-1">
            <PayoutForm
              merchantId={merchantId}
              bankAccounts={bankAccounts}
              onSuccess={handlePayoutSuccess}
              onError={handlePayoutError}
            />
          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-2xl font-bold mb-4">Recent Transactions</h2>
              <TransactionTable transactions={transactions} />
            </div>
          </div>
        </div>

        <div>
          <h2 className="text-2xl font-bold mb-4">Payout History</h2>
          <PayoutHistory payouts={payouts} onRefresh={fetchData} />
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
