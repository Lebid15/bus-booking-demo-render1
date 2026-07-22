# G18 / E19 Traceability — UX, RTL and Accessibility

| Acceptance criterion | Implementation | Automated / practical evidence | Result |
|---|---|---|---|
| `E19-AC01` A medium phone on weak connectivity can complete booking without an app or heavy transfer | responsive public booking, server timeouts, compact page payload, browser E2E under emulated slow 3G | Chromium 360×800 completed booking and received PNR `BKY6PPNU`; encoded journey transfer `180,540` bytes (<3 MB) | PASS practically |
| `E19-AC02` Arabic screens have correct RTL and understandable numbers, currency and dates | Arabic `lang/dir`, shared locale formatters, `<bdi>` for variable values, mobile overflow guards | Browser result: RTL root and 0 horizontal overflow; production build includes 40 routes | PASS |
| `E19-AC03` Core functions are available by keyboard without a mouse | skip link, visible focus, arrow/Home/End seat navigation, focusable unavailable seats with descriptive state | Browser result confirms arrow-key focus movement; `ux-contract-test.mjs` | PASS |
| `E19-AC04` Loading/empty/error states provide action and booking input is not lost without reason | route loading/error boundaries, actionable empty states, `sessionStorage` booking draft and idempotency state | Browser reload restored passenger name and selected seat; static UX contract 7/7 | PASS |
| `E19-AC05` Important policy summaries appear before confirmation with full-text links | versioned public policy summaries derived from trip snapshot, summary cards and office-scoped policy links | `test_e19_ac05_public_trip_exposes_versioned_policy_summaries_without_full_legal_text`; browser found 3 versioned summaries and links | PASS |

## Practical browser evidence

- Headless Chromium with a 360×800 viewport and slow-3G network emulation.
- No serious or critical Axe violations on the seat-selection or booking-success state.
- No horizontal overflow before or after confirmation.
- Booking draft survived reload.
- Full booking completed and returned PNR `BKY6PPNU` and a ticket action.
- All visible primary touch targets were at least 40px; CSS target baseline is 44px.
- Screenshot: `docs/evidence/G18-final-closure/mobile-booking-success.png`.
- Machine-readable results: `docs/evidence/G18-final-closure/ux-browser-results.json`.
