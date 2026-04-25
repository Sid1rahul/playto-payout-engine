import React from "react";
import { formatINR, formatDate } from "../utils";

const STATUS_COLORS = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function TransactionTable({ transactions }) {
  if (!transactions || transactions.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 text-center text-gray-500">
        No transactions yet
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-6 py-3 text-left text-sm font-semibold">Type</th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Amount</th>
            <th className="px-6 py-3 text-left text-sm font-semibold">
              Description
            </th>
            <th className="px-6 py-3 text-left text-sm font-semibold">Date</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((txn) => (
            <tr key={txn.id} className="border-t hover:bg-gray-50">
              <td className="px-6 py-4">
                <span
                  className={`inline-block px-3 py-1 rounded text-sm font-semibold ${
                    txn.txn_type === "credit"
                      ? "bg-green-100 text-green-800"
                      : "bg-red-100 text-red-800"
                  }`}
                >
                  {txn.txn_type.toUpperCase()}
                </span>
              </td>
              <td className="px-6 py-4">
                <span
                  className={`font-semibold ${
                    txn.txn_type === "credit"
                      ? "text-green-600"
                      : "text-red-600"
                  }`}
                >
                  {txn.txn_type === "credit" ? "+" : "-"}
                  {formatINR(txn.amount_paise)}
                </span>
              </td>
              <td className="px-6 py-4 text-sm text-gray-600">
                {txn.description}
              </td>
              <td className="px-6 py-4 text-sm text-gray-600">
                {formatDate(txn.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default TransactionTable;
