
# -*- coding: utf-8 -*-
"""
Env-based Telegram collector for image-only rental posts (Batumi focus).
Autodiscovery of channels via keywords, optional LLM (Ollama) normalization.
Outputs rows to `matches.csv` consumed by the Streamlit UI (`app/app.py`).

Python 3.10, Windows 10 tested. Configure via `.env` (see `.env.example`).

Comments/docstrings in EN, runtime messages in RU (user-facing).

MIT License.
"""
import os
import re
import csv
import json
import logging
import datetime as dt
from dataclasses import dataclass
from typing import List, Optional

import requests
from dotenv import load_dotenv
from telethon import TelegramClient, functions, types
from telethon.errors import RPCError, SessionPasswordNeededError
from telethon.tl.types import Channel, Message

# Env / config
load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or "0")
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE_NUMBER = os.getenv("TELEGRAM_PHONE", "")
SESSION = os.getenv("TELEGRAM_SESSION", "tg_rent_session")

USD_MIN = float(os.getenv("USD_MIN", "400"))
USD_MAX = float(os.getenv("USD_MAX", "500"))
GEL_PER_USD = float(os.getenv("GEL_PER_USD", "2.7"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
TERM_MIN_MONTHS = int(os.getenv("TERM_MIN_MONTHS", "6"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct")

CSV_PATH = "matches.csv"
LOG_LEVEL = logging.INFO

DISCOVER_KEYWORDS: List[str] = [
    "Аренда Батуми", "Квартиры Батуми", "Сдать снять Батуми",
    "Batumi rent", "Batumi apartments", "Batumi real estate",
    "ქირავდება ბათუმი", "ბინების გაქირავება ბათუმში",
]
DISCOVER_LIMIT_PER_QUERY = 30
DISCOVER_MIN_SUBS = 300
DISCOVER_MAX_CHANNELS = 40

OUT_OF_BATUMI = [
    "махинджаури","мaхинджаури","მახინჯაური","gonio","гонио","გონიო","квариати","kvariati",
    "сарпи","sarpi","чакви","chakvi","зеленый мыс","mtsvane","მცვანე","mtsvane kontskhi",
    "кобулети","kobulet","ქობულეთი","kobuleti","khelvachauri","ხელვაჩაური",
]
EXCLUDE_BUILDINGS = ["magnolia","магнолия","alliance magnolia","альянс магнолия"]
PRIORITY_STREETS = [
    "инасеридзе","inasaridze","ინასარიძე",
    "kobaladze","кобаладзе","კობалაძე",
    "angisa","ангиса","ანგის",
    "agmashenebeli","агмашенебели",
    "vox","вокс","grand mall","metro city","метро сити",
]

UTC = dt.timezone.utc
TBILISI_TZ = dt.timezone(dt.timedelta(hours=4))

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("collector")

@dataclass
class Listing:
    channel: str
    url: Optional[str]
    message_id: int
    date_local: str
    price_usd: float
    score: int
    text: str

EMOJI_DIGITS = {"0️⃣":"0","1️⃣":"1","2️⃣":"2","3️⃣":"3","4️⃣":"4","5️⃣":"5","6️⃣":"6","7️⃣":"7","8️⃣":"8","9️⃣":"9"}

def _norm_nums_currency(text: str) -> str:
    import unicodedata
    s = text
    for emo, d in EMOJI_DIGITS.items():
        s = s.replace(emo, d)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("💵"," $ ").replace("💲"," $ ").replace("₾"," GEL ")
    return s

def _norm_text(t: str) -> str:
    s = t.lower()
    s = s.replace("х","x").replace("×","x").replace("•","+")
    s = re.sub(r"\s*([x+])\s*","+ ", s)
    s = re.sub(r"[^\w+#\s-]"," ", s)
    s = re.sub(r"\s+"," ", s).strip()
    return s

def _has_one_plus_one(text: str) -> bool:
    return "1+1" in _norm_text(text)

def _explicit_three_room(text: str) -> bool:
    s = _norm_text(text)
    return bool(re.search(r"\b(тр[её]хкомнат\w*|3-?комнат\w*|\b3к\b|\b3-к\b|\b3\s*room\b|\b3br\b)", s))

def _explicit_two_bed(text: str) -> bool:
    s = _norm_text(text)
    if re.search(r"двуспальн\w+\s+кроват", s):
        return False
    return _explicit_three_room(s) or bool(re.search(r"\b(2\s*спальн\w*|две\s*спальн\w*|2\s*bed(room)?s?)\b", s))

def _detect_daily(text: str) -> bool:
    s = _norm_text(text)
    return bool(re.search(r"\b(сутк|посуточ|per\s*day|daily|ноч[ьи]|за\s*день)\b", s))

def _mentions(tokens: List[str], text: str) -> bool:
    s = text.lower()
    return any(tok in s for tok in tokens)

def _extract_price_usd(text: str) -> Optional[float]:
    t = _norm_nums_currency(text)
    m = re.search(r"(\d[\d \u00A0]{1,6}(?:[.,]\d{1,2})?)\s*(?:\$|usd)\b", t, flags=re.I)
    if m:
        v = float(m.group(1).replace(" ","").replace("\u00A0","").replace(",","."))
        return round(v, 2)
    m = re.search(r"(\d[\d \u00A0]{1,6}(?:[.,]\d{1,2})?)\s*(?:gel|lari|лари|ლ)\b", t, flags=re.I)
    if m:
        v = float(m.group(1).replace(" ","").replace("\u00A0","").replace(",","."))
        return round(v / GEL_PER_USD, 2)
    return None

def _first_json_object(s: str) -> Optional[str]:
    depth = 0; start = -1
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    return s[start:i+1]
    return None

def llm_extract(text: str) -> Optional[dict]:
    if LLM_PROVIDER != "ollama":
        return None
    schema = {
        "accept": False, "reason": "", "price_value": None, "price_currency": "USD", "price_usd": None,
        "period": "unknown", "term_months": None, "bedrooms_count": None, "two_separate_bedrooms": None,
        "inner_bedroom": False, "is_magnolia": False, "excluded_location": False, "priority_bonus": 0, "score_10": 0
    }
    prompt = f"""
Strict selection for long-term rent in Batumi (LLM-only). Output ONE-LINE MINIFIED JSON with EXACT keys:
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
NEVER accept: price_usd > {USD_MAX}, студия/studio, daily/сутки, Magnolia, outside Batumi,
"1+1" (ONE bedroom), 2к unless EXPLICIT "2 спальни"/"two bedrooms".
ACCEPT only if: period="month", {USD_MIN} ≤ price_usd ≤ {USD_MAX}, bedrooms_count ≥ 2, no inner bedroom,
excluded_location=false, is_magnolia=false, (term_months is null or ≥ {TERM_MIN_MONTHS}).
Reason must be short Russian. Output ONE minified JSON only.
Text:
{text[:6000]}
""".strip()
    try:
        r = requests.post(
            OLLAMA_URL,
            headers={"Content-Type":"application/json"},
            data=json.dumps({
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role":"system","content":"Ты детерминированный экстрактор JSON. Отдавай ровно ОДИН minified JSON."},
                    {"role":"user","content": prompt},
                ],
                "options":{"temperature":0,"num_ctx":4096},
                "stream": False,
            }),
            timeout=30,
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
        blob = _first_json_object(content) or content
        data = json.loads(blob.strip())
        if data.get("price_usd") is None and isinstance(data.get("price_value"), (int,float)):
            cur = (data.get("price_currency") or "USD").upper()
            val = float(data["price_value"])
            data["price_usd"] = val if cur == "USD" else round(val / GEL_PER_USD, 2)
        return data
    except Exception as e:
        log.debug(f"LLM skip: {e}")
        return None

def _ensure_csv_header(path: str) -> None:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["match_type","channel","message_id","date_local","price_usd","score","url","text"])

def _append_csv_row(path: str, entry: "Listing") -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            "strict", entry.channel, entry.message_id, entry.date_local,
            entry.price_usd, entry.score, entry.url or "", entry.text.replace("\n"," ")[:1800]
        ])

async def discover_channels(client: TelegramClient) -> List[Channel]:
    found = {}
    for kw in DISCOVER_KEYWORDS:
        try:
            res = await client(functions.contacts.SearchRequest(q=kw, limit=DISCOVER_LIMIT_PER_QUERY))
        except RPCError as e:
            log.warning(f"Поиск по '{kw}' упал: {e}")
            continue
        for ch in res.chats:
            if not isinstance(ch, Channel):
                continue
            try:
                full = await client(functions.channels.GetFullChannelRequest(channel=types.InputChannel(ch.id, ch.access_hash)))
                subs = getattr(full.full_chat, "participants_count", 0) or 0
            except RPCError:
                subs = 0
            if subs >= DISCOVER_MIN_SUBS:
                found[ch.id] = ch
        if len(found) >= DISCOVER_MAX_CHANNELS:
            break
    selected = list(found.values())[:DISCOVER_MAX_CHANNELS]
    log.info(f"Дискавер: выбрано каналов = {len(selected)} (мин. подписчиков: {DISCOVER_MIN_SUBС})")
    return selected

async def collect(client: TelegramClient) -> None:
    cutoff = dt.datetime.now(UTC) - dt.timedelta(days=LOOKBACK_DAYS)
    _ensure_csv_header(CSV_PATH)
    channels = await discover_channels(client)

    log.info(f"Сбор из {len(channels)} каналов, период {LOOKBACK_DAYS}д, только посты с фото")
    for ch in channels:
        title = getattr(ch, "username", None) or getattr(ch, "title","") or str(getattr(ch, "id",""))
        processed = kept = 0

        async for msg in client.iter_messages(ch, limit=1200):
            if not isinstance(msg, Message) or not getattr(msg, "date", None):
                continue

            msg_dt = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC)
            if msg_dt.astimezone(UTC) < cutoff:
                break

            if not getattr(msg, "photo", None):
                continue

            text = (getattr(msg, "message", None) or "").strip()
            if not text:
                continue

            processed += 1

            dec = llm_extract(text) or {}
            if not isinstance(dec.get("price_usd"), (int,float)):
                p = _extract_price_usd(text)
                if p is not None:
                    dec["price_usd"] = p

            accept = True
            s = text.lower()
            if _has_one_plus_one(text): accept = False
            if _detect_daily(text): accept = False
            if _mentions(OUT_OF_BATUMI, text): accept = False
            if _mentions(EXCLUDE_BUILDINGS, text): accept = False
            if not _explicit_two_bed(text): accept = False

            pr = dec.get("price_usd")
            if not (isinstance(pr,(int,float)) and USD_MIN <= pr <= USD_MAX):
                accept = False

            if not accept:
                continue

            score = int(dec.get("score_10") or 5)
            if any(p in s for p in PRIORITY_STREETS):
                score = min(10, score + 1)

            username = getattr(ch, "username", None)
            url = f"https://t.me/{username}/{msg.id}" if username else None

            entry = Listing(
                channel=title,
                url=url,
                message_id=msg.id,
                date_local=msg_dt.astimezone(TBILISI_TZ).strftime("%Y-%m-%d %H:%M"),
                price_usd=float(dec.get("price_usd") or 0.0),
                score=score,
                text=text,
            )
            _append_csv_row(CSV_PATH, entry)
            kept += 1

        log.info(f"Канал: {title} | обработано={processed}, прошло фильтр={kept}")

    log.info("Готово. Результат в matches.csv")

def main():
    if not API_ID or not API_HASH or not PHONE_NUMBER:
        log.error("Заполни TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_PHONE в .env")
        return

    client = TelegramClient(SESSION, API_ID, API_HASH)

    import asyncio
    async def run():
        await client.connect()
        if not await client.is_user_authorized():
            log.info("Нужна авторизация → отправляю код")
            await client.send_code_request(PHONE_NUMBER)
            code = input("Код из Telegram: ")
            try:
                await client.sign_in(PHONE_NUMBER, code)
            except SessionPasswordNeededError:
                pwd = input("Пароль двухэтапной аутентификации: ")
                await client.sign_in(password=pwd)
        try:
            await collect(client)
        finally:
            await client.disconnect()

    asyncio.run(run())

if __name__ == "__main__":
    main()
