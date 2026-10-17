"""Gardenia multilingual WhatsApp Cloud API webhook (standard library only)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

LOG = logging.getLogger("gardenia.whatsapp")
SUPPORTED_LANGUAGES = ("en", "ha", "yo", "ig", "fr")
LANGUAGE_NAMES = {
    "en": "English",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo",
    "fr": "Français",
}
TEXT: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome to Gardenia. Reply BUYER or FARMER to choose your assistant, or HELP for options. Supported languages: English, Hausa, Yoruba, Igbo, French. Change language anytime with LANGUAGE followed by the language name.",
        "help": "Buyer: SOURCE, REORDER, DEMAND, or QUALITY. Farmer: LISTING, PLANNER, PRICING, POST-HARVEST, or FINANCE. Reply BUYER or FARMER to switch role. Demo guidance only; this WhatsApp assistant is not connected to live Gardenia listings or your account yet.",
        "language": "Language set to {language}. You can change it with LANGUAGE English, Hausa, Yoruba, Igbo, or French.",
        "buyer": "Buyer assistant selected. Ask SOURCE for product-finding guidance, REORDER for repeat-purchase planning, DEMAND for a demand scenario, or QUALITY for a freshness checklist. Live listings and order history are not connected yet.",
        "farmer": "Farmer assistant selected. Ask LISTING for a listing draft checklist, PLANNER for planting and harvest planning, PRICING for a price comparison, POST-HARVEST for handling checks, or FINANCE for cash-flow arithmetic.",
        "source": "Sourcing assistant: send product, grade, quantity and unit, delivery location, and target date. I can help shape a brief, but live Gardenia listings and supplier matching are not connected yet.",
        "reorder": "Smart reorder: share the product, last order date and quantity, current stock, and when you need more. I can help make a reminder checklist. Your Gardenia order history is not connected, so I cannot generate a real reorder alert.",
        "demand": "Demand planning: share the product, recent weekly sales or usage, and the planning horizon. I can outline a scenario, but no Gardenia sales, seasonality, or market data is connected for a real forecast.",
        "quality": "Quality and freshness: share the product, harvest or packing date, lot, storage/transport conditions, and evidence available. I can provide checks to request, not verify quality. A physical inspection or qualified test may be needed.",
        "listing": "Listing copilot: send crop/product, available quantity and unit, grade/quality facts, collection location, and your asking price if known. I can draft clear listing text for you to review. I will not publish it.",
        "planner": "Harvest planner: share crop and variety, farm location, planting date (or planned date), and your expected days to maturity. I can outline a planning calendar; local weather and extension advice are not connected.",
        "pricing": "Pricing advisor: share product, grade, unit, location, your target price, and a recent comparable reference price. I can compare your inputs; I do not have live market prices.",
        "postharvest": "Post-harvest assistant: share the crop, harvest date, symptoms or handling concern, and storage conditions. I can suggest general checks, not diagnose spoilage or certify food safety. Follow local extension guidance.",
        "finance": "Farm finance: share cash available, expected sales, operating costs, and the next-cycle amount needed (include currency and timing). I can help with basic planning arithmetic, not credit or lending decisions.",
        "fallback": "I didn't quite understand. Reply HELP for the menu, BUYER or FARMER to choose a role, or send LANGUAGE Hausa/Yoruba/Igbo/French to change language.",
        "text_only": "Please send a text message. For a photo or document, describe the crop and what you want help checking. This assistant cannot inspect images yet.",
        "stopped": "You are opted out. Gardenia will not send further assistant replies unless you send START.",
    },
    "ha": {
        "welcome": "Barka da zuwa Gardenia. Amsa BUYER ko FARMER don zaɓar mataimaki, ko HELP don ganin zaɓuɓɓuka. Harsuna: Turanci, Hausa, Yarbanci, Igbo, Faransanci. Canza harshe da LANGUAGE sannan sunan harshe.",
        "help": "Mai saye: SOURCE, REORDER, DEMAND, ko QUALITY. Manomi: LISTING, PLANNER, PRICING, POST-HARVEST, ko FINANCE. Amsa BUYER ko FARMER don canza matsayi. Shawara ce ta demo kawai; ba a haɗa wannan mataimaki da kayayyaki ko asusunka na Gardenia ba tukuna.",
        "language": "An saita harshe zuwa {language}. Za ka iya canzawa da LANGUAGE da sunan harshe.",
        "buyer": "An zaɓi mataimakin mai saye. Amsa SOURCE don taimakon neman kaya, REORDER don shirin sake saya, DEMAND don kimanta buƙata, ko QUALITY don jerin duba sabo. Ba a haɗa kayayyaki ko tarihin sayayya kai tsaye ba tukuna.",
        "farmer": "An zaɓi mataimakin manomi. Amsa LISTING don rubutun kaya, PLANNER don shirin shuka da girbi, PRICING don kwatanta farashi, POST-HARVEST don sarrafa bayan girbi, ko FINANCE don lissafin kuɗi.",
        "source": "Taimakon nema: aika sunan kaya, inganci, adadi da ma'auni, wurin kaiwa, da ranar da kake buƙata. Zan taimaka tsara buƙata, amma ba a haɗa binciken kayayyaki na Gardenia kai tsaye ba tukuna.",
        "reorder": "Sake saya: aika kaya, ranar da adadin sayayya ta ƙarshe, abin da kake da shi yanzu, da lokacin da kake buƙata. Zan taimaka da jerin tunatarwa; ba a haɗa tarihin sayayyarka na Gardenia ba.",
        "demand": "Shirin buƙata: aika kaya, adadin sayarwa ko amfani na mako-mako, da tsawon lokacin shiri. Zan taimaka da misali, amma babu bayanan Gardenia ko na kasuwa don hasashe na gaske.",
        "quality": "Inganci da sabo: aika kaya, ranar girbi ko tattarawa, lamba, yanayin ajiya da jigila, da shaidar da kake da ita. Zan ba da jerin dubawa kawai; ba zan iya tabbatar da inganci ba. Ana iya buƙatar gwajin ƙwararre.",
        "listing": "Mataimakin talla: aika kaya, adadi da ma'auni, gaskiyar inganci, wurin karɓa, da farashinka idan ka sani. Zan tsara rubutun talla don ka duba; ba zan wallafa shi ba.",
        "planner": "Shirin girbi: aika amfanin gona da iri, wurin gona, ranar shuka, da kwanakin da kake tsammanin girbi. Zan tsara jadawali na kimanta kawai; ba a haɗa yanayi ko shawarar jami'in noma ba.",
        "pricing": "Shawarar farashi: aika kaya, inganci, ma'auni, wuri, farashin da kake so, da farashin kwatanci na kwanan nan. Zan kwatanta bayananka ne kawai; ba ni da farashin kasuwa na yanzu.",
        "postharvest": "Bayan girbi: aika amfanin gona, ranar girbi, matsalar da kake gani, da yanayin ajiya. Zan ba da dubawa ta gaba ɗaya, ba gano lalacewa ko tabbatar da lafiyar abinci ba. Bi shawarar jami'in noma na yankinka.",
        "finance": "Kuɗin gona: aika kuɗin da kake da shi, kuɗin tallace-tallace da ake sa rai, kashe-kashe, da buƙatar kuɗin kakar gaba tare da kuɗi da lokaci. Zan taimaka da lissafi mai sauƙi, ba shawarar bashi ko rance ba.",
        "fallback": "Ban gane ba. Amsa HELP don zaɓuɓɓuka, BUYER ko FARMER don zaɓar matsayi, ko LANGUAGE English/Yoruba/Igbo/French don canza harshe.",
        "text_only": "Aika saƙon rubutu don Allah. Idan hoto ko takarda ne, bayyana amfanin gona da abin da kake son dubawa. Ba zan iya duba hoto ba tukuna.",
        "stopped": "An cire ka daga saƙonnin mataimaki. Ba za a sake amsawa ba sai ka aika START.",
    },
    "yo": {
        "welcome": "Ẹ káàbọ̀ sí Gardenia. Dáhùn BUYER tàbí FARMER láti yan olùrànlọ́wọ́, tàbí HELP fún àṣàyàn. Èdè: Gẹ̀ẹ́sì, Hausa, Yorùbá, Igbo, Faransé. Lo LANGUAGE àti orúkọ èdè láti yí i padà.",
        "help": "Olùrà: SOURCE, REORDER, DEMAND, tàbí QUALITY. Àgbẹ̀: LISTING, PLANNER, PRICING, POST-HARVEST, tàbí FINANCE. Dáhùn BUYER tàbí FARMER láti yí ipa padà. Ìtọ́sọ́nà àpẹẹrẹ nìkan ni; a kò tíì so olùrànlọ́wọ́ WhatsApp yìí pọ̀ mọ́ ọjà tàbí àkọọ́lẹ̀ Gardenia rẹ.",
        "language": "A ti ṣètò èdè sí {language}. Lo LANGUAGE àti orúkọ èdè láti yí i padà.",
        "buyer": "A ti yan olùrànlọ́wọ́ olùrà. Dáhùn SOURCE fún ìtọ́sọ́nà rírà ọjà, REORDER fún ètò àtúnsàrà, DEMAND fún èrò ìbéèrè, tàbí QUALITY fún àkójọ ìṣàyẹ̀wò ọ̀tun. A kò tíì so ọjà tàbí ìtàn ìrà pọ̀.",
        "farmer": "A ti yan olùrànlọ́wọ́ àgbẹ̀. Dáhùn LISTING fún àpèjúwe ọjà, PLANNER fún ètò gbíngbin àti ìkórè, PRICING fún ìfiwéra owó, POST-HARVEST fún ìtọ́jú lẹ́yìn ìkórè, tàbí FINANCE fún ìṣirò owó.",
        "source": "Olùrànlọ́wọ́ rírà: fi ọjà, ìpele, iye àti ẹyọ rẹ̀, ibi ìfijiṣẹ́, àti ọjọ́ tí o fẹ́ ránṣẹ́. Mo lè ṣètò àkótán àìní, ṣùgbọ́n a kò tíì so ìwádìí ọjà Gardenia pọ̀.",
        "reorder": "Àtúnsàrà: fi ọjà, ọjọ́ àti iye ìrà tó kọjá, ọjà tó kù lọ́wọ́ rẹ, àti ìgbà tí o nílò sí i. Mo lè ràn ọ́ lọ́wọ́ láti ṣètò ìránnilétí; a kò so ìtàn ìrà Gardenia rẹ pọ̀.",
        "demand": "Ètò ìbéèrè: fi ọjà, iye títà tàbí lílò lọ́sọ̀ọ̀sẹ̀, àti àkókò ètò sílẹ̀. Mo lè ṣe àpẹẹrẹ, ṣùgbọ́n kò sí dátà títà Gardenia tàbí ti ọjà fún àsọtẹ́lẹ̀ gidi.",
        "quality": "Dídára àti ọ̀tun: fi ọjà, ọjọ́ ìkórè tàbí ìdìpọ̀, nọ́mbà ọ̀pọ̀, ipamọ́/ìrìnàjò, àti ẹ̀rí tó wà. Mo lè fún ọ ní àkójọ ìṣàyẹ̀wò, ṣùgbọ́n mi ò lè fìdí dídára múlẹ̀. Ayẹ̀wò onímọ̀ lè pọndandan.",
        "listing": "Olùrànlọ́wọ́ àkójọ ọjà: fi ohun ọ̀gbìn, iye àti ẹyọ, àlàyé dídára tó dájú, ibi gbígbà, àti owó tí o fẹ́ bí o bá mọ̀ ọ́. Màá kọ àpèjúwe fún àyẹ̀wò rẹ; mi ò ní tẹ̀ ẹ́ jáde.",
        "planner": "Ètò ìkórè: fi ohun ọ̀gbìn àti irú rẹ̀, ibi oko, ọjọ́ gbíngbin, àti ọjọ́ mélòó tí o retí kí ó tó dàgbà. Màá ṣe àkókò àfojúsùn; a kò ní dátà ojú ọjọ́ tàbí ìmọ̀ràn agbẹ̀gbìn agbègbè.",
        "pricing": "Ìmọ̀ràn owó: fi ọjà, dídára, ẹyọ, ibi, owó tí o fẹ́ àti owó àfiwé tuntun. Màá fi àwọn nọ́ńbà rẹ wé ara wọn; mi ò ní owó ọjà lọ́wọ́lọ́wọ́.",
        "postharvest": "Lẹ́yìn ìkórè: fi ohun ọ̀gbìn, ọjọ́ ìkórè, ohun tí o ṣàkíyèsí, àti bí o ṣe tọ́jú rẹ̀. Màá dábàá àwọn àyẹ̀wò gbogbogbòò, kì í ṣe àyẹ̀wò ìbàjẹ́ tàbí ìfọwọ́sí ààbò oúnjẹ. Tẹ̀lé ìmọ̀ràn agbẹ̀gbìn agbègbè.",
        "finance": "Owó oko: fi owó tó wà, títà tí o retí, ìnáwó iṣẹ́, àti owó àkókò tó ń bọ̀ pẹ̀lú irú owó àti àkókò. Màá ràn ọ́ lọ́wọ́ pẹ̀lú ìṣirò ìpìlẹ̀, kì í ṣe ìpinnu yá owó.",
        "fallback": "Mi ò lóye dáadáa. Dáhùn HELP fún àṣàyàn, BUYER tàbí FARMER láti yan ipa, tàbí LANGUAGE English/Hausa/Igbo/French láti yí èdè padà.",
        "text_only": "Jọ̀wọ́ fi ọ̀rọ̀ ránṣẹ́. Tí fọ́tò tàbí ìwé bá jẹ́, ṣàlàyé ohun ọ̀gbìn àti ohun tí o fẹ́ ṣàyẹ̀wò. Mi ò tíì lè ṣàyẹ̀wò àwòrán.",
        "stopped": "O ti jáde kúrò nínú ìdáhùn olùrànlọ́wọ́. Gardenia kò ní tún dáhùn títí o fi ránṣẹ́ START.",
    },
    "ig": {
        "welcome": "Nnọọ na Gardenia. Zaghachi BUYER ma ọ bụ FARMER ịhọrọ onye enyemaka, ma ọ bụ HELP ịhụ nhọrọ. Asụsụ: Bekee, Hausa, Yoruba, French, Igbo. Gbanwee asụsụ site na LANGUAGE na aha asụsụ.",
        "help": "Onye zụrụ: SOURCE, REORDER, DEMAND, ma ọ bụ QUALITY. Onye ọrụ ugbo: LISTING, PLANNER, PRICING, POST-HARVEST, ma ọ bụ FINANCE. Zaghachi BUYER ma ọ bụ FARMER ịgbanwe ọrụ. Nke a bụ ndụmọdụ ngosi; ejikọtaghị onye enyemaka WhatsApp a na ngwaahịa ma ọ bụ akaụntụ Gardenia gị.",
        "language": "Edobela asụsụ ka ọ bụrụ {language}. Jiri LANGUAGE na aha asụsụ gbanwee ya.",
        "buyer": "Ị họrọla onye enyemaka onye zụrụ. Zaghachi SOURCE maka enyemaka ịchọta ngwaahịa, REORDER maka atụmatụ ịzụrụ ọzọ, DEMAND maka atụmatụ mkpa, ma ọ bụ QUALITY maka ndepụta nyocha ịdị ọhụrụ. Ejikọtaghị ngwaahịa na akụkọ ịzụrụ gị.",
        "farmer": "Ị họrọla onye enyemaka onye ọrụ ugbo. Zaghachi LISTING maka ederede ngwaahịa, PLANNER maka atụmatụ ịkụ na iwe ihe ubi, PRICING maka atụnyere ọnụahịa, POST-HARVEST maka njikwa mgbe owuwe ihe ubi gasịrị, ma ọ bụ FINANCE maka mgbakọ ego.",
        "source": "Enyemaka ịchọta ngwaahịa: zipu ngwaahịa, ọkwa ịdị mma, ọnụọgụ na nha, ebe a ga-ebuga ya, na ụbọchị ịchọrọ ya. Enwere m ike ịhazi arịrịọ, mana ejikọtaghị ọchụchọ ahịa Gardenia.",
        "reorder": "Ịzụta ọzọ: zipu ngwaahịa, ụbọchị na ọnụọgụ ị zụtara ikpeazụ, ihe fọdụrụ ugbu a, na mgbe ịchọrọ ọzọ. Enwere m ike inyere aka hazie ncheta; ejikọtaghị akụkọ ịzụrụ Gardenia gị.",
        "demand": "Atụmatụ mkpa: zipu ngwaahịa, ire ma ọ bụ ojiji kwa izu n'oge gara aga, na oge atụmatụ. Enwere m ike ime atụ, mana data ahịa Gardenia ma ọ bụ ahịa adịghị maka amụma ziri ezi.",
        "quality": "Ịdị mma na ịdị ọhụrụ: zipu ngwaahịa, ụbọchị e wetara ma ọ bụ chịkọta ya, nọmba ogbe, ọnọdụ nchekwa/ụgbọ njem, na ihe akaebe dị. Enwere m ike inye ndepụta nyocha, mana enweghị m ike ịchọpụta ịdị mma. Nnyocha ọkachamara nwere ike ịdị mkpa.",
        "listing": "Onye enyemaka ndepụta: zipu ihe ubi/ngwaahịa, ọnụọgụ na nha, eziokwu gbasara ịdị mma, ebe a ga-eburu ya, na ọnụahịa gị ma ọ bụrụ na ị maara ya. Aga m depụta ederede ka ị nyochaa; agaghị m ebipụta ya.",
        "planner": "Atụmatụ owuwe ihe ubi: zipu ihe ubi na ụdị ya, ebe ugbo, ụbọchị ịkụ, na ụbọchị ole ọ na-ewe ka o tozuo dịka i chere. Aga m emepụta kalenda atụmatụ; ejikọtaghị ihu igwe ma ọ bụ ndụmọdụ ọrụ ugbo mpaghara.",
        "pricing": "Ndụmọdụ ọnụahịa: zipu ngwaahịa, ọkwa, nha, ebe, ọnụahịa ịchọrọ, na ọnụahịa ntụnyere ọhụrụ. Aga m atụnyere naanị ihe i nyere; enweghị m ọnụahịa ahịa dị ugbu a.",
        "postharvest": "Mgbe owuwe ihe ubi gasịrị: zipu ihe ubi, ụbọchị owuwe, ihe ị hụrụ, na ọnọdụ nchekwa. Aga m atụ aro nyocha izugbe, ọ bụghị ịchọpụta ire ere ma ọ bụ ikwenye nchekwa nri. Soro ndụmọdụ ọrụ ugbo mpaghara.",
        "finance": "Ego ugbo: zipu ego dị, ego ire ị na-atụ anya, ụgwọ ọrụ, na ego ịchọrọ maka oge ọzọ tinyere ego na oge. Enwere m ike inyere aka na mgbakọ dị mfe, ọ bụghị mkpebi ego mgbazinye.",
        "fallback": "Aghọtaghị m nke ọma. Zaghachi HELP maka nhọrọ, BUYER ma ọ bụ FARMER ịhọrọ ọrụ, ma ọ bụ LANGUAGE English/Hausa/Yoruba/French ịgbanwe asụsụ.",
        "text_only": "Biko zipu ozi ederede. Ọ bụrụ foto ma ọ bụ akwụkwọ, kọwaa ihe ubi na ihe ịchọrọ nyocha. Enweghị m ike ilele foto ugbu a.",
        "stopped": "Ị kwụsịla nnata nzaghachi onye enyemaka. Gardenia agaghị aza ọzọ ruo mgbe izipụrụ START.",
    },
    "fr": {
        "welcome": "Bienvenue sur Gardenia. Répondez BUYER ou FARMER pour choisir votre assistant, ou HELP pour voir les options. Langues disponibles : anglais, haoussa, yoruba, igbo, français. Pour changer, envoyez LANGUAGE suivi de la langue.",
        "help": "Acheteur : SOURCE, REORDER, DEMAND ou QUALITY. Agriculteur : LISTING, PLANNER, PRICING, POST-HARVEST ou FINANCE. Répondez BUYER ou FARMER pour changer de profil. Conseils de démonstration uniquement : cet assistant WhatsApp n'est pas encore relié aux annonces ou à votre compte Gardenia.",
        "language": "Langue réglée sur {language}. Envoyez LANGUAGE suivi du nom de la langue pour la modifier.",
        "buyer": "Assistant acheteur sélectionné. Demandez SOURCE pour rechercher un produit, REORDER pour planifier un réachat, DEMAND pour un scénario de demande, ou QUALITY pour une liste de contrôle. Les annonces et l'historique des commandes ne sont pas encore connectés.",
        "farmer": "Assistant agriculteur sélectionné. Demandez LISTING pour rédiger une annonce, PLANNER pour planifier semis et récolte, PRICING pour comparer des prix, POST-HARVEST pour les contrôles après récolte, ou FINANCE pour un calcul de trésorerie.",
        "source": "Sourcing : indiquez le produit, la qualité, la quantité et l'unité, le lieu de livraison et la date souhaitée. Je peux structurer votre demande, mais la recherche dans les annonces Gardenia n'est pas encore connectée.",
        "reorder": "Réapprovisionnement : indiquez le produit, la date et la quantité de la dernière commande, le stock actuel et la date du prochain besoin. Je peux créer une liste de rappel ; votre historique Gardenia n'est pas connecté.",
        "demand": "Prévision de la demande : indiquez le produit, les ventes ou usages hebdomadaires récents et l'horizon. Je peux proposer un scénario, mais aucune donnée de ventes Gardenia, saisonnière ou de marché n'est connectée.",
        "quality": "Qualité et fraîcheur : indiquez le produit, la date de récolte ou d'emballage, le lot, les conditions de stockage/transport et les preuves disponibles. Je peux suggérer des contrôles, pas vérifier la qualité. Une inspection ou analyse qualifiée peut être nécessaire.",
        "listing": "Assistant d'annonce : indiquez le produit, la quantité et l'unité, les caractéristiques de qualité vérifiées, le lieu de collecte et votre prix si vous le connaissez. Je peux rédiger un brouillon à vérifier ; je ne le publierai pas.",
        "planner": "Planification de récolte : indiquez la culture et la variété, le lieu, la date de plantation prévue et le délai estimé avant maturité. Je peux proposer un calendrier indicatif ; météo et conseil agricole local ne sont pas connectés.",
        "pricing": "Conseil tarifaire : indiquez le produit, la qualité, l'unité, le lieu, votre prix cible et un prix de référence récent comparable. Je compare vos données ; je ne dispose pas de prix de marché en direct.",
        "postharvest": "Après-récolte : indiquez la culture, la date de récolte, les symptômes ou problèmes et le stockage. Je peux proposer des contrôles généraux, pas diagnostiquer l'altération ni certifier la sécurité alimentaire. Suivez les conseils agricoles locaux.",
        "finance": "Finances agricoles : indiquez la trésorerie disponible, les ventes prévues, les coûts d'exploitation et le besoin pour le prochain cycle (devise et échéance). Je peux faire des calculs simples, pas décider d'un crédit ou d'un prêt.",
        "fallback": "Je n'ai pas compris. Répondez HELP pour le menu, BUYER ou FARMER pour choisir un profil, ou envoyez LANGUAGE English/Hausa/Yoruba/Igbo pour changer de langue.",
        "text_only": "Veuillez envoyer un message texte. Pour une photo ou un document, décrivez la culture et ce que vous souhaitez vérifier. L'assistant ne peut pas encore analyser les images.",
        "stopped": "Vous êtes désabonné. Gardenia ne répondra plus jusqu'à ce que vous envoyiez START.",
    },
}

LANGUAGE_TERMS = {
    "en": ("english", "anglais", "turanci"),
    "ha": ("hausa", "hausaa"),
    "yo": ("yoruba", "yorùbá", "yarbanci"),
    "ig": ("igbo", "ibo"),
    "fr": ("french", "français", "francais", "faransanci"),
}
LANGUAGE_HINTS = {
    "ha": ("sannu", "ina so", "manomi", "manoma", "noma", "farashi"),
    "yo": ("ẹ káàárọ̀", "e kaaro", "mo fẹ", "mo fe", "àgbẹ̀", "agbe", "irugbin", "owó"),
    "ig": ("ndewo", "achọrọ", "acho", "ọrụ ugbo", "ugbo", "ego", "onye ọrụ ugbo"),
    "fr": ("bonjour", "je veux", "je cherche", "agriculteur", "récolte", "prix", "acheteur"),
}
INTENT_TERMS = {
    "help": ("help", "menu", "aide", "aide-moi"),
    "buyer": ("buyer", "acheteur", "mai saye", "olùrà", "onye zụrụ"),
    "farmer": ("farmer", "seller", "agriculteur", "agriculteur", "manomi", "àgbẹ̀", "agbe", "ọrụ ugbo"),
    "source": ("source", "sourcing", "find", "buy", "product", "purchase", "rechercher", "cherche", "chercher", "achat", "produit", "nema", "saya", "ṣàwárí", "rírà"),
    "reorder": ("reorder", "re-order", "repeat", "réapprovisionnement", "racheter", "sake saya", "tun ra", "ịzụta ọzọ"),
    "demand": ("demand", "forecast", "forecasting", "prévision", "demande", "hasashe", "ìbéèrè", "amụma"),
    "quality": ("quality", "fresh", "freshness", "qualité", "fraîcheur", "sabo", "inganci", "dídára", "ịdị mma"),
    "listing": ("listing", "list", "advert", "annonce", "talla", "àkójọ", "ndepụta"),
    "planner": ("planner", "plant", "planting", "harvest", "planification", "planter", "récolte", "girbi", "shuka", "gbíngbin", "ìkórè", "ịkụ", "owuwe"),
    "pricing": ("pricing", "price", "prix", "farashi", "owó", "ọnụahịa"),
    "postharvest": ("post-harvest", "postharvest", "spoilage", "after harvest", "après-récolte", "après récolte", "bayan girbi", "lẹ́yìn ìkórè", "mgbe owuwe"),
    "finance": ("finance", "financial", "money", "cash", "finances", "trésorerie", "kuɗi", "owó oko", "ego ugbo"),
}


class LanguageStore:
    """Store preferences against a keyed identifier, never a raw phone number."""

    def __init__(self, database: str, hash_key: str):
        self.database = database
        self.hash_key = hash_key.encode("utf-8")
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS user_preferences (
                    user_key TEXT PRIMARY KEY,
                    language TEXT NOT NULL,
                    role TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    opted_out INTEGER NOT NULL DEFAULT 0
                )"""
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(user_preferences)")}
            if "opted_out" not in columns:
                connection.execute(
                    "ALTER TABLE user_preferences ADD COLUMN opted_out INTEGER NOT NULL DEFAULT 0"
                )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=5)

    def _key(self, user_id: str) -> str:
        return hmac.new(self.hash_key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()

    def get(self, user_id: str) -> tuple[str, str]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT language, role FROM user_preferences WHERE user_key = ?",
                (self._key(user_id),),
            ).fetchone()
        return (row[0], row[1]) if row else ("en", "")

    def set(self, user_id: str, language: str | None = None, role: str | None = None) -> None:
        old_language, old_role = self.get(user_id)
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO user_preferences (user_key, language, role, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_key) DO UPDATE SET
                     language = excluded.language,
                     role = excluded.role,
                     updated_at = excluded.updated_at""",
                (
                    self._key(user_id),
                    language or old_language,
                    role if role is not None else old_role,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def is_opted_out(self, user_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT opted_out FROM user_preferences WHERE user_key = ?",
                (self._key(user_id),),
            ).fetchone()
        return bool(row and row[0])

    def set_opted_out(self, user_id: str, opted_out: bool) -> None:
        old_language, old_role = self.get(user_id)
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO user_preferences (user_key, language, role, updated_at, opted_out)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_key) DO UPDATE SET
                     opted_out = excluded.opted_out,
                     updated_at = excluded.updated_at""",
                (
                    self._key(user_id),
                    old_language,
                    old_role,
                    datetime.now(timezone.utc).isoformat(),
                    int(opted_out),
                ),
            )
            connection.commit()


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def detect_language(text: str) -> str | None:
    normalized = normalize(text)
    for language in ("fr", "ha", "yo", "ig"):
        if any(term in normalized for term in LANGUAGE_HINTS[language]):
            return language
    return None


