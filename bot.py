import asyncio
import json
import logging
import os
import aiohttp
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ---------------------------------------------------------------------------
# Configuration & Environment Variables
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKENS = [
    os.environ.get("TELEGRAM_BOT_TOKEN"),
    os.environ.get("TELEGRAM_BOT_TOKEN_2"),
    os.environ.get("TELEGRAM_BOT_TOKEN_3"),
    os.environ.get("TELEGRAM_BOT_TOKEN_4")
]

ACTIVE_BOT_TOKENS = [t.strip() for t in TELEGRAM_BOT_TOKENS if t and t.strip()]
MAIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TOKEN_PANEL_MAP = {
    # Original Active Tokens
    "C57kIlfs-FfhslhXZnaJiM8TD8bNIQ65VtXt0ah3-Nk": "Sadmanaldo",
    "5JhoHt02fHyADGx1-1eup1d80_M7OB1z3U9eUwqy3_Q": "Agent Panel",
    "yroBh9QlITbxBy10wysnXuT5cdm_K8ZnkpRrKRdLUlY": "Hamad Jam",
    "HV5GIhjqOz6MsBLYqYFlmv96iHkUG03vq3oydbFYyyc": "Adeel",
    "MhI0RN5zvkwWq47Bu-_N2eWM4qDuKB5PTGWgAeW74kM": "Inzamam",
    "bGBstGBsW-bjfD0ePkpZ_EpHess5onCOKjmTZICZ7Xo": "Malik Tubba",
    "wTsDRc7L_2JTb9a7deSYLrlOBHjm48z-wC5KepM1geU": "Ali Haider",
    "bjTk9YI17AulWdu8QVck5di1n1atRtXHDx6U_KNLfhY": "Iqra",
    "TkwW6fGU_guZRP9WGeVe_5s2iY9_l_MsvJmMrTDJnVw": "Shehraz",
    "_tEkas9jSEKRJ0fz3FbSl5Oh9w3J2k__ausvwouO51M": "Ikram",
    "vnrEuewqrI971B_8Es9g4s0nCTQk1irvAdQp9mGylqQ": "Raheel Bhutta",
    "W8ULKQBssbNofoSXlh0RMsPCYmdEMe1lMQcNuWXd68g": "Khalid",
    "H68v0LJ4ml5GCpiL6_HvQAeaB7HHqnfrIzCQfvAiGEA": "Ali nain",
    "ap1LzYsovP1mf1VN7Bb1y6i3X7u5kr1MMzZBsWtXm60": "K",
    
    # NEW Added Tokens
    "1a97dd85e7abfb93f5c54ca83185d08382cf0a86767f671227982a03e99fb01b": "Usman Baloch",
    "jM3NmxAshzg-YXUdSqaKqSNy-j57V12E2-qoToVgp6E": "Amir Jutt",
    "N2qbHY_60DJfNDoDoBNfblO2GpwxfMnoIG3zuCZJc9Q": "Khatoon",
    "ZJOhLnAGM175HA_Vj7aFp1RvKEFO5x6z_GvjfwLvRII": "Realistic",
    "2vnz7Ge6LVxQWdSZ2oxL8A8ROXzCIS0eZkGp93h0u-o": "Dr Abaido",
    "QC-DX5NF1lCyLhEc7ma6YOcln9VkS277bx05Lrm7irU": "Hashim",
    "Q26YYl5yg19UVYhCZlRvgHtshHpTknVfaGhyaFZScHw=": "Rashid",
}

env_tokens = [t.strip() for t in os.environ.get("LAMIX_TOKEN", "").split(",") if t.strip()]
LAMIX_TOKENS = list(set(env_tokens + list(TOKEN_PANEL_MAP.keys())))

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "1"))
SEEN_IDS_FILE = "seen_sms_ids.json"
MAX_SEEN_IDS = 5000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

if not ACTIVE_BOT_TOKENS or not MAIN_CHAT_ID or not LAMIX_TOKENS:
    logger.error("প্রয়োজনীয় Environment Variables সেট করা নেই!")
    raise SystemExit(1)

bots = [Bot(token=token) for token in ACTIVE_BOT_TOKENS]
bot_index = 0


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def load_seen_ids() -> set:
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            logger.error(f"seen_ids ফাইল লোড করতে সমস্যা: {e}")
    return set()


def save_seen_ids(seen_ids: set):
    try:
        if len(seen_ids) > MAX_SEEN_IDS:
            seen_ids = set(list(seen_ids)[-MAX_SEEN_IDS:])
        with open(SEEN_IDS_FILE, "w") as f:
            json.dump(list(seen_ids), f)
    except Exception as e:
        logger.error(f"seen_ids সেভ করতে সমস্যা: {e}")


