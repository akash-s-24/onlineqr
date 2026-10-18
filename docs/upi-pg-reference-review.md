# CIT India UPI-PG reference review

Reviewed: 2026-10-18

Repository: https://github.com/Centre-for-Information-Technology-India/upi-pg

## Summary

This repository is a Next.js/Firebase application for creating shareable UPI payment links and QR codes. It is useful as a UX and payment-link reference, but it is not a complete bank-confirming payment gateway. Its payment page constructs a `upi://pay` URI, renders a QR image, and opens the URI from a button. It does not show a bank/acquirer webhook, server-side transaction-status verification, card/net-banking processing, or proof that a payment was completed.

Sources: [README](https://github.com/Centre-for-Information-Technology-India/upi-pg), [payment page source](https://raw.githubusercontent.com/Centre-for-Information-Technology-India/upi-pg/main/src/app/pay/%5Bid%5D/PayPageClient.tsx), [payment types](https://raw.githubusercontent.com/Centre-for-Information-Technology-India/upi-pg/main/src/lib/types.ts).

## Useful features to adapt to EventMate

1. **Payment-link model** — Create a unique, expiring payment attempt for each registration instead of showing one reusable event QR. Bind it to registration ID, event ID, amount, and college VPA.
2. **Fixed-amount UPI URI** — Generate a URI with `pa`, `pn`, `am`, `cu`, and a registration-specific `tn`. Keep the amount server-controlled and use paise internally.
3. **Dedicated payment page** — Show the amount, college/payee, event, registration reference, expiry, QR, and an explicit “Pay with any UPI app” action.
4. **Mobile sharing and copy actions** — Copy link, native share, and QR fallback improve mobile completion and support participants who register on one device and pay on another.
5. **Expiry handling** — Expire unused links and refuse to present them as valid after expiry. Expiry must be enforced server-side, not only by the browser.
6. **Payment attempt history** — Keep attempts separate from registrations so retries and abandoned attempts are auditable without creating duplicate registrations.
7. **Dashboard concepts** — Re-share active links, display pending/completed/failed states, and retain payment history. EventMate should implement these in its existing admin and participant dashboards.
8. **Localization and accessibility patterns** — The repository supports multiple Indian languages and uses reusable UI components; the ideas can improve participant-facing copy, but a Flask/HTML implementation is simpler than porting its React stack.

The repository is MIT licensed, which is more permissive than the commercial licensing described by YouPI-PG, but attribution and the exact license obligations should still be preserved when copying code. [MIT license](https://github.com/Centre-for-Information-Technology-India/upi-pg/blob/main/LICENSE)

## What it does not solve

- A UPI intent or QR code does not report authoritative payment success back to the website.
- The repository does not provide card, credit-card, net-banking, or bank-transfer processing.
- It does not prove that the participant paid the exact amount or that the payment went to the intended college account.
- Its `PaymentRequest` type includes `pending`, `completed`, and `failed`, but the visible payment page only constructs and launches the UPI payment URI; a production system still needs bank/acquirer status verification or a trusted payment provider webhook.
- It uses a remote QR image service (`api.qrserver.com`) in the payment page. EventMate should generate QR images locally to avoid a third-party dependency and data leakage.
- The public Firestore rules permit anonymous creation of public payment-request documents and allow anyone to read a single public request. That is acceptable for a generic shareable-link generator only with strict document validation and rate limiting; it is not sufficient as the authoritative payment ledger for participant registrations. [Firestore rules](https://github.com/Centre-for-Information-Technology-India/upi-pg/blob/main/firestore.rules)
- The public payment page can construct a dynamic UPI link using a temporary amount when the request has no fixed amount. EventMate should not copy this flexible-amount behavior for event fees; all paid registrations must use a server-fixed amount.

## Recommended use in EventMate

Adopt the repository's concepts, not its Firebase/Next.js stack:

1. Add a server-side `payment_attempts` record with a random public token, registration ID, amount paise, VPA, status, expiry, and audit timestamps.
2. Generate the UPI URI locally and render a local QR code.
3. Display a mobile payment page with QR, deep-link button, copy/share, event details, and expiry.
4. Keep the registration in `payment_pending` after the participant leaves for the UPI app.
5. Confirm success only through a bank/acquirer API or signed provider webhook. Never change status based on the browser returning from the app.
6. Add idempotent receipt generation, email/WhatsApp delivery retries, participant receipt lookup, admin reconciliation, and manual review for unmatched payments.

This would improve EventMate's current QR-plus-manual-UTR flow while preserving its Flask database and existing pay-on-spot option.

## Comparison with YouPI-PG

The CIT repository is smaller and easier to understand: it focuses on QR/link presentation, expiry, sharing, and Firebase-backed link history. YouPI-PG attempts a much larger self-hosted system with bank observers, queues, automatic attribution, and webhooks, but its open issues identify significant security and correctness problems. For EventMate, the best design is to reuse CIT's payment-page UX and link lifecycle, then connect it to a regulated/acquirer-supported verification mechanism rather than trusting either repository as a complete autonomous payment processor.

## Conclusion

Useful for implementation: **yes, as a reference for UPI payment links, fixed-amount QR UX, expiry, sharing, and payment-attempt history**.

Suitable as the complete secure payment gateway: **no**.

No application code was changed during this review.
