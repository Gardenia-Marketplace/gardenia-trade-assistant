# Using and configuring the Gardenia WhatsApp assistant

## What a buyer or farmer does

1. Open WhatsApp and message the Gardenia business number. The user starts the conversation; the prototype does not send marketing or unsolicited messages.
2. Choose a language by sending `LANGUAGE English`, `LANGUAGE Pidgin`, `LANGUAGE Hausa`, `LANGUAGE Yoruba`, `LANGUAGE Igbo`, or `LANGUAGE French`. The assistant also recognizes a limited set of common phrases in those languages and replies in the detected language.
3. Send `HELP` to see the menu. Send `BUYER` or `FARMER` to choose a role.
4. Buyers can send `SOURCE`, `REORDER`, `DEMAND`, or `QUALITY`. For sourcing, send a natural-language request such as `I need 20 kg tomatoes`; the bot asks for missing location, date, and one-off/recurring details. Farmers can send `LISTING`, `PLANNER`, `PRICING`, `POST-HARVEST`, or `FINANCE`.
5. Reply to the assistant's prompt with the product, quantity/unit, quality details, date/location, or financial values relevant to the chosen tool. The assistant provides a checklist or text guidance. Review all advice; do not treat it as a quote, inspection, agronomy recommendation, or financial decision. Audio messages are not transcribed; send the request as text.
6. Change language at any time with `LANGUAGE <name>`. Use `HELP` if the assistant does not understand a phrase.

### Example conversations

**Buyer:** `LANGUAGE Hausa`  
**Buyer:** `I need 20 kg tomatoes`  
**Assistant:** asks where to deliver, then asks for date and one-off/recurring cadence.  
**Buyer:** supplies those details.  
**Assistant:** explains live Gardenia listing search is not connected and does not invent farms, prices, availability, or delivery information.

**Farmer:** `LANGUAGE Yoruba`  
**Farmer:** `LISTING`  
**Assistant:** asks for crop, quantity/unit, verified quality facts, collection location, and asking price, then drafts listing text for review. It does not publish the listing.

## WhatsApp behavior and current limits

- Supported reply languages are English, Nigerian Pidgin, Hausa, Yoruba, Igbo, and French. Language detection is phrase-based, not a general translation model; use the explicit language command if automatic detection misses.
- English command keywords work in every language. Local-language phrases are also recognized for common intents, but coverage is limited.
- The assistant provides conservative prompts/checklists. No Gardenia API adapter is configured, so it cannot currently access seller records, listings, prices, delivery options, user profiles, orders, weather, images, lab results, or financial accounts.
- It does not submit RFQs, publish listings, create orders or recurring plans, initiate payments, or send proactive messages. The shared sourcing workflow contains confirmation gates for integrations but is not evidence that those operations work here.
- SQLite stores a keyed HMAC of the WhatsApp ID, language/role/opt-out preferences, and an in-progress parsed sourcing request that can include a delivery address and selected offer. The in-progress request expires after 24 hours and is cleared on lookup after expiry; this is not a general database purge/backup retention policy. Raw IDs and full message bodies are not stored. `PREFERENCE_HASH_KEY` must remain stable if preferences should survive restarts. Restrict access to the database, backups, and logs, and apply a documented deletion/retention policy.
- Send `STOP` or `UNSUBSCRIBE` to stop assistant replies; send `START` to resume. This controls this webhook only, not Meta-level business subscriptions. Respect Meta's WhatsApp Business terms and local privacy/marketing law. Do not use this prototype for emergency, food-safety clearance, lending, or regulated advice.

## Meta Cloud API setup

1. Create or select an authorized Meta app and configure WhatsApp Business Platform / Cloud API, a WhatsApp Business Account, and a test or approved business phone number.
2. In Meta's app dashboard, note the app secret, phone-number ID, and a valid access token with the permission needed to send WhatsApp messages. Keep credentials in a secret manager or local `.env`, not in Git.
3. Create a high-entropy webhook verification token and a separate high-entropy `PREFERENCE_HASH_KEY`.
4. Deploy the Python process behind a stable public **HTTPS** endpoint. Set environment variables from `.env.example`. For local development, expose port 8081 using an approved HTTPS tunnel; do not expose the development server directly to the public internet.
5. Set the Meta webhook callback URL to `https://<your-host>/webhook` and enter the exact `WHATSAPP_VERIFY_TOKEN`. Subscribe the WhatsApp product to the `messages` webhook field.
6. Send a message from an allowed tester to the configured test number and confirm a response. Meta signs event bodies using the app secret; this service rejects webhook POSTs without a valid HMAC.
7. For production, use a managed secret store, TLS reverse proxy, process supervisor, backups/retention controls, log monitoring, a webhook rate/size policy, and a documented privacy notice. Set an explicit Graph API version supported by your Meta app.

### Business-initiated messages

This implementation replies to an inbound user message and does not send campaigns. If a future workflow sends a message after the customer-service window or initiates a conversation, first implement the applicable WhatsApp-approved message templates and user opt-in requirements. Do not simply add bulk/proactive messaging.

## Production integration needed

Before making this assistant a Gardenia service, connect it to documented, authorized Gardenia APIs using server-side authentication and role authorization. Keep farmer and buyer data isolated. Obtain user consent before using order histories for suggestions or reorder timing. Recheck listing freshness and seller availability; present quality evidence with provenance; ensure order creation is idempotent against webhook retries; and require explicit confirmation before any action that creates an RFQ, listing, order, or financial transaction. Add an approved transcription integration before accepting audio requests, and pass an actual confidence score to the sourcing flow.
