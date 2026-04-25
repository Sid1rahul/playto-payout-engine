import React from "react";
import { formatINR } from "../utils";

export function BalanceCard({ availableBalance, heldBalance }) {
  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 className="text-2xl font-bold mb-4">Wallet Balance</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-green-50 p-4 rounded">
          <p className="text-gray-600 text-sm mb-1">Available Balance</p>
          <p className="text-3xl font-bold text-green-600">
            {formatINR(availableBalance)}
          </p>
        </div>
        <div className="bg-yellow-50 p-4 rounded">
          <p className="text-gray-600 text-sm mb-1">Held Balance</p>
          <p className="text-3xl font-bold text-yellow-600">
            {formatINR(heldBalance)}
          </p>
        </div>
      </div>
    </div>
  );
}

export default BalanceCard;
