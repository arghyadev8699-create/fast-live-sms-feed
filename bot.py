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
SPECIAL_USER_CHAT_ID = "-1004438427872"
TARGET_USERNAME = "O2Cshahnaz"

TOKEN_PANEL_MAP = {
    "C57kIlfs-FfhslhXZnaJiM8TD8bNIQ65VtXt0ah3-Nk": "Sadmanaldo258",
    "5JhoHt02fHyADGx1-1eup1d80_M7OB1z3U9eUwqy3_Q": "Agent Panel",
    "NY8kOw3mJ023jK0fh3hz6Fb500uSvgJEfFOX4-y8MQI": "Dr Abadu",
    "yroBh9QlITbxBy10wysnXuT5cdm_K8ZnkpRrKRdLUlY": "Hamad Jam",
    "HxldZrjvOfQ0UR5x6WUWaVmipistiDwxmhPHRcjX1pM": "Amir Jutt",
    "HV5GIhjqOz6MsBLYqYFlmv96iHkUG03vq3oydbFYyyc": "Adeel",
    "MhI0RN5zvkwWq47Bu-_N2eWM4qDuKB5PTGWgAeW74kM": "Inzamam",
    "bGBstGBsW-bjfD0ePkpZ_EpHess5onCOKjmTZICZ7Xo": "Malik tubba",
    "wTsDRc7L_2JTb9a7deSYLrlOBHjm48z-wC5KepM1geU": "Ali Haider",
    "bjTk9YI17AulWdu8QVck5di1n1atRtXHDx6U_KNLfhY": "Iqra",
    "TkwW6fGU_guZRP9WGeVe_5s2iY9_l_MsvJmMrTDJnVw": "Shehraz",
    "_tEkas9jSEKRJ0fz3FbSl5Oh9w3J2k__ausvwouO51M": "Ikram",
    "vnrEuewqrI971B_8Es9g4s0nCTQk1irvAdQp9mGylqQ": "Raheel bhutta",
    "W8ULKQBssbNofoSXlh0RMsPCYmdEMe1lMQcNuWXd68g": "Khalid",
    "S_Ynb1Q3SEu_45Y0qZaUSr6zppBTureLSvRcgxW_yJQ": "Khatoon",
    "H68v0LJ4ml5GCpiL6_HvQAeaB7HHqnfrIzCQfvAiGEA": "Ali nain",
    "ap1LzYsovP1mf1VN7Bb1y6i3X7u5kr1MMzZBsWtXm60": "K",
}

env_tokens = [t.strip() for t in os.environ.get("LAMIX_TOKEN", "").split(",") if t.strip()]
LAMIX_TOKENS = list(set(env_tokens + list(TOKEN_PANEL_MAP.keys())))

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
SEEN_IDS_FILE = "seen_sms_ids.json"
MAX_SEEN_IDS = 5000

NUMBER_CLIENT_MAP = {}
PANEL_TOKEN_MAP = {v: k for k, v in TOKEN_PANEL_MAP.items()}

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
# Complete Number-User Syncing Logic
# ---------------------------------------------------------------------------
async def sync_single_token_numbers(session: aiohttp.ClientSession, token: str):
    """একটি প্যানেলের সমস্ত পেজ ঘুরে সম্পূর্ণ নম্বর এবং ক্লায়েন্ট লিস্ট ডাউনলোড করা"""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = "https://panel.lamix.org/api/v1/numbers?limit=500"
    
    while url:
        try:
            async with session.get(url, headers=headers, timeout=12) as res:
                if res.status == 200:
                    data = await res.json() or {}
                    records = data.get("records") or []
                    for item in records:
                        if isinstance(item, dict):
                            num = item.get("number")
                            client = item.get("client") or item.get("username") or item.get("user") or "Unassigned"
                            if num:
                                NUMBER_CLIENT_MAP[str(num)] = str(client)

                    next_cursor = data.get("nextCursor")
                    url = f"https://panel.lamix.org/api/v1/numbers?limit=500&after={next_cursor}" if next_cursor else None
                elif res.status == 429:
                    await asyncio.sleep(2)
                else:
                    url = None
        except Exception:
            url = None
        await asyncio.sleep(0.1)


async def sync_all_numbers(session: aiohttp.ClientSession):
    """১৭টি প্যানেলের সমস্ত নম্বর একসাথে সিঙ্ক করা"""
    tasks = [sync_single_token_numbers(session, token) for token in LAMIX_TOKENS]
    await asyncio.gather(*tasks)


async def sync_number_clients_periodically(session: aiohttp.ClientSession):
    """প্রতি ৩০ সেকেন্ডে ব্যাকগ্রাউন্ডে ইউজারনেম লিস্ট সম্পূর্ণ সিঙ্ক হবে"""
    while True:
        try:
            await sync_all_numbers(session)
        except Exception as e:
            logger.warning(f"Number sync error: {e}")
        await asyncio.sleep(30)


