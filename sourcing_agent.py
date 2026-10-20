"""Stateful, fail-closed buyer sourcing flow shared by Gardenia channels."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


class SourcingTools(Protocol):
    def search_listings(
        self, crop: str, quantity: Decimal, location: str, max_price: Decimal | None, date: str
    ) -> list[dict[str, Any]]: ...

    def get_seller_profile(self, farm_id: str) -> dict[str, Any]: ...

    def get_delivery_options(self, farm_id: str, location: str) -> list[dict[str, Any]]: ...

    def get_price_trend(self, crop: str, region: str) -> dict[str, Any]: ...

    def create_order(
        self,
        items: list[dict[str, Any]],
        address: str,
        delivery_type: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    def create_recurring_plan(self, **details: Any) -> dict[str, Any]: ...

    def request_quote(self, listing_id: str, quantity: Decimal) -> dict[str, Any]: ...

    def handoff_to_human(self, reason: str) -> dict[str, Any]: ...


class ToolUnavailable(RuntimeError):
    pass


LANGUAGE_TEXT = {
    "en": {
        "crop": "What produce do you need?",
        "quantity": "How many kg do you need?",
        "location": "Where in Nigeria should we deliver?",
        "date": "What date do you need it?",
        "cadence": "Is this a one-off order or a recurring supply?",
        "address": "What full delivery address should I include?",
        "confirm_order": "Please reply YES to confirm this order and continue to Gardenia secure checkout. Reply NO to cancel.",
        "no_listings": "I couldn't find a verified offer with complete price and delivery details. I won't guess. Would you like to change the date or location?",
        "not_connected": "I've captured your request, but live Gardenia listing and delivery search isn't connected here yet. I can't show real farms, prices, availability, or place an order.",
        "human_unavailable": "I can't reach a Gardenia agent from this demo. No order was changed or placed. Please contact Gardenia support directly.",
        "search_error": "Gardenia's listing search or seller details are unavailable right now. I haven't confirmed any offer. Please try again later or contact Gardenia support.",
        "quote_unavailable": "Bulk quote requests aren't connected here yet. I won't negotiate or guess a discount.",
        "quote_choose": "Which listing should I request a bulk quote for? Reply 1, 2, or 3.",
        "quote_quantity": "What quantity in kg should I include in the quote request?",
        "low_confidence": "I may have misheard that. Could you confirm the crop, quantity, or location before I search?",
        "need_quantity": "What quantity do you need in kg?",
        "invalid_quantity": "Please confirm the quantity in kg before I search.",
        "choose": "Reply with the number of the farm you want, or tell me what to change.",
        "address_summary": "I have your selected offer. What full delivery address should I include in the order summary?",
        "cancelled": "Okay, I haven't placed an order. Tell me if you'd like to change the request.",
        "confirmed": "Your Gardenia order request was submitted. Continue payment only through Gardenia secure checkout. Order reference: {reference}.",
        "order_error": "I couldn't confirm the order with Gardenia. No successful order is being reported. I'll hand this to a Gardenia agent.",
        "order_status_unknown": "I couldn't confirm Gardenia's response, so I can't tell whether the order was created. I have not reported success. Please contact Gardenia support before trying again.",
        "recurring_error": "The first order was confirmed, but the recurring plan could not be confirmed. I'll hand this to a Gardenia agent to resolve the plan.",
        "human": "I'll connect this to a Gardenia agent. I haven't changed or placed an order.",
        "quality_missing": "The listing has no verified quality evidence available in the tool results. Please request the relevant grade/handling evidence or an inspection before deciding.",
        "repeat": "Please reply YES to confirm or NO to cancel.",
    },
    "pcm": {
        "crop": "Which produce you need?",
        "quantity": "How many kg you need?",
        "location": "Where for Nigeria make we deliver am?",
        "date": "Which date you need am?",
        "cadence": "Na one-time order or you wan supply am regularly?",
        "address": "Wetin be the full delivery address wey I go put?",
        "confirm_order": "Reply YES to confirm this order and continue for Gardenia secure checkout. Reply NO to cancel.",
        "no_listings": "I no fit find verified offer wey get complete price and delivery details. I no go guess. You wan change the date or location?",
        "not_connected": "I don record your request, but live Gardenia farm and delivery search never connect here. I no fit show real farms, prices, availability, or place order. I fit pass your request to Gardenia agent.",
        "low_confidence": "I fit don hear am wrong. Abeg confirm the crop, quantity, or location before I search.",
        "need_quantity": "How many kg you need?",
        "invalid_quantity": "Abeg confirm the quantity for kg before I search.",
        "choose": "Reply with the farm number wey you choose, or tell me wetin to change.",
        "address_summary": "I don get your choice. Wetin be the full delivery address wey I go put for order summary?",
        "cancelled": "No wahala, I never place order. Tell me if you wan change the request.",
        "confirmed": "Your Gardenia order request don submit. Continue payment only for Gardenia secure checkout. Order reference: {reference}.",
        "order_error": "I no fit confirm the order with Gardenia. I no go talk say order succeed. I go pass am to Gardenia agent.",
        "recurring_error": "The first order don confirm, but recurring plan never confirm. I go pass am to Gardenia agent make dem help.",
        "human": "I go connect you to Gardenia agent. I never change or place order.",
        "quality_missing": "The tool results no get verified quality evidence. Abeg ask for grade/handling proof or inspection before you decide.",
        "repeat": "Reply YES to confirm or NO to cancel.",
    },
    "ha": {
        "crop": "Wane amfanin gona kake buƙata?",
        "quantity": "Kilogram nawa kake buƙata?",
        "location": "A ina a Najeriya za a kai kaya?",
        "date": "Wace rana kake buƙatar kayan?",
        "cadence": "Saya sau ɗaya ne ko kana buƙatar kaya akai-akai?",
        "address": "Menene cikakken adireshin kai kaya da zan saka?",
        "confirm_order": "Amsa YES don tabbatar da wannan oda, sannan ka biya ta amintaccen Gardenia checkout. Amsa NO don soke.",
        "no_listings": "Ban sami ingantaccen tayin da ke da cikakken farashi da bayanin kai kaya ba. Ba zan yi zato ba. Kana so a canza rana ko wuri?",
        "not_connected": "Na rubuta buƙatarka, amma ba a haɗa binciken gonaki da kai kaya na Gardenia kai tsaye ba. Ba zan iya nuna gonaki, farashi, kaya ko yin oda na gaske ba. Zan iya miƙa buƙatarka ga wakilin Gardenia.",
        "low_confidence": "Wataƙila ban ji daidai ba. Ka tabbatar da amfanin gona, adadi, ko wuri kafin in bincika.",
        "need_quantity": "Kilogram nawa kake buƙata?",
        "invalid_quantity": "Ka tabbatar da adadin kilogram kafin in bincika.",
        "choose": "Amsa lambar gonar da kake so, ko ka faɗi abin da za a canza.",
        "address_summary": "Na zaɓi tayin. Menene cikakken adireshin kai kaya da zan saka?",
        "cancelled": "To, ban yi oda ba. Ka faɗa idan kana son canza buƙata.",
        "confirmed": "An aika buƙatar odarka zuwa Gardenia. Ci gaba da biyan kuɗi ta amintaccen Gardenia checkout kawai. Lambar oda: {reference}.",
        "order_error": "Ban iya tabbatar da oda daga Gardenia ba. Ba zan ce an yi nasara ba. Zan miƙa wa wakilin Gardenia.",
        "recurring_error": "An tabbatar da odar farko amma ba a tabbatar da shirin maimaitawa ba. Zan miƙa wa wakilin Gardenia.",
        "human": "Zan haɗa ka da wakilin Gardenia. Ban canza ko sanya oda ba.",
        "quality_missing": "Babu ingantacciyar shaidar inganci a bayanan kayan aiki. Ka nemi shaidar aji ko kulawa, ko a duba kaya kafin yanke shawara.",
        "repeat": "Amsa YES don tabbatarwa ko NO don soke.",
    },
    "yo": {
        "crop": "Èso wo ló nílò?",
        "quantity": "Kg mélòó lo nílò?",
        "location": "Ibo ni Nàìjíríà ni kí a fi ránṣẹ́ sí?",
        "date": "Ọjọ́ wo lo nílò rẹ̀?",
        "cadence": "Ìrà lẹ́ẹ̀kan ni, tàbí ìpèsè tó máa ń padà dé?",
        "address": "Kí ni àdírẹ́sì ìfijiṣẹ́ kíkún tí kí n fi sínú àkótán?",
        "confirm_order": "Dáhùn YES láti fìdí àṣẹ yìí múlẹ̀, kí o sì tẹ̀síwájú sí Gardenia secure checkout. Dáhùn NO láti fagilé.",
        "no_listings": "Mi ò rí ọjà oko tí a fìdí rẹ̀ múlẹ̀ tó sì ní gbogbo iye owó àti ìfijiṣẹ́. Mi ò ní sọ nọ́ńbà àfojúsùn. Ṣé o fẹ́ yí ọjọ́ tàbí ibi padà?",
        "not_connected": "Mo ti gba àìní rẹ, ṣùgbọ́n a kò tíì so ìwádìí ọjà oko àti ìfijiṣẹ́ Gardenia pọ̀. Mi ò lè fi oko, owó tàbí ọjà gidi hàn tàbí ṣe àṣẹ. Mo lè fi ìbéèrè náà ránṣẹ́ sí òṣìṣẹ́ Gardenia.",
        "low_confidence": "Ó ṣeé ṣe kí n má gbọ́ dáadáa. Jọ̀wọ́ jẹ́rìí ọjà, iye, tàbí ibi kí n tó wá a.",
        "need_quantity": "Kg mélòó lo nílò?",
        "invalid_quantity": "Jọ̀wọ́ jẹ́rìí iye kg kí n tó wá a.",
        "choose": "Dáhùn nọ́mbà oko tí o fẹ́, tàbí sọ ohun tí o fẹ́ yí padà.",
        "address_summary": "Mo ti gba yíyan rẹ. Kí ni àdírẹ́sì ìfijiṣẹ́ kíkún tí kí n fi sínú àkótán?",
        "cancelled": "Ó dára, mi ò ṣe àṣẹ kankan. Sọ bí o bá fẹ́ yí ìbéèrè padà.",
        "confirmed": "A ti fi ìbéèrè àṣẹ rẹ ránṣẹ́ sí Gardenia. Tẹ̀síwájú pẹ̀lú ìsanwó ní Gardenia secure checkout nìkan. Nọ́mbà àṣẹ: {reference}.",
        "order_error": "Mi ò lè fìdí àṣẹ múlẹ̀ pẹ̀lú Gardenia. Mi ò ní sọ pé ó yọrí sí rere. Màá fi fún òṣìṣẹ́ Gardenia.",
        "recurring_error": "A fìdí àṣẹ àkọ́kọ́ múlẹ̀, ṣùgbọ́n a kò fìdí ètò ìpèsè tó ń tún ara rẹ̀ ṣe múlẹ̀. Màá fi fún òṣìṣẹ́ Gardenia.",
        "human": "Màá so ọ́ pọ̀ mọ́ òṣìṣẹ́ Gardenia. Mi ò yí ohunkóhun padà tàbí ṣe àṣẹ.",
        "quality_missing": "Kò sí ẹ̀rí dídára tí a fìdí rẹ̀ múlẹ̀ nínú èsì irinṣẹ́. Jọ̀wọ́ béèrè ẹ̀rí ìpele/títọ́jú tàbí àyẹ̀wò kí o tó pinnu.",
        "repeat": "Dáhùn YES láti fìdí múlẹ̀ tàbí NO láti fagilé.",
    },
    "ig": {
        "crop": "Kedu ihe ubi ị chọrọ?",
        "quantity": "Kg ole ka ịchọrọ?",
        "location": "Ebee na Naịjirịa ka a ga-ebuga ya?",
        "date": "Kedu ụbọchị ịchọrọ ya?",
        "cadence": "Ọ bụ otu ugboro ka ọ bụ nnyefe na-aga n'ihu?",
        "address": "Kedu adreesị nnyefe zuru ezu m ga-etinye?",
        "confirm_order": "Zaghachi YES iji kwenye iwu a, gaa n'ihu na Gardenia secure checkout. Zaghachi NO kagbuo.",
        "no_listings": "Ahụghị m ngwaahịa ugbo akwadoro nwere ọnụahịa na nnyefe zuru ezu. Agaghị m echepụta ha. Ị chọrọ ịgbanwe ụbọchị ma ọ bụ ebe?",
        "not_connected": "Edere m arịrịọ gị, mana ejikọtaghị ọchụchọ ugbo na nnyefe Gardenia ugbu a. Enweghị m ike igosi ezigbo ugbo, ọnụahịa, ngwaahịa ma ọ bụ tinye iwu. Enwere m ike inyefe onye ọrụ Gardenia arịrịọ ahụ.",
        "low_confidence": "O nwere ike ịbụ na aghọtachaghị m nke ọma. Biko kwenye ihe ubi, ọnụọgụ, ma ọ bụ ebe tupu m chọọ ya.",
        "need_quantity": "Kg ole ka ịchọrọ?",
        "invalid_quantity": "Biko kwenye ọnụọgụ kg tupu m chọọ ya.",
        "choose": "Zaghachi nọmba ugbo ịchọrọ, ma ọ bụ gwa m ihe a ga-agbanwe.",
        "address_summary": "Ahọrọla m onyinye ahụ. Kedu adreesị nnyefe zuru ezu m ga-etinye?",
        "cancelled": "Ọ dị mma, etinyeghị m iwu. Gwa m ma ịchọrọ ịgbanwe arịrịọ ahụ.",
        "confirmed": "E zigara arịrịọ iwu gị na Gardenia. Gaa n'ihu na ịkwụ ụgwọ naanị na Gardenia secure checkout. Nọmba iwu: {reference}.",
        "order_error": "Enweghị m ike ikwenye iwu ahụ na Gardenia. Agaghị m ekwu na ọ gara nke ọma. Aga m enyefe ya onye ọrụ Gardenia.",
        "recurring_error": "Ekwenyela iwu mbụ, mana enwebeghị nkwenye maka atụmatụ nnyefe ugboro ugboro. Aga m enyefe onye ọrụ Gardenia.",
        "human": "Aga m ejikọ gị na onye ọrụ Gardenia. Agbanwebeghị m ma ọ bụ tinye iwu.",
        "quality_missing": "Enweghị ihe akaebe ịdị mma akwadoro na nsonaazụ ngwaọrụ. Biko rịọ maka ihe akaebe ọkwa/njikwa ma ọ bụ nyocha tupu ị kpebie.",
        "repeat": "Zaghachi YES iji kwenye ma ọ bụ NO kagbuo.",
    },
}

PRODUCE_WORDS = (
    "tomatoes", "tomato", "onions", "onion", "pepper", "ugu", "spinach", "okra",
    "plantain", "banana", "cassava", "yam", "maize", "corn", "rice", "beans",
    "potato", "carrot", "cabbage", "lettuce", "cucumber", "ginger", "garlic",
    "cocoyam", "mango", "orange", "pineapple", "watermelon",
)
SOURCE_CUES = ("need", "want", "looking for", "buy", "order", "source", "find", "abeg", "dey find", "i need", "i want")
RECURRING_CUES = ("every", "weekly", "daily", "each monday", "each week", "regular", "recurring", "every monday")


def normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def prompt(language: str, key: str) -> str:
    return LANGUAGE_TEXT.get(language, LANGUAGE_TEXT["en"]).get(key, LANGUAGE_TEXT["en"][key])


def extract_crop(text: str) -> str | None:
    normalized = normalize(text)
    for word in sorted(PRODUCE_WORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", normalized):
            return word
    return None


def parse_quantity_kg(text: str) -> Decimal | None:
    normalized = normalize(text).replace(",", "")
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(kg|kgs|kilograms?|kilo)\b", normalized)
    if not match:
        return None
    try:
        quantity = Decimal(match.group(1))
    except InvalidOperation:
        return None
    if quantity <= 0 or quantity > Decimal("1000000"):
        return None
    return quantity


def _money(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def _format_ngn(value: Decimal) -> str:
    return f"₦{value:,.2f}".removesuffix(".00")


def _usable_candidates(
    listings: list[dict[str, Any]],
    tools: SourcingTools,
    location: str,
    quantity: Decimal,
    *,
    allow_partial: bool = False,
) -> list[dict[str, Any]]:
    candidates = []
    for listing in listings:
        farm_id = listing.get("farm_id")
        listing_id = listing.get("listing_id")
        price_per_kg = _money(listing.get("price_per_kg"))
        available_kg = _money(listing.get("available_kg"))
        if not farm_id or not listing_id or price_per_kg is None or available_kg is None:
            continue
        if available_kg <= 0 or (available_kg < quantity and not allow_partial) or listing.get("available") is False:
            continue
        profile = tools.get_seller_profile(str(farm_id))
        if profile.get("verified") is not True:
            continue
        delivery_options = tools.get_delivery_options(str(farm_id), location)
        options = [
            option for option in delivery_options
            if _money(option.get("fee")) is not None and option.get("date") and option.get("type")
        ]
        if not options:
            continue
        delivery = options[0]
        allocated_kg = min(available_kg, quantity)
        total = price_per_kg * allocated_kg + _money(delivery["fee"])
        reliability = profile.get("reliability")
        if not isinstance(reliability, (int, float, Decimal)) or not 0 <= float(reliability) <= 100:
            reliability = None
        candidates.append({
            "listing": listing,
            "profile": profile,
            "delivery": delivery,
            "price_per_kg": price_per_kg,
            "available_kg": available_kg,
            "delivery_fee": _money(delivery["fee"]),
            "allocated_kg": allocated_kg,
            "total": total,
            "reliability": reliability,
        })
    return candidates


def _split_plan(candidates: list[dict[str, Any]], quantity: Decimal) -> dict[str, Any] | None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        delivery = candidate["delivery"]
        groups.setdefault((delivery["type"], delivery["date"]), []).append(candidate)

    plans = []
    for (delivery_type, delivery_date), group in groups.items():
        remaining = quantity
        parts = []
        ordered = sorted(group, key=lambda item: (item["price_per_kg"], item["delivery_fee"]))
        used_farms = set()
        for candidate in ordered:
            farm_id = candidate["listing"]["farm_id"]
            if farm_id in used_farms:
                continue
            allocated = min(candidate["available_kg"], remaining)
            if allocated <= 0:
                continue
            used_farms.add(farm_id)
            parts.append({
                "listing_id": candidate["listing"]["listing_id"],
                "farm_id": candidate["listing"]["farm_id"],
                "farm_name": candidate["listing"].get("farm_name"),
                "state": candidate["listing"].get("state"),
                "quantity_kg": allocated,
                "price_per_kg": candidate["price_per_kg"],
                "delivery_fee": candidate["delivery_fee"],
                "total": candidate["price_per_kg"] * allocated + candidate["delivery_fee"],
                "delivery_type": delivery_type,
                "delivery_date": delivery_date,
                "reliability": candidate["reliability"],
                "quality_evidence": candidate["profile"].get("quality_evidence"),
            })
            remaining -= allocated
            if remaining <= 0:
                break
        if remaining <= 0 and len(parts) > 1:
            plans.append({
                "is_split": True,
                "parts": parts,
                "delivery_type": delivery_type,
                "delivery_date": delivery_date,
                "total": sum((part["total"] for part in parts), Decimal("0")),
                "reliability": min(
                    (part["reliability"] for part in parts if part["reliability"] is not None),
                    default=None,
                ),
            })
    if not plans:
        return None
    return min(plans, key=lambda plan: plan["total"])


def shortlist_message(candidates: list[dict[str, Any]], quantity: Decimal, language: str = "en") -> str:
    lines = []
    for index, candidate in enumerate(candidates[:3], 1):
        if candidate.get("is_split"):
            parts = []
            for part in candidate["parts"]:
                farm = part.get("farm_name") or "Farm name not supplied"
                state = part.get("state") or "State not supplied"
                reliability = (
                    f"{part['reliability']}% on-time"
                    if part["reliability"] is not None
                    else "reliability not supplied"
                )
                parts.append(
                    f"{part['quantity_kg']} kg from {farm} ({state}) at "
                    f"{_format_ngn(part['price_per_kg'])}/kg plus "
                    f"{_format_ngn(part['delivery_fee'])} delivery, reliability {reliability}"
                )
            lines.append(
                f"{index}. Split order: {'; '.join(parts)} - Total "
                f"{_format_ngn(candidate['total'])} - Delivery "
                f"{candidate['delivery_type']}/{candidate['delivery_date']}"
            )
            continue
        listing = candidate["listing"]
        profile = candidate["profile"]
        delivery = candidate["delivery"]
        reliability = (
            f"{candidate['reliability']}% on-time"
            if candidate["reliability"] is not None
            else "Not supplied"
        )
        farm = listing.get("farm_name") or "Farm name not supplied"
        state = listing.get("state") or "State not supplied"
        price = _format_ngn(candidate["price_per_kg"])
        total = _format_ngn(candidate["total"])
        line = (
            f"{index}. {farm} - {state} - {price}/kg - Total {total} "
            f"(includes {_format_ngn(candidate['delivery_fee'])} delivery) - "
            f"Delivery {delivery['type']}/{delivery['date']} - Reliability {reliability}"
        )
        quality = profile.get("quality_evidence")
        if quality:
            line += f" - Quality evidence: {quality}"
        elif language == "en":
            line += " - Quality: evidence not supplied"
        lines.append(line)
    return "\n".join(lines)


class BuyerSourcingAgent:
    def __init__(self, store: Any, tools: SourcingTools | None = None):
        self.store = store
        self.tools = tools

    def _get_state(self, user_id: str) -> dict[str, Any]:
        return self.store.get_conversation(user_id)

    def _save(self, user_id: str, state: dict[str, Any]) -> None:
        self.store.set_conversation(user_id, state)

    def _clear(self, user_id: str) -> None:
        self.store.clear_conversation(user_id)

    def handle(
        self,
        user_id: str,
        text: str,
        language: str = "en",
        *,
        input_type: str = "text",
        confidence: float | None = None,
    ) -> str | None:
        normalized = normalize(text)
        if input_type == "voice" and (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.75 <= confidence <= 1.0
        ):
            return prompt(language, "low_confidence")
        if re.search(r"\b(complaint|refund|dispute|payment failed|angry|upset)\b", normalized):
            return self.handoff(user_id, "buyer complaint, dispute, refund, or payment issue", language)

        state = self._get_state(user_id)
        if normalized in ("cancel", "cancel order", "stop request"):
            self._clear(user_id)
            return prompt(language, "cancelled")
        if not state:
            if not any(cue in normalized for cue in SOURCE_CUES) and not extract_crop(normalized):
                return None
            crop = extract_crop(normalized)
            quantity = parse_quantity_kg(normalized)
            state = {
                "kind": "sourcing",
                "stage": "location" if crop and quantity else "quantity",
                "crop": crop,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if not state["crop"]:
                state["stage"] = "crop"
                self._save(user_id, state)
                return prompt(language, "crop")
            if quantity:
                state["quantity_kg"] = str(quantity)
            self._save(user_id, state)
            return prompt(language, "location") if quantity else prompt(language, "quantity")

        stage = state.get("stage")
        if stage == "quantity":
            quantity = parse_quantity_kg(normalized)
            if quantity is None:
                return prompt(language, "need_quantity")
            state["quantity_kg"] = str(quantity)
            state["stage"] = "location"
            self._save(user_id, state)
            return prompt(language, "location")
        if stage == "crop":
            crop = extract_crop(normalized)
            if not crop:
                state["crop"] = normalized[:80]
            else:
                state["crop"] = crop
            state["stage"] = "quantity"
            self._save(user_id, state)
            return prompt(language, "quantity")
        if stage == "location":
            state["location"] = text.strip()[:160]
            state["stage"] = "date"
            self._save(user_id, state)
            return prompt(language, "date")
        if stage == "date":
            state["date"] = text.strip()[:100]
            state["stage"] = "cadence"
            self._save(user_id, state)
            return prompt(language, "cadence")
        if stage == "cadence":
            state["recurring"] = any(cue in normalized for cue in RECURRING_CUES)
            state["cadence"] = text.strip()[:100] if state["recurring"] else None
            if not self.tools:
                self._save(user_id, state)
                return prompt(language, "not_connected")
            try:
                quantity = Decimal(state["quantity_kg"])
                listings = self.tools.search_listings(
                    state["crop"], quantity, state["location"], None, state["date"]
                )
                available = _usable_candidates(
                    listings, self.tools, state["location"], quantity, allow_partial=True
                )
                candidates = [
                    item for item in available if item["available_kg"] >= quantity
                ]
                if not candidates:
                    split = _split_plan(available, quantity)
                    candidates = [split] if split else []
                trend = self.tools.get_price_trend(state["crop"], state["location"])
                if not isinstance(trend, dict):
                    self._save(user_id, state)
                    return prompt(language, "search_error")
            except ToolUnavailable:
                self._save(user_id, state)
                return prompt(language, "not_connected")
            except Exception:
                self._save(user_id, state)
                return prompt(language, "search_error")
            if not candidates:
                self._save(user_id, state)
                return prompt(language, "no_listings")
            candidates.sort(key=lambda item: (
                item["total"],
                -(item["reliability"] if item["reliability"] is not None else -1),
                item["delivery_date"] if item.get("is_split") else item["delivery"]["date"],
            ))
            saved_candidates = []
            for candidate in candidates[:3]:
                if candidate.get("is_split"):
                    parts = candidate["parts"]
                else:
                    parts = [{
                        "listing_id": candidate["listing"]["listing_id"],
                        "farm_id": candidate["listing"]["farm_id"],
                        "farm_name": candidate["listing"].get("farm_name"),
                        "state": candidate["listing"].get("state"),
                        "quantity_kg": quantity,
                        "price_per_kg": candidate["price_per_kg"],
                        "delivery_fee": candidate["delivery_fee"],
                        "total": candidate["total"],
                        "delivery_type": candidate["delivery"]["type"],
                        "delivery_date": candidate["delivery"]["date"],
                        "reliability": candidate["reliability"],
                        "quality_evidence": candidate["profile"].get("quality_evidence"),
                    }]
                saved_candidates.append({
                    "is_split": bool(candidate.get("is_split")),
                    "parts": [
                        {
                            key: str(value) if isinstance(value, Decimal) else value
                            for key, value in part.items()
                        }
                        for part in parts
                    ],
                    "total": str(candidate["total"]),
                    "delivery_type": (
                        candidate["delivery_type"] if candidate.get("is_split")
                        else candidate["delivery"]["type"]
                    ),
                    "delivery_date": (
                        candidate["delivery_date"] if candidate.get("is_split")
                        else candidate["delivery"]["date"]
                    ),
                    "reliability": candidate["reliability"],
                })
            state["candidates"] = saved_candidates
            state["stage"] = "choose"
            self._save(user_id, state)
            reply = shortlist_message(candidates, quantity, language) + "\nRecommendation: lowest confirmed delivered total among verified farms with complete delivery details. Reply 1, 2, or 3 to choose, or tell me what to change."
            if trend.get("movement") in ("unusually_high", "unusually_low"):
                reply += f"\nPrice trend: Gardenia data reports an unusually {'high' if trend['movement'] == 'unusually_high' else 'low'} price for this crop in this region."
            return reply
        if stage == "quote_choice":
            choice = re.fullmatch(r"\s*([1-3])\s*", text)
            candidates = state.get("candidates", [])
            if not choice or int(choice.group(1)) > len(candidates):
                return prompt(language, "quote_choose")
            candidate = candidates[int(choice.group(1)) - 1]
            if candidate["is_split"]:
                return prompt(language, "quote_unavailable")
            state["quote_listing_id"] = candidate["parts"][0]["listing_id"]
            state["stage"] = "quote_quantity"
            self._save(user_id, state)
            return prompt(language, "quote_quantity")
        if stage == "quote_quantity":
            quantity = parse_quantity_kg(normalized)
            if quantity is None:
                return prompt(language, "need_quantity")
            if not self.tools:
                return prompt(language, "quote_unavailable")
            try:
                quote = self.tools.request_quote(state["quote_listing_id"], quantity)
            except Exception:
                return prompt(language, "search_error")
            if (
                not isinstance(quote, dict)
                or not quote.get("request_id")
                or quote.get("status") not in ("requested", "created")
            ):
                return prompt(language, "quote_unavailable")
            self._clear(user_id)
            return str(quote.get("message") or "Gardenia received the quote request. No discount or price is guaranteed.")
        if stage == "choose":
            if any(term in normalized for term in ("bulk", "quote", "discount")):
                if not self.tools:
                    return prompt(language, "quote_unavailable")
                state["stage"] = "quote_choice"
                self._save(user_id, state)
                return prompt(language, "quote_choose")
            choice = re.fullmatch(r"\s*([1-3])\s*", text)
            if not choice:
                return prompt(language, "choose")
            index = int(choice.group(1)) - 1
            candidates = state.get("candidates", [])
            if index >= len(candidates):
                return prompt(language, "choose")
            state["selected"] = candidates[index]
            state["stage"] = "address"
            self._save(user_id, state)
            return prompt(language, "address_summary")
        if stage == "address":
            if len(text.strip()) < 5:
                return prompt(language, "address")
            state["address"] = text.strip()[:500]
            state["stage"] = "confirm"
            self._save(user_id, state)
            return self._order_summary(state, language)
        if stage == "confirm":
            if normalized == "no":
                self._clear(user_id)
                return prompt(language, "cancelled")
            if normalized != "yes":
                return prompt(language, "repeat")
            if not self.tools:
                self._clear(user_id)
                return prompt(language, "not_connected")
            selected = state["selected"]
            items = [
                {
                    "listing_id": part["listing_id"],
                    "farm_id": part["farm_id"],
                    "crop": state["crop"],
                    "quantity_kg": Decimal(part["quantity_kg"]),
                    "price_per_kg": Decimal(part["price_per_kg"]),
                    "delivery_fee": Decimal(part["delivery_fee"]),
                    "total": Decimal(part["total"]),
                    "delivery_date": part["delivery_date"],
                }
                for part in selected["parts"]
            ]
            if any(
                item["quantity_kg"] * item["price_per_kg"] + item["delivery_fee"] != item["total"]
                for item in items
            ) or sum((item["total"] for item in items), Decimal("0")) != Decimal(selected["total"]):
                self._clear(user_id)
                return prompt(language, "order_error")
            idempotency_key = hashlib.sha256(
                f"{user_id}:{state['created_at']}".encode("utf-8")
            ).hexdigest()
            try:
                result = self.tools.create_order(
                    items,
                    state["address"],
                    selected["delivery_type"],
                    idempotency_key=idempotency_key,
                )
            except Exception:
                self._clear(user_id)
                return self._order_handoff(language)
            reference = result.get("order_id") if isinstance(result, dict) else None
            if not reference or result.get("status") not in ("confirmed", "created"):
                self._clear(user_id)
                return self._order_handoff(language)
            if state.get("recurring"):
                try:
                    plan = self.tools.create_recurring_plan(
                        items=items,
                        address=state["address"],
                        cadence=state["cadence"],
                        start_date=selected["delivery_date"],
                        order_id=reference,
                    )
                except Exception:
                    self._clear(user_id)
                    return self.handoff(user_id, "first order confirmed but recurring plan failed", language)
                if (
                    not isinstance(plan, dict)
                    or not plan.get("plan_id")
                    or plan.get("status") not in ("confirmed", "created")
                ):
                    self._clear(user_id)
                    return self.handoff(user_id, "first order confirmed but recurring plan was not confirmed", language)
            self._clear(user_id)
            return prompt(language, "confirmed").format(reference=reference)
        return prompt(language, "not_connected")

    def _order_summary(self, state: dict[str, Any], language: str) -> str:
        selected = state["selected"]
        quantity = Decimal(state["quantity_kg"])
        lines = [
            f"Order summary: {state['crop']} — {quantity} kg",
        ]
        for part in selected["parts"]:
            lines.extend([
                f"Farm: {part.get('farm_name') or 'Name not supplied'} — {part.get('state') or 'State not supplied'}",
                f"Quantity: {part['quantity_kg']} kg at {_format_ngn(Decimal(part['price_per_kg']))}/kg",
                f"Delivery: {_format_ngn(Decimal(part['delivery_fee']))} — {part['delivery_type']} — {part['delivery_date']}",
                f"Farm subtotal including delivery: {_format_ngn(Decimal(part['total']))}",
            ])
        lines.extend([
            f"Total including delivery: {_format_ngn(Decimal(selected['total']))}",
            f"Address: {state['address']}",
        ])
        if state.get("recurring"):
            lines.extend([
                f"Recurring request: {state['cadence']}",
                "Recurring stock and pause/cancel terms must be confirmed with Gardenia; they are not connected in this prototype.",
            ])
        lines.append(prompt(language, "confirm_order"))
        return "\n".join(lines)

    def handoff(self, user_id: str, reason: str, language: str = "en") -> str:
        if not self.tools:
            self._clear(user_id)
            return prompt(language, "human_unavailable")
        try:
            result = self.tools.handoff_to_human(reason)
        except Exception:
            self._clear(user_id)
            return prompt(language, "human_unavailable")
        self._clear(user_id)
        if not isinstance(result, dict) or result.get("status") not in ("queued", "connected", "created"):
            return prompt(language, "human_unavailable")
        return prompt(language, "human")

    def _order_handoff(self, language: str) -> str:
        if not self.tools:
            return prompt(language, "order_status_unknown")
        try:
            result = self.tools.handoff_to_human("Gardenia order status could not be confirmed")
        except Exception:
            return prompt(language, "order_status_unknown")
        if isinstance(result, dict) and result.get("status") in ("queued", "connected", "created"):
            return prompt(language, "order_error")
        return prompt(language, "order_status_unknown")
