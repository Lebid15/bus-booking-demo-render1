const arabicLocale = "ar-SY-u-nu-latn";

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(arabicLocale, { maximumFractionDigits: 2 }).format(value);
}

export function formatMoney(amount: string | number, currency: string): string {
  const numeric = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(numeric)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(arabicLocale, {
      style: "currency",
      currency,
      currencyDisplay: "code",
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(numeric);
  } catch {
    return `${formatNumber(numeric)} ${currency}`;
  }
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(arabicLocale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Damascus",
  }).format(new Date(value));
}

export function formatTime(value: string): string {
  return new Intl.DateTimeFormat(arabicLocale, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Damascus",
  }).format(new Date(value));
}