async def fetch_single_number_user(session: aiohttp.ClientSession, panel_name: str, number: str) -> str:
    """জরুরি ক্ষেত্রে একক মোবাইল নম্বরের ইউজারনেম রি-ফ্যাচ করা"""
    token = PANEL_TOKEN_MAP.get(panel_name)
    if not token:
        return "Unassigned"
    
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://panel.lamix.org/api/v1/numbers?number={number}"
    
    try:
        async with session.get(url, headers=headers, timeout=5) as res:
            if res.status == 200:
                data = await res.json() or {}
                records = data.get("records") or []
                if records and isinstance(records[0], dict):
                    client = records[0].get("client") or records[0].get("username") or "Unassigned"
                    NUMBER_CLIENT_MAP[str(number)] = str(client)
                    return str(client)
    except Exception:
        pass
    return "Unassigned"


# ---------------------------------------------------------------------------
# Message Fetching & Multi-Bot OTP Processing
# ---------------------------------------------------------------------------
async def fetch_single_token_messages(session: aiohttp.ClientSession, token: str) -> list:
    panel_name = TOKEN_PANEL_MAP.get(token, "Sadmanaldo258")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    url = "https://panel.lamix.org/api/v1/messages?limit=50"

    try:
        async with session.get(url, headers=headers, timeout=6) as response:
            if response.status == 200:
                data = await response.json() or {}
                records = data.get("records") or []
                for rec in records:
                    if isinstance(rec, dict):
                        rec["_panel_name"] = panel_name
                return records
            elif response.status == 429:
                await asyncio.sleep(2)
    except Exception as e:
        logger.warning(f"Fetch Error ({panel_name}): {e}")
    return []


async def fetch_all_messages(session: aiohttp.ClientSession) -> list:
    tasks = [fetch_single_token_messages(session, token) for token in LAMIX_TOKENS]
    results = await asyncio.gather(*tasks)

    all_records = []
    for records in results:
        all_records.extend(records)
    return all_records


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
        panel_name = str(sms.get("_panel_name") or "Sadmanaldo258")

        # মেমরিতে ইউজারনেম না থাকলে রিয়েল-টাইমে লাইভ রি-ফ্যাচ করা
        username = NUMBER_CLIENT_MAP.get(number)
        if not username or username == "Unassigned":
            username = await fetch_single_number_user(session, panel_name, number)

        sms_key = f"{panel_name}_{number}_{message_text}_{date_str}"

        if sms_key in seen_sms_ids:
            continue

        if TARGET_USERNAME.lower() in username.lower():
            target_chat_id = SPECIAL_USER_CHAT_ID
        else:
            target_chat_id = MAIN_CHAT_ID

        telegram_msg = (
            f"⚡ *LIVE OTP RECEIVED* ⚡\n"
            f"👤 *Panel:* {escape_markdown(panel_name)}\n"
            f"👤 *User:* `{escape_markdown(username)}`\n"
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

        while not sent_successfully and attempts < len(bots):
            current_bot = bots[bot_index]
            used_bot_id = bot_index + 1
            bot_index = (bot_index + 1) % len(bots)
            attempts += 1

            try:
                await current_bot.send_message(
                    chat_id=target_chat_id,
                    text=telegram_msg,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                seen_sms_ids.add(sms_key)
                save_seen_ids(seen_sms_ids)
                logger.info(f"OTP Sent via Bot #{used_bot_id}: {number} -> User: {username}")
                sent_successfully = True
                await asyncio.sleep(0.1)

            except TelegramError as e:
                logger.warning(f"Bot #{used_bot_id} Failed: {e}. Switching bot...")

        if not sent_successfully:
            await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Main Execution Flow
# ---------------------------------------------------------------------------
async def main():
    logger.info(f"SMS Feed Bot ({len(bots)} Active Bots) চালু হচ্ছে...")

    async with aiohttp.ClientSession() as session:
        # ১. আগে সব ইউজারনেম ও নম্বরের তথ্য ডাউনলোড না হওয়া পর্যন্ত বোট ওটিপি পাঠাবে না
        logger.info("প্যানেল থেকে সমস্ত নম্বর ও ইউজারনেম ডাউনলোড করে মেমরিতে সেভ করা হচ্ছে...")
        await sync_all_numbers(session)
        logger.info(f"সফলভাবে {len(NUMBER_CLIENT_MAP)} টি নম্বরের ইউজারনেম মেমরিতে সিঙ্ক হয়েছে!")

        # ২. ব্যাকগ্রাউন্ডে পিরিওডিক সিঙ্ক চালু করা
        asyncio.create_task(sync_number_clients_periodically(session))

        # ৩. পুরানো ওটিপি স্ক্যান করে ইগনোর করা
        logger.info("প্রথমবার পুরানো SMS ডাটা স্ক্যান করে মেমরিতে নেওয়া হচ্ছে...")
        sms_list = await fetch_all_messages(session)
        for sms in sms_list:
            if isinstance(sms, dict):
                number = str(sms.get("number") or "N/A")
                message_text = str(sms.get("content") or "")
                date_str = str(sms.get("time") or "N/A")
                panel_name = str(sms.get("_panel_name") or "Sadmanaldo258")
                seen_sms_ids.add(f"{panel_name}_{number}_{message_text}_{date_str}")

        save_seen_ids(seen_sms_ids)
        logger.info("লাইভ ট্র্যাকিং সম্পূর্ণ রেডি এবং চালু হয়েছে!")

        while True:
            try:
                await process_sms(session)
            except Exception as e:
                logger.error(f"Main Loop Exception: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
