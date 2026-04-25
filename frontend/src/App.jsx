import React, { useEffect, useState } from "react";
import Dashboard from "./components/Dashboard";
import { getBalance } from "./api";

function App() {
  // Hardcoded for now - in production, would use auth
  // Using the first seeded merchant ID
  const merchantId = "merchant-1"; // This will be replaced with actual merchant ID from first seed

  // Get bank accounts from the merchant (would be fetched from API in real app)
  const [bankAccounts, setBankAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Try to load merchant data
    // For MVP, we'll assume the frontend knows the merchant ID and bank account IDs
    const initializeMerchant = async () => {
      try {
        // In a real app, this would fetch merchant details
        // For now, we'll just set up with placeholder data
        setBankAccounts([
          {
            id: "bank-account-1",
            account_holder_name: "Acme Design Studio",
            account_number: "1234567890",
          },
        ]);
        setLoading(false);
      } catch (error) {
        console.error("Failed to initialize merchant", error);
        setLoading(false);
      }
    };

    initializeMerchant();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-600 text-lg">Initializing...</div>
      </div>
    );
  }

  return <Dashboard merchantId={merchantId} bankAccounts={bankAccounts} />;
}

export default App;
