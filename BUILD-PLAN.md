# Gardenia Trade Assistant — Product & Technical Plan

## Product direction

An authorized buyer-side assistant for Gardenia Marketplace that turns a natural-language purchase need into a transparent, comparable sourcing brief. Gardenia's public site describes a marketplace for buyers and farmers/sellers; its public visitor experience currently starts with account onboarding. This prototype therefore demonstrates a buyer workspace and does not imply that any sample listing, supplier, price, match score, stock level, or delivery estimate is live.

## Prototype delivered

Open `index.html` in a modern browser. No build step or external dependency is required.

- Separate entry points: `buyer.html` and `farmer.html`; each opens only its own workspace and navigation.
- Search sample agricultural offers by product, category, supplier, and location.
- Sort by relevance, sample price, or sample delivery lead time.
- Add offers to a sourcing list at the listed illustrative minimum quantity; adjust in MOQ-sized increments.
- Review combined sample quantity, supplier count, and indicative subtotal.
- Draft (but do not send) a multi-supplier RFQ summary.
- Use the assistant panel to build a sourcing brief one question at a time; it does not use the sample cards as live recommendations.
- Persist the demo sourcing list in local browser storage.
- Switch between buyer and farmer workspaces using the demo role selector.
- **Buyer tools:** similar-interest sourcing suggestions, sample smart-reorder reminders, a user-input demand scenario, and a quality/freshness due-diligence checklist.
- **Farmer tools:** listing copy draft, planting/harvest date planner, comparison against a farmer-entered price reference, post-harvest handling checklist, and farm cash-flow arithmetic.
- Responsive layout for desktop and mobile.

All new assistant tools run locally in the browser. Buyer interest and reorder history are fictional examples; the demand range is a simple arithmetic scenario; quality/freshness is not actually verified. Farmer tools do not inspect Gardenia farm records, query live prices/weather, diagnose spoilage, guarantee harvest dates, or assess credit eligibility.

## WhatsApp assistant implementation

`whatsapp_assistant.py` is a standard-library Python webhook for Meta's WhatsApp Business Cloud API. It verifies webhook setup, checks each POST against Meta's `X-Hub-Signature-256`, handles text and interactive replies, and sends user-initiated replies through the configured Graph API endpoint. The phrase-based localization supports English, Nigerian Pidgin, Hausa, Yoruba, Igbo, and French. `sourcing_agent.py` captures a buyer brief and enforces verified-offer checks and an explicit order confirmation gate when tools are provided, but this project has no live Gardenia adapter. It must not present a live shortlist, order, quote, or human handoff without successful tool results.

The service stores a keyed HMAC of the WhatsApp ID plus language, role, opt-out status, and temporary parsed conversation state in SQLite. The state can include a delivery address and expires after 24 hours; raw IDs and full message text are not stored. WhatsApp audio is not transcribed. `STOP`/`UNSUBSCRIBE` pauses replies, `START` resumes them, and `PREFERENCE_HASH_KEY` should be stable for persistent preferences. Meta tokens and signing secrets are environment-only. See `WHATSAPP-SETUP.md`.

## MVP buyer journey

1. Sign in through Gardenia's existing identity and account-type model; authorize buyer/corporate/cooperative permissions.
2. Describe the product, grade/quality, quantity and unit, destination, target date, and optional budget.
3. Resolve ambiguous requirements with follow-up questions before ranking offers.
4. Retrieve eligible, current marketplace listings through an authorized API; explain match factors and show comparable landed-cost components only when sourced.
5. Let a buyer select offers and opt into aggregation. Show source, freshness, MOQ, seller, quantity allocation, delivery terms, fees, and exclusions.
6. Create an RFQ draft. The buyer reviews and explicitly confirms before it is submitted to sellers.
7. Track seller responses and buyer-approved next steps in Gardenia's existing RFQ/order workflow.

### Buyer assistant tools

- **Sourcing agent:** rank relevant Gardenia listings from the buyer's authorized past purchases, saved products, current brief, and consented similar-interest signals. Explain which signals drove each suggestion; never expose another buyer's identity or private history.
- **Smart reorder:** detect buyer-approved repeat patterns from orders, surface a reminder and prior order context, then refresh live price, listing status, MOQ, and quantity before offering a new RFQ/cart action. Reminder is not automatic purchase.
- **Demand forecaster:** forecast SKU/category demand from permissioned order history and seasonality, show horizon, range, assumptions, confidence/data sufficiency, and allow scenario edits. Do not claim certainty.
- **Quality/freshness verifier:** distinguish listing evidence, seller-provided information, certificates, sensor/chain-of-custody data, and actual inspection. Report evidence provenance, dates, missing checks, and uncertainty; automated screening must not claim food-safety clearance.

### Farmer assistant tools

- **Listing copilot:** draft structured listing fields from farmer-supplied facts; require farmer review before saving/publishing and do not invent certifications or attributes.
- **Harvest and planting planner:** create an editable crop calendar from crop/variety, location, planting date, local agronomy/weather sources, and farmer inputs; label estimates and flag missing context.
- **Dynamic pricing advisor:** compare current listings and recent transactions where authorized, normalized for grade, unit, location, time, volume, and fees; show sources and ranges, not a guaranteed selling price.
- **Post-harvest and spoilage assistant:** use crop-specific handling guidance and farmer-entered observations to prioritize checks and escalation; do not replace a qualified inspection or food-safety procedure.
- **Farm finance assistant:** summarize farmer-authorized costs, expected revenue, and cash timing; explain assumptions and refer regulated lending/credit decisions to approved providers.

## Proposed architecture

