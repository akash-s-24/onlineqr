# YouPI-PG feasibility review for EventMate

Reviewed: 2026-10-18

## Decision

YouPI-PG can be integrated with EventMate at a technical level, but the current upstream repository should not be deployed unchanged for real participant payments. The safe scope is to use its direct UPI QR/intent experience and retain server-side/manual payment confirmation, or to harden and independently validate the gateway before enabling automatic confirmation.

## What the repository does

The repository describes a self-hosted Node.js 20 monorepo with a payment API, checkout portal, merchant admin panel, SQLite persistence, a browser SDK, a FIFO single-active-payment queue, dynamic UPI QR generation, and observer services. Its advertised flow is:

1. EventMate creates a payment session containing an order/registration ID and exact amount.
2. The checkout UI displays a UPI URI/QR and mobile deep links.
3. The participant pays directly to the configured merchant VPA, so the money settles directly to the receiving account rather than through an aggregator.
4. A bank SMS, Android notification, Gmail alert, or Google Messages observer reports the credit to YouPI-PG.
5. The gateway matches the observed amount/UTR to the session and sends an HMAC-signed webhook to EventMate.
6. EventMate marks the registration paid only after verifying the webhook on the raw request body.

The repository claims zero platform transaction fees, but this is not the same as guaranteed zero cost: the merchant still needs an eligible bank/VPA, hosting, HTTPS, operational monitoring, and potentially WhatsApp, Google, or device infrastructure. NPCI states that merchant UPI acceptance requires an acquiring-bank relationship/onboarding and that the merchant receives the money immediately according to its agreement; the QR itself can carry the merchant UPI ID and amount.

