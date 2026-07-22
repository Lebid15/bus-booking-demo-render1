import fs from "node:fs";

const files = {
  layout: fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  shell: fs.readFileSync(new URL("../components/app-shell.tsx", import.meta.url), "utf8"),
  seats: fs.readFileSync(new URL("../components/seat-hold-client.tsx", import.meta.url), "utf8"),
  css: fs.readFileSync(new URL("../app/globals.css", import.meta.url), "utf8"),
};
const checks = [
  ["RTL Arabic root", files.layout.includes('lang="ar" dir="rtl"')],
  ["Skip link", files.shell.includes("skip-link") && files.shell.includes("main-content")],
  ["Keyboard seat navigation", files.seats.includes("ArrowDown") && files.seats.includes("data-seat-index")],
  ["Booking draft persistence", files.seats.includes("sessionStorage") && files.seats.includes("booking-draft")],
  ["Policy summaries before confirmation", files.seats.includes("policy-summary-list") && files.seats.includes("قراءة النص الكامل")],
  ["Reduced motion", files.css.includes("prefers-reduced-motion")],
  ["44px touch targets", files.css.includes("min-height: 44px")],
];
for (const [name, ok] of checks) console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
if (checks.some(([, ok]) => !ok)) process.exit(1);
console.log(`${checks.length}/${checks.length} UX contract checks passed`);