- **Web client:** distinct, Gardenia-authenticated buyer and farmer workspaces with role-authorized tools; buyer search, offer comparison, sourcing basket, assistant conversation, and RFQ review; farmer listing, crop-planning, pricing, post-harvest, and finance workflows.
- **WhatsApp channel:** verified Meta webhook, constrained text/interactive message parser, language preference, translated intent guides, and outbound reply client. Apply opt-out checks, protect webhook secrets, and keep channel permissions aligned with the user's Gardenia identity before enabling account-specific data or actions.
- **Application API:** session and role authorization, request validation, rate limits, audit events, and a stable interface between the client and Gardenia services.
- **Marketplace adapter:** read listings, seller and verification details, inventory/availability, delivery regions, and current price/MOQ from documented Gardenia APIs. Do not scrape authenticated pages or automate account actions.
- **Sourcing service:** parse requirements into a typed brief; search and normalize eligible offers; calculate explainable ranking; build allocations subject to MOQ, stock, geography, quality, and delivery constraints.
- **Buyer intelligence service:** permission-scoped features for recommendations, repeat-order reminders, and demand scenarios; isolate user histories and record recommendation provenance.
- **Farmer workflow services:** draft-only listing assistance, locally grounded crop-calendar data, normalized pricing references, crop-specific post-harvest sources, and farmer-consented financial summaries.
- **Assistant orchestration:** model may extract/filter requirements and explain results, but deterministic services own eligibility, price arithmetic, totals, and state transitions. Treat listing and seller text as untrusted data; do not follow instructions contained in listings.
- **RFQ integration:** create a draft in Gardenia's existing workflow and submit only after an authenticated buyer confirmation. Use idempotency keys and return the actual Gardenia RFQ identifier/status.
- **Data and observability:** minimize stored conversation data; retain necessary RFQ/audit state under Gardenia's retention policy; measure listing freshness, search quality, RFQ conversion, and integration errors without logging secrets.

### Suggested typed contracts

```text
SourcingBrief {
  items: [{ productId?, query, grade?, quantity, unit, qualitySpecs? }],
  destination: { country, region?, city? },
  deliveryWindow?: { earliest?, latest? },
  budget?: { amount, currency, basis? },
  aggregationConsent: boolean
}

Offer {
  listingId, sellerId, product, grade, availableQuantity, unit,
  minimumOrder, currency, unitPrice, priceUpdatedAt,
  origin, deliveryRegions[], leadTime?, qualityEvidence[], status
}

RfqDraft {
  brief, allocations: [{ listingId, sellerId, quantity, unit }],
  estimate: { subtotal, currency, exclusions[] },
  expiresAt?, idempotencyKey
}
```

These are proposed integration contracts, not existing Gardenia API schemas.

## Matching and aggregation

1. Apply hard constraints first: active/eligible listing, product identity, quantity/available stock, minimum order, grade/required certifications, delivery region, and target date.
2. Rank eligible listings with disclosed factors such as product/grade fit, total estimated cost (only if complete), freshness, delivery fit, and seller evidence. Avoid presenting a score as certification or guarantee.
3. Aggregate only compatible demand and offers. Enforce each seller's MOQ, available stock, unit conversions, delivery constraints, and buyer opt-in. Keep allocation and seller-level totals visible.
4. If no match satisfies hard requirements, report which constraints failed and offer alternatives only with the buyer's consent.
5. Recheck price and stock immediately before RFQ submission; surface changes and require reconfirmation.

## Security, safety, and trust requirements

- Integrate only through Gardenia-approved APIs and OAuth/session mechanisms; never collect or embed user credentials in the assistant.
- Enforce buyer/seller authorization server-side and validate every listing, quantity, currency, unit conversion, and destination.
- Treat assistant output as advisory. Never place orders, commit funds, message suppliers, or submit an RFQ without explicit buyer confirmation.
- Display provenance, last-updated time, exclusions, seller verification state, and uncertainty; do not fabricate claims or silently fall back to stale prices.
- Use CSRF protections for state-changing requests, output escaping, content-security policy, rate limiting, and auditable idempotent RFQ submission.
- Minimize personal/business data in model prompts; use approved processors and retention controls.

## Delivery phases

1. **Discovery:** obtain Gardenia product taxonomy, buyer/RFQ flow, supported markets/currencies, approved API documentation, authentication and sandbox access, and legal/compliance constraints.
2. **Read-only MVP:** authenticated product search, typed brief, transparent ranking, live offer comparison, and saved sourcing lists.
3. **RFQ drafts:** MOQ-aware offer allocation, explicit aggregation consent, and buyer-confirmed RFQ creation against a sandbox.
4. **Production hardening:** authorization/security review, accessibility, localization, observability, load/error testing, freshness safeguards, and rollout behind a feature flag.
5. **Farmer tools:** begin with farmer-reviewed listing drafts and transparent calculators; add validated agronomy/price/handling sources only after Gardenia confirms access, geographic coverage, and content ownership.

## Decisions and dependencies before live integration

- Gardenia API endpoints, schemas, rate limits, sandbox, auth scopes, and integration owner.
- Launch market(s), settlement currencies, unit conventions, and approved unit conversions.
- Whether aggregation means one buyer's multi-supplier RFQ, pooled demand across buyers, or both. Cross-buyer pooling needs explicit consent and privacy/contract rules.
- Seller verification, product-grade evidence, pricing/freight/tax ownership, and conflict/dispute handling.
- Existing Gardenia frontend/backend stack and deployment/review requirements.

Until these are confirmed, the browser prototype uses local illustrative data and never makes a marketplace request or transaction. The WhatsApp backend makes a Graph API request only when configured with Meta credentials; its replies remain generic guidance and do not transact with Gardenia.