Sources: [YouPI-PG README](https://github.com/gxurav1710/YouPI-PG), [YouPI-PG architecture](https://raw.githubusercontent.com/gxurav1710/YouPI-PG/main/ARCHITECTURE.md), [NPCI UPI FAQ](https://www.npci.org.in/what-we-do/upi/faqs).

## Compatibility with this website

EventMate is a Python/Flask application with MySQL/PostgreSQL support and a SQLite fallback. Its current registration flow already has:

- `Online` and `Cash` payment choices;
- an event-level fee and UPI ID;
- a locally generated QR endpoint;
- a UTR field;
- `pending`, `pay_on_site`, `paid`, and `unpaid` states;
- duplicate registration and duplicate UTR protection;
- an admin payment-verification route.

That makes integration possible without replacing the registration system. The clean boundary is a small payment-adapter layer: EventMate owns participants, events, registration capacity, and final payment state; YouPI-PG owns a payment session and bank observation; a signed webhook or a verified server-side status query updates the EventMate registration.

The existing form is currently not a true online gateway: it generates a QR, asks the participant to type a UTR, and leaves the registration pending until an administrator verifies it. It does not create a gateway session, receive a callback, or automatically prove that the UTR belongs to the correct amount and receiving account.

## Feasibility by capability

| Capability | Feasible? | Assessment |
| --- | --- | --- |
| Display a dynamic UPI QR with event amount | Yes | Straightforward and already partly present in EventMate. |
| Open GPay/PhonePe/Paytm-style UPI intents | Yes, with mobile/browser caveats | Requires a public HTTPS gateway URL and careful fallback to QR. |
| Keep pay-on-spot/cash | Yes | Existing EventMate flow can remain separate. |
| Automatically know that a bank credit arrived | Conditionally | Needs a dependable observer/device or a bank/acquirer API. SMS parsing alone is not authoritative. |
| Automatically associate a credit with the right registration | Not safely with the upstream code | Amount-only matching and late/concurrent payments create attribution risk. |
| Securely notify EventMate | Yes after hardening | HMAC, timestamp freshness, delivery idempotency, replay protection, and allowlisted webhook networking are required. |
| Deploy unchanged in production | No | Open upstream issues document exploitable security and correctness gaps. |

## Important upstream risks found

The repository's own open issues identify the following blockers:

- Payment creation and several checkout/PII endpoints trust client-supplied merchant/customer identifiers and are unauthenticated, allowing unauthorized session creation, slot denial, and PII exposure. [Issue #2](https://github.com/gxurav1710/YouPI-PG/issues/2)
- Attribution can fall back across merchants/accounts; UTR deduplication is incomplete; late payments and repeated UTRs can be credited to the wrong session. [Issue #5](https://github.com/gxurav1710/YouPI-PG/issues/5)
- SMS/Gmail parsers can accept debits, balances, weakly verified senders, or incorrect amounts as credits, and in-memory deduplication is lost on restart. [Issue #6](https://github.com/gxurav1710/YouPI-PG/issues/6)
- Webhook retries are not scheduled; timestamps are not included in the HMAC; SSRF is possible through an unvalidated webhook URL; some terminal states do not emit webhooks. [Issue #7](https://github.com/gxurav1710/YouPI-PG/issues/7)
- The Android observer reportedly permits cleartext traffic, contains duplicate Java/Kotlin sources, and has build/signing hygiene problems. [Issue #11](https://github.com/gxurav1710/YouPI-PG/issues/11)
- Processing expiry, restart recovery, timestamp-format comparisons, and uncaught timer errors can produce false failures, stale sessions, or API crashes. [Issue #12](https://github.com/gxurav1710/YouPI-PG/issues/12)
- The project reports build/typecheck failures, tests that do not exercise shipped code, missing observer coverage, schema drift, and environment/documentation mismatches. [Issue #13](https://github.com/gxurav1710/YouPI-PG/issues/13)

The repository also states that it is distributed under commercial/sovereign licensing, so the exact license terms must be reviewed before copying code into EventMate or redistributing a modified gateway. [Repository license section](https://github.com/gxurav1710/YouPI-PG#license)

## Recommended implementation for EventMate

### Phase 1: safe integration boundary

Implement an adapter around EventMate's existing registration flow:

- create an internal payment attempt before showing the QR;
- use integer paise for all amounts and bind the attempt to registration ID, event ID, amount, VPA, and expiry;
- show YouPI-PG checkout/QR or a compatible local QR;
- accept browser success only as a UI hint, never as proof;
- receive and verify signed server-to-server notifications;
- require exact amount, exact receiving VPA/account, unique UTR, freshness, and idempotency before marking paid;
- keep cash/pay-on-spot unchanged;
- retain a manual admin review path for delayed, partial, duplicate, or unmatched credits.

### Phase 2: hardening before automatic confirmation

Before production use, the gateway would need a security patch set covering authentication/authorization, tenant/account scoping, PII access, observer sender validation, persistent UTR uniqueness, late-payment handling, webhook retries and replay protection, SSRF blocking, TLS-only observer traffic, restart recovery, consistent timestamps, rate limits, audit logs, and an independent end-to-end test suite.

### Operations and management

This is not a drop-in Python library. It adds a separate Node.js service cluster (the README lists ports 6100, 7000, 6001, 8090, 6002, and 6003), a SQLite database, HTTPS/domain routing, secrets, backups, logs, health checks, and possibly an Android phone carrying the receiving-bank SIM. Someone must handle observer downtime, bank alert format changes, duplicate/late payments, refunds, reconciliation, and participant support.

## Final recommendation

Implementability: **yes, with a controlled adapter**.

Production readiness of the unmodified repository: **no**.

For this event-registration site, the most reliable low-complexity option is either (a) a direct UPI QR/intent plus manual admin verification, or (b) a bank/acquirer-supported merchant API/webhook if automatic confirmation is mandatory. I recommend implementing YouPI-PG only after hardening the gateway boundary and adding a reconciliation/manual-review path; I do not recommend trusting its current SMS/Gmail observation pipeline to approve registrations automatically.

No application implementation was performed during this review.
