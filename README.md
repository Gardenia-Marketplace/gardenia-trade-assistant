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

The WhatsApp Cloud API webhook supports English, Hausa, Yoruba, Igbo, and French, role selection, sourcing and farm-assistance intents, and a saved language preference. It is a guided assistant; it does not access the web demo, Gardenia accounts, live marketplace listings, orders, or prices.

1. Follow [WHATSAPP-SETUP.md](./WHATSAPP-SETUP.md) to configure a Meta WhatsApp Business Cloud API app and a public HTTPS webhook.
2. Copy `.env.example` to `.env` and fill in the values from Meta. The service loads this file on startup without overriding variables already set in the process environment. Do not paste credentials into source code or commit `.env`.
3. Run `python whatsapp_assistant.py`. The app binds to `127.0.0.1:8081` by default. Meta needs a reachable HTTPS callback; use a secure deployment or HTTPS tunnel and configure the app's callback accordingly.
4. In the Meta app, subscribe the webhook to `messages` and send a WhatsApp message to the configured test/business number.

The service handles webhook verification, validates Meta's `X-Hub-Signature-256` HMAC on events, and responds to supported text messages. It stores only a keyed hash of the WhatsApp user ID and the user's language/role/opt-out preference in SQLite; message bodies and raw user IDs are not stored. `STOP` opts out, and `START` opts back in. The demo does not send proactive messages or perform transactions.

## Development checks

Run the standard-library test suite:

```powershell
python -m unittest discover -s tests -v
```

Required Meta credentials are intentionally absent. Without them, this repository runs the web demo and automated tests, but it cannot send or receive WhatsApp messages.

## GitHub

The intended GitHub repository visibility is **private**, with the suggested name `gardenia-trade-assistant`. Never commit `.env`, Meta access tokens, signing secrets, or private customer/order data.
