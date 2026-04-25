/**
 * Format paise amount to INR currency string
 * Always convert paise → INR at the display layer only
 */
export const formatINR = (paise) => {
  if (paise === null || paise === undefined) {
    return "₹0.00";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
  }).format(paise / 100);
};

/**
 * Format date to readable string
 */
export const formatDate = (dateString) => {
  return new Date(dateString).toLocaleString("en-IN");
};
