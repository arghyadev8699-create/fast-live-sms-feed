import asyncio
import json
import logging
import os
import aiohttp
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ---------------------------------------------------------------------------
# Dynamic Environment Variables & Mapping Configuration
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKENS = [
    os.environ.get("TELEGRAM_BOT_TOKEN"),
    os.environ.get("TELEGRAM_BOT_TOKEN_2"),
    os.environ.get("TELEGRAM_BOT_TOKEN_3"),
    os.environ.get("TELEGRAM_BOT_TOKEN_4")
]

ACTIVE_BOT_TOKENS = [t.strip() for t in TELEGRAM_BOT_TOKENS if t and t.strip()]
MAIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "1"))
SEEN_IDS_FILE = "seen_sms_ids.json"
MAX_SEEN_IDS = 5000

# Parse dynamic TOKEN:Name mappings from Environment Variable
TOKEN_PANEL_MAP = {}
raw_tokens = os.environ.get("LAMIX_TOKEN", "").split(",")

for item in raw_tokens:
    item = item.strip()
    if not item:
        continue
    if ":" in item:
        token, name = item.split(":", 1)
        TOKEN_PANEL_MAP[token.strip()] = name.strip()
    else:
        TOKEN_PANEL_MAP[item] = "Agent Panel"

LAMIX_TOKENS = list(TOKEN_PANEL_MAP.keys())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

if not ACTIVE_BOT_TOKENS or not MAIN_CHAT_ID or not LAMIX_TOKENS:
    logger.error("প্রয়োজনীয় Environment Variables সঠিকভাবে সেট করা নেই!")
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
        # ১ম বার চালু হলে বিদ্যমান SMS স্ক্যান করে 'seen' হিসেবে মার্ক করা হচ্ছে (টেলিগ্রামে পাঠানো হবে না)
        logger.info("পুরানো SMS ডাটা স্ক্যান করে ব্যাকগ্রাউন্ডে নিস্ক্রিয় করা হচ্ছে...")
        sms_list = await fetch_all_messages(session)
        for sms in sms_list:
            if isinstance(sms, dict):
                number = str(sms.get("number") or "N/A")
                message_text = str(sms.get("content") or sms.get("message") or "")
                date_str = str(sms.get("time") or "N/A")
                panel_name = str(sms.get("_panel_name") or "Agent Panel")
                seen_sms_ids.add(f"{panel_name}_{number}_{message_text}_{date_str}")

        save_seen_ids(seen_sms_ids)
        logger.info("পুরানো OTP স্কিপ সম্পূর্ণ! এখন থেকে শুধুমাত্র নতুন (LIVE) OTP পাঠানো হবে।")

        while True:
            try:
                await process_sms(session)
            except Exception as e:
                logger.error(f"Main Loop Exception: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
