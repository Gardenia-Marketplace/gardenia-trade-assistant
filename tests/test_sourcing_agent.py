import unittest
from decimal import Decimal

from sourcing_agent import BuyerSourcingAgent


class MemoryStore:
    def __init__(self):
        self.state = {}

    def get_conversation(self, user_id):
        return dict(self.state.get(user_id, {}))

    def set_conversation(self, user_id, state):
        self.state[user_id] = dict(state)

    def clear_conversation(self, user_id):
        self.state.pop(user_id, None)


class FakeTools:
    def __init__(self):
        self.created = []
        self.quotes = []
        self.handoffs = []
        self.split_mode = False

    def search_listings(self, crop, quantity, location, max_price, date):
        self.search = (crop, quantity, location, date)
        if self.split_mode:
            return [
                {
                    "farm_id": "farm-1",
                    "listing_id": "listing-1",
                    "farm_name": "Verified Farm",
                    "state": "Oyo",
                    "price_per_kg": "500",
                    "available_kg": "12",
                    "available": True,
                },
                {
                    "farm_id": "farm-2",
                    "listing_id": "listing-2",
                    "farm_name": "Second Farm",
                    "state": "Ogun",
                    "price_per_kg": "600",
                    "available_kg": "10",
                    "available": True,
                },
            ]
        return [{
            "farm_id": "farm-1",
            "listing_id": "listing-1",
            "farm_name": "Verified Farm",
            "state": "Oyo",
            "price_per_kg": "500",
            "available_kg": "200",
            "available": True,
        }]

    def get_seller_profile(self, farm_id):
        return {"verified": True, "reliability": 97, "quality_evidence": "Grade A"}

    def get_delivery_options(self, farm_id, location):
        return [{"fee": "1500", "date": "2026-05-10", "type": "delivery"}]

    def get_price_trend(self, crop, region):
        return {"movement": "normal"}

    def create_order(self, items, address, delivery_type, idempotency_key):
        self.created.append((items, address, delivery_type, idempotency_key))
        return {"order_id": "order-1", "status": "confirmed"}

    def create_recurring_plan(self, **details):
        return {"plan_id": "plan-1", "status": "confirmed"}

    def request_quote(self, listing_id, quantity):
        self.quotes.append((listing_id, quantity))
        return {"request_id": "quote-1", "status": "requested"}

    def handoff_to_human(self, reason):
        self.handoffs.append(reason)
        return {"status": "queued"}


class SourcingAgentTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.tools = FakeTools()
        self.agent = BuyerSourcingAgent(self.store, self.tools)

    def complete_to_shortlist(self, user="buyer-1"):
        self.assertIn("Where in Nigeria", self.agent.handle(user, "I need 20 kg tomatoes"))
        self.assertIn("What date", self.agent.handle(user, "Yaba, Lagos"))
        self.assertIn("one-off", self.agent.handle(user, "Monday 10 May"))
        shortlist = self.agent.handle(user, "one-off")
        self.assertIn("Verified Farm", shortlist)
        self.assertEqual(self.tools.search, ("tomatoes", Decimal("20"), "Yaba, Lagos", "Monday 10 May"))
        return shortlist

    def test_search_and_order_wait_for_explicit_yes(self):
        shortlist = self.complete_to_shortlist()
        self.assertIn("₦11,500", shortlist)
        self.agent.handle("buyer-1", "1")
        summary = self.agent.handle("buyer-1", "1 Main Street, Yaba, Lagos")
        self.assertIn("20 kg", summary)
        self.assertIn("1 Main Street, Yaba, Lagos", summary)
        self.assertIn("reply YES", summary)
        self.assertFalse(self.tools.created)
        self.agent.handle("buyer-1", "maybe")
        self.assertFalse(self.tools.created)
        result = self.agent.handle("buyer-1", "YES")
        self.assertIn("order-1", result)
        self.assertEqual(len(self.tools.created), 1)
        self.assertEqual(self.tools.created[0][0][0]["total"], Decimal("11500"))
        self.assertTrue(self.tools.created[0][3])

    def test_partial_inventory_can_be_split_across_verified_farms(self):
        self.tools.split_mode = True
        shortlist = self.complete_to_shortlist()
        self.assertIn("Split order", shortlist)
        self.assertIn("12 kg from Verified Farm", shortlist)
        self.assertIn("8 kg from Second Farm", shortlist)
        self.agent.handle("buyer-1", "1")
        summary = self.agent.handle("buyer-1", "1 Main Street, Yaba, Lagos")
        self.assertIn("Total including delivery: ₦13,800", summary)
        self.agent.handle("buyer-1", "YES")
        items = self.tools.created[0][0]
        self.assertEqual([item["quantity_kg"] for item in items], [Decimal("12"), Decimal("8")])

    def test_low_confidence_voice_does_not_start_search(self):
        response = self.agent.handle(
            "buyer-voice", "20 kg tomatoes", input_type="voice", confidence=0.4
        )
        self.assertIn("confirm", response.lower())
        self.assertFalse(self.store.state)

    def test_invalid_voice_confidence_is_clarified_not_raised(self):
        response = self.agent.handle(
            "buyer-voice", "20 kg tomatoes", input_type="voice", confidence="high"
        )
        self.assertIn("confirm", response.lower())
        self.assertFalse(self.store.state)

    def test_bulk_quote_uses_quote_tool_without_claiming_discount(self):
        self.complete_to_shortlist()
        self.assertIn("Which listing", self.agent.handle("buyer-1", "Can I get a bulk quote?"))
        self.assertIn("quantity in kg", self.agent.handle("buyer-1", "1"))
        response = self.agent.handle("buyer-1", "200 kg")
        self.assertIn("quote", response.lower())
        self.assertEqual(self.tools.quotes, [("listing-1", Decimal("200"))])
        self.assertFalse(self.tools.created)

    def test_handoff_does_not_claim_connection_when_tool_is_missing(self):
        agent = BuyerSourcingAgent(self.store)
        response = agent.handoff("buyer-1", "payment problem")
        self.assertIn("can't reach", response.lower())


if __name__ == "__main__":
    unittest.main()
