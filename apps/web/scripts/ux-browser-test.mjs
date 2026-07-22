import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const require = createRequire(import.meta.url);
const axePath = require.resolve("axe-core/axe.min.js");
const axeSource = fs.readFileSync(axePath, "utf8");
const tripId = process.env.TRIP_ID;
const base = process.env.WEB_BASE_URL ?? "http://127.0.0.1:3000";
const evidenceDir = process.env.EVIDENCE_DIR ?? ".";
if (!tripId) throw new Error("TRIP_ID is required");
fs.mkdirSync(evidenceDir, { recursive: true });

const results = [];
function check(name, ok, details = {}) {
  results.push({ name, ok: Boolean(ok), details });
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
}

const browser = await puppeteer.launch({
  executablePath: await chromium.executablePath(),
  args: chromium.args,
  headless: chromium.headless,
  defaultViewport: { width: 360, height: 800, deviceScaleFactor: 1 },
});
let page;
try {
  page = await browser.newPage();
  const client = await page.createCDPSession();
  await client.send("Network.enable");
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 180,
    downloadThroughput: 1_600_000 / 8,
    uploadThroughput: 750_000 / 8,
    connectionType: "cellular3g",
  });
  let encodedBytes = 0;
  client.on("Network.loadingFinished", (event) => { encodedBytes += event.encodedDataLength || 0; });
  const responses = [];
  page.on("response", (response) => responses.push({ url: response.url(), status: response.status() }));
  page.on("console", (msg) => console.log(`browser:${msg.type()}: ${msg.text()}`));

  await page.goto(`${base}/trips/${tripId}/seats?passengers=1`, { waitUntil: "networkidle0", timeout: 120000 });
  const layout = await page.evaluate(() => ({
    dir: document.documentElement.dir,
    lang: document.documentElement.lang,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    skipLink: Boolean(document.querySelector(".skip-link")),
  }));
  check("Arabic RTL root", layout.dir === "rtl" && layout.lang === "ar", layout);
  check("No horizontal overflow at 360px", layout.overflow <= 1, layout);
  check("Skip link exists", layout.skipLink, layout);

  await page.addScriptTag({ content: axeSource });
  const axeBefore = await page.evaluate(async () => await globalThis.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }));
  const seriousBefore = axeBefore.violations.filter((item) => ["serious", "critical"].includes(item.impact));
  check("No serious/critical accessibility violations on seat page", seriousBefore.length === 0, { violations: seriousBefore.map((v) => v.id) });

  const seatSelector = '.seat-button[aria-disabled="false"]';
  await page.waitForSelector(seatSelector, { timeout: 30000 });
  await page.focus(seatSelector);
  const beforeIndex = await page.$eval(seatSelector, (el) => el.getAttribute("data-seat-index"));
  await page.keyboard.press("ArrowLeft");
  await new Promise((resolve) => setTimeout(resolve, 200));
  const afterIndex = await page.evaluate(() => document.activeElement?.getAttribute("data-seat-index"));
  check("Arrow-key seat navigation moves focus", beforeIndex !== afterIndex, { beforeIndex, afterIndex });

  await page.$eval(seatSelector, (el) => el.click());
  await page.type('.passenger-card input[type="text"]', "محمد أحمد");
  const selectedId = await page.$eval('.seat-button[aria-pressed="true"]', (el) => el.getAttribute("data-seat-index"));
  await page.reload({ waitUntil: "networkidle0", timeout: 120000 });
  await page.waitForSelector('.passenger-card input[type="text"]');
  const restored = await page.$eval('.passenger-card input[type="text"]', (el) => el.value);
  const restoredSeat = await page.$eval('.seat-button[aria-pressed="true"]', (el) => el.getAttribute("data-seat-index"));
  check("Booking draft survives reload", restored === "محمد أحمد" && restoredSeat === selectedId, { restored, selectedId, restoredSeat });

  await page.evaluate(() => {
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent?.includes("حفظ المقاعد مؤقتًا"));
    button?.click();
  });
  await page.waitForSelector(".hold-success", { timeout: 60000 });
  const policyCount = await page.$$eval(".policy-summary-card", (nodes) => nodes.length);
  const fullLinks = await page.$$eval(".policy-summary-card a", (nodes) => nodes.map((node) => node.getAttribute("href")));
  check("Versioned policy summaries appear before confirmation", policyCount >= 3 && fullLinks.every(Boolean), { policyCount, fullLinks });

  await page.type('.hold-success input[type="text"]', "محمد أحمد");
  await page.type('.hold-success input[type="tel"]', "+963944123456");
  await page.type('.hold-success input[type="email"]', "mobile-test@example.com");
  await page.click('.policy-check input[type="checkbox"]');
  await page.evaluate(() => {
    const button = [...document.querySelectorAll("button")].find((item) => item.textContent?.includes("إنشاء الحجز النهائي"));
    button?.click();
  });
  await page.waitForSelector(".booking-success", { timeout: 60000 });
  const success = await page.evaluate(() => ({
    text: document.querySelector(".booking-success")?.textContent ?? "",
    pnr: document.querySelector(".booking-success bdi")?.textContent ?? "",
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    ticketLinks: document.querySelectorAll(".ticket-card a").length,
  }));
  check("Mobile browser completes booking and receives PNR", success.pnr.length >= 6, success);
  check("Booking success keeps mobile layout within viewport", success.overflow <= 1, success);
  check("Ticket action is available", success.ticketLinks >= 1, success);

  await page.addScriptTag({ content: axeSource });
  const axeAfter = await page.evaluate(async () => await globalThis.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }));
  const seriousAfter = axeAfter.violations.filter((item) => ["serious", "critical"].includes(item.impact));
  check("No serious/critical accessibility violations on success page", seriousAfter.length === 0, { violations: seriousAfter.map((v) => v.id) });

  const touchTargets = await page.evaluate(() => [...document.querySelectorAll("button, a.primary-link")].filter((el) => {
    const style = getComputedStyle(el); return style.visibility !== "hidden" && style.display !== "none";
  }).map((el) => { const rect = el.getBoundingClientRect(); return { text: el.textContent?.trim(), width: rect.width, height: rect.height }; }));
  const smallTargets = touchTargets.filter((item) => item.width > 0 && item.height > 0 && (item.width < 40 || item.height < 40));
  check("Visible primary touch targets are at least 40px", smallTargets.length === 0, { smallTargets });
  check("Complete mobile journey transfer remains below 3 MB", encodedBytes <= 3_000_000, { encodedBytes });
  await page.screenshot({ path: path.join(evidenceDir, "mobile-booking-success.png"), fullPage: true });
} catch (error) {
  results.push({ name: "browser-test-execution", ok: false, details: { error: String(error) } });
  console.error(error);
} finally {
  fs.writeFileSync(path.join(evidenceDir, "ux-browser-results.json"), JSON.stringify(results, null, 2));
  await browser.close();
}
if (results.some((item) => !item.ok)) process.exit(1);
