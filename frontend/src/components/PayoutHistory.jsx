import React, { useEffect, useState } from "react";
import { getPayout } from "../api";
import { formatINR, formatDate } from "../utils";

const STATUS_COLORS = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function PayoutHistory({ payouts, onRefresh }) {
  const [localPayouts, setLocalPayouts] = useState(payouts || []);
  const [pollingActive, setPollingActive] = useState(false);

  useEffect(() => {
    setLocalPayouts(payouts || []);

    // Check if any payout is in a non-terminal state
    const hasActive = payouts?.some(
      (p) => p.status === "pending" || p.status === "processing"
    );

    if (hasActive) {
      setPollingActive(true);
      const interval = setInterval(() => {
        onRefresh?.();
      }, 5000);

      return () => clearInterval(interval);
    } else {
      setPollingActive(false);
    }
  }, [payouts, onRefresh]);

  if (!localPayouts || localPayouts.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 text-center text-gray-500">
        No payouts yet
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <div className="px-6 py-4 border-b flex justify-between items-center">
        <h3 className="text-lg font-semibold">Payout History</h3>
        {pollingActive && (
          <span className="text-sm text-blue-600 flex items-center gap-2">
            <span className="inline-block w-2 h-2 bg-blue-600 rounded-full animate-pulse"></span>
            Live updates
          </span>
        )}
      </div>
      <table className="w-full">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-6 py-3 text-left text-sm font-semibold">
              Payout ID
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Amount</th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Status</th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Date</th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Notes</th>
          </tr>
        </thead>
        <tbody>
          {localPayouts.map((payout) => (
            <tr key={payout.id} className="border-t hover:bg-gray-50">
              <td className="px-6 py-4 text-sm font-mono">
                {payout.id.substring(0, 8)}...
              </td>
              <td className="px-6 py-4 font-semibold">
                {formatINR(payout.amount_paise)}
              </td>
              <td className="px-6 py-4">
                <span
                  className={`inline-block px-3 py-1 rounded text-sm font-semibold ${
                    STATUS_COLORS[payout.status] ||
                    "bg-gray-100 text-gray-800"
                  }`}
                >
                  {payout.status}
                </span>
              </td>
              <td className="px-6 py-4 text-sm text-gray-600">
                {formatDate(payout.created_at)}
              </td>
              <td className="px-6 py-4 text-sm text-gray-600">
                {payout.status === "failed" && payout.failure_reason && (
                  <span className="text-red-600">{payout.failure_reason}</span>
                )}
                {payout.status === "processing" && (
                  <span className="text-blue-600">
                    Attempt {payout.attempt_count || 1}/3
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default PayoutHistory;