def requested_language(text: str) -> str | None:
    normalized = normalize(text)
    if not re.match(r"^(language|langue|harshe|èdè|asụsụ)\b", normalized):
        return None
    for language, terms in LANGUAGE_TERMS.items():
        if any(term in normalized for term in terms):
            return language
    return None


def find_intent(text: str) -> str | None:
    normalized = normalize(text)
    for intent, terms in INTENT_TERMS.items():
        if any(term in normalized for term in terms):
            return intent
    return None


def build_reply(text: str, language: str, role: str) -> tuple[str, str | None, str | None]:
    """Return reply, updated language (if explicitly changed), and updated role."""
    normalized = normalize(text)
    language_change = requested_language(text)
    if language_change:
        return TEXT[language_change]["language"].format(language=LANGUAGE_NAMES[language_change]), language_change, None

    detected = detect_language(text)
    if detected:
        language = detected

    intent = find_intent(text)
    if intent in ("buyer", "farmer"):
        role = intent
        return TEXT[language][intent], detected, role
    if intent == "help":
        return TEXT[language]["help"], detected, None

    farmer_intents = {"listing", "planner", "pricing", "postharvest", "finance"}
    buyer_intents = {"source", "reorder", "demand", "quality"}
    if intent in farmer_intents:
        role = "farmer"
        return TEXT[language][intent], detected, role
    if intent in buyer_intents:
        role = "buyer"
        return TEXT[language][intent], detected, role
    if not normalized:
        return TEXT[language]["welcome"], detected, None
    return TEXT[language]["fallback"], detected, None


