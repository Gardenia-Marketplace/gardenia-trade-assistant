import hashlib
import hmac
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import whatsapp_assistant as assistant


class LanguageTests(unittest.TestCase):
    def test_language_commands(self):
        for command, expected in (
            ("LANGUAGE Hausa", "ha"),
            ("LANGUAGE Yoruba", "yo"),
            ("LANGUAGE Igbo", "ig"),
            ("LANGUAGE French", "fr"),
            ("LANGUAGE English", "en"),
        ):
            with self.subTest(command=command):
                language = assistant.requested_language(command)
                self.assertEqual(language, expected)

    def test_detects_supported_languages(self):
        self.assertEqual(assistant.detect_language("Bonjour, je cherche du maïs"), "fr")
        self.assertEqual(assistant.detect_language("Sannu, ina so in saya"), "ha")
        self.assertEqual(assistant.detect_language("Ẹ káàárọ̀, mo fẹ ra"), "yo")
        self.assertEqual(assistant.detect_language("Ndewo, achọrọ m ịzụta"), "ig")

    def test_role_and_intent_replies(self):
        reply, language, role = assistant.build_reply("SOURCE", "en", "")
        self.assertIn("live Gardenia listings", reply)
        self.assertEqual(role, "buyer")
        reply, language, role = assistant.build_reply("LISTING", "en", "buyer")
        self.assertIn("I will not publish it", reply)
        self.assertEqual(role, "farmer")
        reply, language, _ = assistant.build_reply("Bonjour, je cherche du maïs", "en", "")
        self.assertEqual(language, "fr")
        self.assertIn("pas encore connectée", reply)

    def test_unknown_language_is_not_silently_accepted(self):
        self.assertIsNone(assistant.requested_language("LANGUAGE Klingon"))


class PreferenceTests(unittest.TestCase):
    def test_preferences_are_keyed_and_do_not_store_raw_user_id(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "preferences.sqlite3")
            store = assistant.LanguageStore(database, "test-secret")
            store.set("15551234567", "yo", "farmer")
            self.assertEqual(store.get("15551234567"), ("yo", "farmer"))
            import sqlite3

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute("SELECT user_key FROM user_preferences").fetchone()
            self.assertNotEqual(row[0], "15551234567")
            self.assertEqual(len(row[0]), 64)

    def test_parsed_conversation_state_expires_and_is_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "preferences.sqlite3")
            store = assistant.LanguageStore(database, "test-secret")
            store.set("15551234567", "en", "buyer")
            state = {
                "kind": "sourcing",
                "stage": "address",
                "address": "Private delivery address",
                "created_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            }
            store.set_conversation("15551234567", state)
            self.assertEqual(store.get_conversation("15551234567"), {})
            self.assertEqual(store.get("15551234567"), ("en", "buyer"))
            import sqlite3

            with closing(sqlite3.connect(database)) as connection:
                row = connection.execute(
                    "SELECT conversation_json, conversation_expires_at FROM user_preferences"
                ).fetchone()
            self.assertEqual(row, (None, None))


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.sent = []
        self.config = {
            "verify_token": "verify-test",
            "app_secret": "app-secret",
            "access_token": "access",
            "phone_number_id": "phone-id",
            "graph_version": "v23.0",
        }
        self.store = assistant.LanguageStore(
            str(Path(self.tempdir.name) / "preferences.sqlite3"), "hash-secret"
        )
        handler = assistant.create_handler(
            self.config, self.store, sender=lambda *args: self.sent.append(args)
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_health_and_meta_verification(self):
        with urlopen(self.url + "/healthz") as response:
            self.assertEqual(response.read(), b"ok")
        with urlopen(self.url + "/?hub.mode=subscribe&hub.verify_token=verify-test&hub.challenge=123") as response:
            self.assertEqual(response.read(), b"123")

    def test_rejects_bad_signature_and_unknown_route(self):
        request = Request(self.url + "/webhook", data=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 401)
        error.exception.close()
        request = Request(self.url + "/not-webhook", data=b"{}")
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_valid_signed_message_gets_reply_and_saves_language(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15551234567",
                                        "type": "text",
                                        "text": {"body": "LANGUAGE Hausa"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        body = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new(
            self.config["app_secret"].encode(), body, hashlib.sha256
        ).hexdigest()
        request = Request(
            self.url + "/webhook",
            data=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"EVENT_RECEIVED")
        for _ in range(50):
            if self.sent:
                break
            threading.Event().wait(0.02)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("Hausa", self.sent[0][1])
        self.assertEqual(self.store.get("15551234567")[0], "ha")
        self.assertFalse(self.store.is_opted_out("15551234567"))

    def test_stop_suppresses_replies_until_start(self):
        self.store.set("15551234567", "fr", "buyer")
        self.store.set_opted_out("15551234567", True)
        self.assertTrue(self.store.is_opted_out("15551234567"))
        self.store.set_opted_out("15551234567", False)
        self.assertFalse(self.store.is_opted_out("15551234567"))


if __name__ == "__main__":
    unittest.main()