seen_sms_ids: set = load_seen_ids()


def escape_markdown(text) -> str:
    if text is None:
        return ""
    special_chars = r"_*[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{ch}" if ch in special_chars else ch for ch in str(text))


# ---------------------------------------------------------------------------
# Fast Parallel Message Fetching
# ---------------------------------------------------------------------------
async def fetch_single_token_messages(session: aiohttp.ClientSession, token: str) -> list:
    panel_name = TOKEN_PANEL_MAP.get(token, "Agent Panel")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    url = "https://panel.lamix.org/api/v1/messages?limit=20"

    try:
        async with session.get(url, headers=headers, timeout=4) as response:
            if response.status == 200:
                data = await response.json() or {}
                records = data.get("records") or []
                for rec in records:
                    if isinstance(rec, dict):
                        rec["_panel_name"] = panel_name
                return records
    except Exception:
        pass
    return []


async def fetch_all_messages(session: aiohttp.ClientSession) -> list:
    tasks = [fetch_single_token_messages(session, token) for token in LAMIX_TOKENS]
    results = await asyncio.gather(*tasks)

    all_records = []
    for records in results:
        all_records.extend(records)
    return all_records


# ---------------------------------------------------------------------------
# OTP Processing & Sending
# ---------------------------------------------------------------------------
async def process_sms(session: aiohttp.ClientSession):
    global bot_index
    sms_list = await fetch_all_messages(session)

    for sms in reversed(sms_list):
        if not isinstance(sms, dict):
            continue

        number = str(sms.get("number") or "N/A")
        message_text = str(sms.get("content") or sms.get("message") or "")
        date_str = str(sms.get("time") or "N/A")
        cli_name = str(sms.get("cli") or "N/A")
        range_name = str(sms.get("range") or "N/A")
        panel_name = str(sms.get("_panel_name") or "Agent Panel")

        sms_key = f"{panel_name}_{number}_{message_text}_{date_str}"

        if sms_key in seen_sms_ids:
            continue

        # সুপার-ফাস্ট টেমপ্লেট
        telegram_msg = (
            f"⚡ *LIVE OTP RECEIVED* ⚡\n"
            f"👤 *Agent / Panel:* `{escape_markdown(panel_name)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 *CLI / Service:* `{escape_markdown(cli_name)}`\n"
            f"📱 *Number:* `{escape_markdown(number)}`\n"
            f"📡 *Range:* `{escape_markdown(range_name)}`\n"
            f"⏰ *Time:* `{escape_markdown(date_str)}`\n\n"
            f"💬 *SMS Content:*\n`{escape_markdown(message_text)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 *এই সার্ভিসটি বর্তমানে সচল আছে, সবাই ট্রাই করুন\\!*"
        )

        sent_successfully = False
        attempts = 0

        # মাল্টি-বোট ইনস্ট্যান্ট সুইচিং
        while not sent_successfully and attempts < len(bots):
            current_bot = bots[bot_index]
            used_bot_id = bot_index + 1
            bot_index = (bot_index + 1) % len(bots)
            attempts += 1

            try:
                await current_bot.send_message(
                    chat_id=MAIN_CHAT_ID,
                    text=telegram_msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                seen_sms_ids.add(sms_key)
                save_seen_ids(seen_sms_ids)
                logger.info(f"Instant OTP Sent via Bot #{used_bot_id}: {number} (Agent: {panel_name})")
                sent_successfully = True

            except TelegramError as e:
                logger.warning(f"Bot #{used_bot_id} Error: {e}. Switching to next bot...")

        if not sent_successfully:
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------------------------
async def main():
    logger.info(f"Bullet-Speed SMS Bot ({len(bots)} Active Bots) চালু হচ্ছে...")

    async with aiohttp.ClientSession() as session:
        logger.info("পুরানো SMS ডাটা স্ক্যান করে মেমরিতে নেওয়া হচ্ছে...")
        sms_list = await fetch_all_messages(session)
        for sms in sms_list:
            if isinstance(sms, dict):
                number = str(sms.get("number") or "N/A")
                message_text = str(sms.get("content") or "")
                date_str = str(sms.get("time") or "N/A")
                panel_name = str(sms.get("_panel_name") or "Agent Panel")
                seen_sms_ids.add(f"{panel_name}_{number}_{message_text}_{date_str}")

        save_seen_ids(seen_sms_ids)
        logger.info("আল্ট্রা-ফাস্ট লাইভ ট্র্যাকিং সম্পূর্ণ চালু হয়েছে!")

        while True:
            try:
                await process_sms(session)
            except Exception as e:
                logger.error(f"Main Loop Exception: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