def message_text(message: dict[str, Any]) -> str | None:
    if message.get("type") == "text":
        body = message.get("text", {}).get("body")
        return body if isinstance(body, str) else None
    interactive = message.get("interactive", {})
    for reply_type in ("button_reply", "list_reply"):
        reply = interactive.get(reply_type, {})
        body = reply.get("title") or reply.get("id")
        if isinstance(body, str):
            return body
    return None


def send_whatsapp_text(
    recipient: str,
    body: str,
    access_token: str,
    phone_number_id: str,
    graph_version: str,
    timeout: float = 10,
) -> None:
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": body[:4096]},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"WhatsApp API returned HTTP {response.status}")
    except urllib.error.HTTPError as error:
        LOG.error("WhatsApp send failed with HTTP %s", error.code)
        raise RuntimeError(f"WhatsApp API returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        LOG.error("WhatsApp send failed due to a network error")
        raise RuntimeError("WhatsApp API network request failed") from error


def create_handler(config: dict[str, str], store: LanguageStore, sender=send_whatsapp_text):
    class WebhookHandler(BaseHTTPRequestHandler):
        server_version = "GardeniaWhatsApp/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            LOG.info("Webhook request %s", self.command)

        def _respond(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] == "/healthz":
                self._respond(200, b"ok")
                return
            params = parse_qs(urlsplit(self.path).query)
            challenge = params.get("hub.challenge", [""])[0]
            valid = (
                params.get("hub.mode", [""])[0] == "subscribe"
                and secrets.compare_digest(params.get("hub.verify_token", [""])[0], config["verify_token"])
                and len(challenge) <= 512
            )
            self._respond(200 if valid else 403, challenge.encode("utf-8") if valid else b"forbidden")

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/webhook":
                self._respond(404, b"not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._respond(400, b"invalid content length")
                return
            if length <= 0 or length > 1_000_000:
                self._respond(413 if length > 1_000_000 else 400, b"invalid body size")
                return
            raw_body = self.rfile.read(length)
            signature = self.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(
                config["app_secret"].encode("utf-8"), raw_body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                self._respond(401, b"invalid signature")
                return
            try:
                payload = json.loads(raw_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._respond(400, b"invalid JSON")
                return
            self._respond(200, b"EVENT_RECEIVED")
            threading.Thread(target=self._process, args=(payload,), daemon=True).start()

        def _process(self, payload: dict[str, Any]) -> None:
            entries = payload.get("entry", [])
            if not isinstance(entries, list):
                return
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    metadata = value.get("metadata", {})
                    configured_phone_id = metadata.get("phone_number_id")
                    if configured_phone_id and configured_phone_id != config["phone_number_id"]:
                        LOG.warning("Ignoring webhook event for an unexpected phone number")
                        continue
                    messages = value.get("messages", [])
                    if not isinstance(messages, list):
                        continue
                    for message in messages:
                        recipient = message.get("from")
                        if not isinstance(recipient, str) or not recipient:
                            continue
                        text = message_text(message)
                        language, role = store.get(recipient)
                        normalized = normalize(text or "")
                        if normalized in ("stop", "unsubscribe"):
                            store.set_opted_out(recipient, True)
                            reply = TEXT[language]["stopped"]
                        elif store.is_opted_out(recipient):
                            if normalized != "start":
                                continue
                            store.set_opted_out(recipient, False)
                            reply = TEXT[language]["welcome"]
                        elif normalized == "start":
                            reply = TEXT[language]["welcome"]
                        elif text is None:
                            reply = TEXT[language]["text_only"]
                        else:
                            reply, updated_language, updated_role = build_reply(text, language, role)
                            if updated_language or updated_role is not None:
                                store.set(recipient, updated_language, updated_role)
                        try:
                            sender(
                                recipient,
                                reply,
                                config["access_token"],
                                config["phone_number_id"],
                                config["graph_version"],
                            )
                        except Exception:
                            LOG.exception("Unable to send WhatsApp reply")

    return WebhookHandler


def load_config() -> dict[str, str]:
    required = ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Set required environment variables: " + ", ".join(missing))
    return {
        "verify_token": os.environ["WHATSAPP_VERIFY_TOKEN"],
        "app_secret": os.environ["WHATSAPP_APP_SECRET"],
        "access_token": os.environ["WHATSAPP_ACCESS_TOKEN"],
        "phone_number_id": os.environ["WHATSAPP_PHONE_NUMBER_ID"],
        "graph_version": os.environ.get("WHATSAPP_GRAPH_VERSION", "v23.0"),
        "hash_key": os.environ.get("PREFERENCE_HASH_KEY", os.environ["WHATSAPP_APP_SECRET"]),
        "database": os.environ.get("PREFERENCES_DB", "data/whatsapp-preferences.sqlite3"),
        "host": os.environ.get("HOST", "127.0.0.1"),
        "port": os.environ.get("PORT", "8081"),
    }


def load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=value settings without overriding the process environment."""
    env_file = Path(path)
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name.replace("_", "a").isalnum():
            os.environ.setdefault(name, value)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_dotenv()
    config = load_config()
    store = LanguageStore(config["database"], config["hash_key"])
    server = ThreadingHTTPServer((config["host"], int(config["port"])), create_handler(config, store))
    LOG.info("WhatsApp webhook listening on %s:%s", config["host"], config["port"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Shutting down WhatsApp webhook")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
