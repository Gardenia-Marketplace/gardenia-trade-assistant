# Gardenia Trade Assistant prototype

An independent prototype for Gardenia's buyer and farmer workflows. The web demo is static; the WhatsApp webhook is a separate Python standard-library service.

See [BUILD-PLAN.md](./BUILD-PLAN.md) for product direction, integration boundaries, and production requirements.

## Separate workspaces

Open `buyer.html` for buyer sourcing and tools, or `farmer.html` for the farmer tools. These are separate entry points and show different navigation and capabilities. `index.html` is the underlying app shell and defaults to buyer view; it accepts `?workspace=buyer` or `?workspace=farmer`.

Start a static web server from the project folder:

```powershell
python -m http.server 8000
```

Then visit `http://localhost:8000/buyer.html` or `http://localhost:8000/farmer.html`. The listings and tool outputs are demo content, not live Gardenia data.

## WhatsApp assistant

The WhatsApp Cloud API webhook supports English, Nigerian Pidgin, Hausa, Yoruba, Igbo, and French, role selection, and sourcing and farm-assistance intents. The buyer sourcing flow captures a request, asks for missing details, and is designed to show a verified shortlist and request an order only after explicit confirmation when approved Gardenia tools are connected. No live Gardenia tool adapter is included or configured here, so this repository cannot return real listings, seller profiles, prices, delivery options, quotes, or create orders or recurring plans.

1. Follow [WHATSAPP-SETUP.md](./WHATSAPP-SETUP.md) to configure a Meta WhatsApp Business Cloud API app and a public HTTPS webhook.
2. Copy `.env.example` to `.env` and fill in the values from Meta. The service loads this file on startup without overriding variables already set in the process environment. Do not paste credentials into source code or commit `.env`.
3. Run `python whatsapp_assistant.py`. The app binds to `127.0.0.1:8081` by default. Meta needs a reachable HTTPS callback; use a secure deployment or HTTPS tunnel and configure the app's callback accordingly.
4. In the Meta app, subscribe the webhook to `messages` and send a WhatsApp message to the configured test/business number.

The service handles webhook verification, validates Meta's `X-Hub-Signature-256` HMAC on events, and responds to supported text messages. It stores a keyed hash of the WhatsApp user ID, language/role/opt-out preferences, and an in-progress parsed sourcing request in SQLite. That request can include the buyer's location, delivery address, and selected offer; it is scheduled to expire after 24 hours and is cleared on lookup after expiry. Raw user IDs and full message bodies are not stored. Protect the database as personal data and apply an operational retention/deletion policy. WhatsApp audio is not transcribed, and the bot asks for text instead. `STOP` opts out, and `START` opts back in. The demo does not send proactive messages or perform transactions.

## Development checks

Run the standard-library test suite:

```powershell
python -m unittest discover -s tests -v
```

Required Meta credentials are intentionally absent. Without them, this repository runs the web demo and automated tests, but it cannot send or receive WhatsApp messages.

## GitHub

The intended GitHub repository visibility is **private**, with the suggested name `gardenia-trade-assistant`. Never commit `.env`, Meta access tokens, signing secrets, or private customer/order data.
