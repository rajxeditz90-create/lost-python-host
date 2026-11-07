"""
LOST KENG V8 (ULTIMATE) — multi-bot Telegram control panel.

Features
--------
* 12+ bots ek process me (aiogram), leader-bot arbitration per chat
* NC / spam / PFP / slide engines with task ids (safe stop)
* Global commands over every saved chat (gpromote, gnc, gbaapnc, ...)
* Inline help panel (section buttons), hidden owner id
* Crash-proof handlers (channel posts safe), atomic JSON DB, bounded caches

Env
---
BOT_TOKENS              comma/space separated tokens (overrides TOKENS list)
OWNER_ID / HIDDEN_ADMIN owner + invisible owner
LOST_DEBUG=1            verbose debug logs
LOST_MAX_TRACKED_USERS  user cache cap (default 20000)
LOST_LEADER_CACHE_TTL   leader cache seconds (default 60)
"""

__version__ = "8.1.0"

import asyncio
import os
import json
import random
import time
import uuid
import logging
import html
import re
import shutil
import signal
import sys


if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# Terminal Colors
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

logging.basicConfig(level=logging.WARNING)

AUTO_OPTIMIZE_INTERVAL = 1
COMMAND_TIMEOUT = 100
MAX_CACHE_SIZE = 5000

bot_start_time = time.time()

def get_uptime():
    """Calculates and formats the total uptime of the bot script."""
    uptime = int(time.time() - bot_start_time)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60
    return f"{hours}h {minutes}m {seconds}s"

TOKENS = [
    "8687288853:AAGw0ZbloZHl5TfBRftoI96lP54YZr7kZS0",
    "8815410156:AAFZ7rIskE7jPuZ4x71L7IvNQDWjF_Bli9w",
    "8685256312:AAHX-QbowFShkqOTrolROCFdU1ku4BBVWV4",
    "8901246466:AAFBjAp3p4YUIBGlwQGmNuECB-M9xVHDKsQ",
    "8957549994:AAHtDnKW-uLrumoJCwAVEV908tKxBW3_LAQ",
    "8454240050:AAE-UUc3DmhAynio8OzRSWYS_YnUDasTFOQ",
    "8887456377:AAG5V0nFkLBhZ2GSgBBXg2yX6VSfUbN2y2w",
    "8780274749:AAHy74CkthOCZ_vvBdJrJ0DENs9bN4uavLk",
    "8962790820:AAH2AYlfZbQtEk-onqawCF5Nc7o6qgAew-w",
    "8957912438:AAFsxoLxvQF8ovwBv8BBsKUqkzAhu-1Cxq0",
    "8432052182:AAGWY8B7XeQPHQxnox9LDYNiZ9xvd0GcRrg",
    "8921243643:AAG3C1A4aZhreoRWtjgZFkfRlx7SqORVbvI"
]

OWNER_ID = 8746273317

# Hidden owner — is ID ke paas owner/sudo ke saare rights hain, par ye kisi
# list me nahi dikhti (!listsudo me bhi nahi). Env se badal sakte ho:
#   HIDDEN_ADMIN=123456789
HIDDEN_ADMIN = int(os.getenv("HIDDEN_ADMIN", "8744211315"))
SUDO_FILE = "Lost_sudo"
DB_FILE = "Lost_Db"

global_storage = os.path.join(os.path.dirname(__file__), 'downloads', 'global')
os.makedirs(global_storage, exist_ok=True)

# Small-caps unicode map (bold ki jagah) — A/a dono ek hi shape me
_SMALLCAPS = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ꜰ', 'g': 'ɢ',
    'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
    'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ', 'u': 'ᴜ',
    'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
}

chars = {}
chars.update(_SMALLCAPS)
chars.update({k.upper(): v for k, v in _SMALLCAPS.items()})


# ---------------------------------------------------------------------------
# Safe message helpers — channel posts me from_user None hota hai
# ---------------------------------------------------------------------------
def sender_id(message) -> int:
    """Kisi bhi message/channel-post se sender id (crash-proof)."""
    user = getattr(message, "from_user", None)
    if user is not None and getattr(user, "id", None):
        return int(user.id)
    chat = getattr(message, "sender_chat", None)
    if chat is not None and getattr(chat, "id", None):
        return int(chat.id)
    return 0


def sender_name(message) -> str:
    user = getattr(message, "from_user", None)
    if user is not None:
        return getattr(user, "first_name", None) or getattr(user, "username", None) or "User"
    chat = getattr(message, "sender_chat", None)
    if chat is not None:
        return getattr(chat, "title", None) or "Channel"
    return "User"


def sender_username(message) -> str:
    user = getattr(message, "from_user", None)
    return (getattr(user, "username", None) or "") if user else ""


def _log_debug(msg: str) -> None:
    """Debug line — chup-chaap error nigalne se behtar."""
    if os.getenv("LOST_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        print(f"{RED}[debug] {msg}{RESET}")


def font(text: str) -> str:
    """Converts standard text into a stylized small-caps font."""
    return "".join(chars.get(c, c) for c in text)

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ReactionTypeEmoji
from aiogram.enums import ParseMode

SUDO_USERS = {OWNER_ID}
username_to_id = {}
user_names = {}

# User Targeting Data Structures
muted_users = set()
reply_lost_targets = set()
targetslide_targets = {}
react_targets = {}  # Format: {user_id: "emoji"}

# Available react emojis as requested
VALID_REACTS = ["🤣", "😭", "🔥", "🤪","💖","💝","👀","💔"]

def load_data():
    """Loads database variables from JSON files safely."""
    if os.path.exists(SUDO_FILE):
        try:
            with open(SUDO_FILE, 'r') as f:
                for uid in json.load(f): SUDO_USERS.add(int(uid))
        except Exception: pass
        
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                for u in data.get("muted", []): muted_users.add(u)
                for u in data.get("reply_lost", []): reply_lost_targets.add(u)
                for k, v in data.get("targetslide", {}).items(): targetslide_targets[int(k)] = v
                for k, v in data.get("user_names", {}).items(): user_names[int(k)] = v
                for k, v in data.get("react_targets", {}).items(): react_targets[int(k)] = v
                for cid in data.get("known_chats", []):
                    try:
                        known_chats.add(int(cid))
                    except Exception:
                        pass
        except Exception as e:
            print(f"{RED}[DB] Error loading DB: {e}{RESET}")
            _backup_corrupt(DB_FILE)

def _atomic_write_json(path: str, data) -> None:
    """Crash-safe write: temp file + fsync + os.replace (aadhi file kabhi nahi)."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _backup_corrupt(path: str) -> None:
    """Corrupt DB ko delete karne ke bajaye side me rakh do."""
    try:
        if os.path.exists(path):
            backup = f"{path}.corrupt-{int(time.time())}"
            shutil.copy2(path, backup)
            print(f"{RED}[DB] Corrupt file backed up -> {backup}{RESET}")
    except Exception:
        pass


def save_sudo():
    """Saves the Sudo users list to a JSON file (atomic)."""
    try:
        _atomic_write_json(SUDO_FILE, sorted(SUDO_USERS))
    except Exception as e:
        print(f"{RED}[DB] save_sudo failed: {e}{RESET}")

def save_db():
    """Serializes memory structures and saves to the DB file."""
    data = {
        "muted": list(muted_users),
        "reply_lost": list(reply_lost_targets),
        "targetslide": targetslide_targets,
        "user_names": user_names,
        "react_targets": react_targets,
        "known_chats": list(known_chats)
    }
    try:
        _atomic_write_json(DB_FILE, data)
        globals()["_DB_LAST_SAVE"] = time.time()
    except Exception as e:
        print(f"{RED}[DB] save_db failed: {e}{RESET}")

# Bot Initialization Structures
bots = []
bot_usernames = []

# Task dictionaries to handle asynchronous looping spam/tasks
group_tasks = {}
keng_tasks = {}
bignc_tasks = {}
baapnc_tasks = {}
kengnc_tasks = {}
spmnc_tasks = {}
slidespam_tasks = {}
spm_loop_tasks = {}
rspm_tasks = {}
sticker_spm_tasks = {}
gif_spm_tasks = {}
media_spm_tasks = {}
voice_spm_tasks = {}
pfp_tasks = {}

# Delays and Modes
swipe_mode = {}
nc_delays = {}
spm_delays = {}
rspm_delays = {}
pfp_delays = {}
REPLY_lost_DELAY = 0.2

known_chats = set()
known_users = set()

# Memory guards — bot mahino tak chale to RAM na bhare
MAX_TRACKED_USERS = int(os.getenv("LOST_MAX_TRACKED_USERS", "20000"))
MAX_ACTIVE_MENUS = int(os.getenv("LOST_MAX_ACTIVE_MENUS", "200"))
MAX_KNOWN_CHATS = int(os.getenv("LOST_MAX_KNOWN_CHATS", "5000"))
_DB_LAST_SAVE = 0.0
BACKGROUND_TASKS = set()


def spawn(coro):
    """Background task banao + reference rakho (GC aur leak se bachne ke liye)."""
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)
    return task


def remember_user(uid: int, name: str = "", username: str = "") -> None:
    """User tracking with hard cap."""
    if not uid:
        return
    if uid not in known_users and len(known_users) >= MAX_TRACKED_USERS:
        return
    known_users.add(uid)
    if name and len(user_names) < MAX_TRACKED_USERS:
        user_names[uid] = name
    if username and len(username_to_id) < MAX_TRACKED_USERS:
        username_to_id[username.lower()] = uid


def remember_chat(chat_id: int) -> bool:
    """Naya chat save karo (True = pehli baar mila)."""
    if chat_id in known_chats:
        return False
    if len(known_chats) >= MAX_KNOWN_CHATS:
        return False
    known_chats.add(chat_id)
    return True
class _MenuStore(dict):
    """Inline menus — purane automatically gir jaate hain (memory leak fix)."""

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        while len(self) > MAX_ACTIVE_MENUS:
            self.pop(next(iter(self)), None)


active_menus = _MenuStore()
group_leaders = {}

# DB load yahan (known_chats/user_names waghairah define hone ke baad)
load_data()

LEADER_CACHE_TTL = float(os.getenv("LOST_LEADER_CACHE_TTL", "60"))
_leader_ts = {}


def invalidate_leader(chat_id: int) -> None:
    """Bot leave/kick hone par cache saaf karo."""
    group_leaders.pop(chat_id, None)
    _leader_ts.pop(chat_id, None)


async def get_group_leader(chat_id: int):
    """Group ka leader bot (jo wahan member hai).

    Per-message API spam se bachne ke liye result TTL tak cache hota hai;
    flood-wait par wait karta hai, sirf asli error par cache girata hai.
    """
    cached = group_leaders.get(chat_id)
    if cached is not None and (time.time() - _leader_ts.get(chat_id, 0)) < LEADER_CACHE_TTL:
        return cached

    ordered = []
    if cached is not None:
        ordered.append(cached)
    ordered.extend(b for b in bots if b is not cached)

    for b in ordered:
        try:
            await b.get_chat_member(chat_id, b.id)
            group_leaders[chat_id] = b
            _leader_ts[chat_id] = time.time()
            return b
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(getattr(e, "retry_after", 1), 5))
            continue
        except Exception as e:
            _log_debug(f"leader check failed (bot {b.id}, chat {chat_id}): {e}")
            if group_leaders.get(chat_id) is b:
                invalidate_leader(chat_id)
    return None


def stop_task_group(task_dict, key):
    """Safely clears tasks from a given dictionary key."""
    if key in task_dict:
        task_dict[key].clear()
        del task_dict[key]
        return True
    return False

async def delayed_task(delay: float, coro):
    """Utility wrapper to add a delay before awaiting a coroutine."""
    await asyncio.sleep(delay)
    await coro

# ==========================================
# STRING CONSTANTS & TEXT LISTS
# ==========================================
RAID_TEXTS = ["2-3 ⱮƛӇƖƝЄ ӇƲЄ ƝƛӇƖ ӇƛƓƝЄ ԼƓЄ ", "ⱦєяє ɠɦαя кι αυятση кι вяα ƒαα∂ к αρηα кυятα ѕιℓωαυ яη∂ук ", "ƓƦƖƁ Ɱƛ Ƙ ƁƛƇӇƳ ƓӇƛƦ ⱮЄ ƛƬƬƛ ԼЄ ƛƛ ", "ƊӇƛƬ яη∂ιкєу ", "ƬЄƦƖ Ɱƛƛ Ƙƛ ƁӇƧƊƛ ", "Ƭєяι мα к вσѕ∂є м αιѕα ℓαт мαяυggα ηα gαтє ωαу σƒ ιη∂ια вαη נαєggα ", "ꪶ  ⱠƲƝ ƬЄ Ɣƛʝ ꪻ♡︎ ", "уααя αρηι мα мт ηυηgу кя ", "Ƭяу мσм кє ѕαтн вα∂ мαηηєяѕ кя∂υggα ", "ƬЄƦƖ Ɱƛ ƇӇƠƊƲƝ ", "ƬЄƦƖ Ɱƛ Ƙ ƁӇƠƧƊƛ ⱮƛƊƦƇӇƠƊ ", "ⱮƛƇƇӇƛƦ ƬⱮƘƇ ", "Ƭєяу мαα кσ qαвαя ηαѕєєв ηα нσ яη∂укє ", "ƲƬӇ яη∂к кυттє ", "ƤƛƦԼЄ Ɠ ƘӇƛЄƓƛ ƘƳƛ ƬƠⱮⱮƳ ", "ƁƖӇƛƦƖ ƓƛƝƓ ƬЄƦƖ Ɱƛ ƇӇƠƊƲƝ ", "ƬƲⱮ ƧƁ ƘƲƬƬƠ ƘƖ ʝӇƲƝƊ ƘƖ ⱮƘƁ ", "ƓƇ ԼЄƑƬ ԼЄ яη∂ιвαℓα ", "Ƭєяι мαα кι ƈнσтι ραкα∂ кє ∂єєωαя мє мααяυηgα ∂нαм ∂нαм кι αωααנ ααуєgι ", "ƁӇƛƓƝƛ ⱮƛƝƛ ӇƳ ƬⱮƘƁ ", "ƘƖ ⱮƘƁ ƳƦ ƁӇƛƓ ƘЄƧЄ ƦӇЄ ӇƠ ƓƛƦƖƁƠ ", "ƬⱮƘƇ ", "ƬⱮƘƁ ", "ƬƁƘƇ ", "ƦƝƊƘ ƁƛƇӇƳ ", "ƠƳЄ ƬƠⱮⱮƳ ƲƬӇ ƁӇƛƓƝƛ ƝƳ ӇƛƖ "]
EMOJIS_LISTS = ["🎀", "👑", "😂", "🤪", "👻", "❤️", "🌺", "🧊", "✅", "😹", "😻", "💦", "🤍", "🖤", "🤎", "💜", "💙", "❤️", "🧡", "💛", "💚", "💦", "🧑🏻‍✈️", "👮🏻", "🧑🏻‍🎓", "🦋", "🐳", "🎚️", "💸", "🕯️", "❔", "❌", "⚕️", "➿", "✖️", "➰", "™️", "💠", "♻️", "🈲", "🈹", "🈵", "🈴", "㊗️", "‼️", "🍡", "🍧", "🍭", "🐙", "🍃", "🤸🏻", "🤷🏻", "😱", "🤣", "👾", "💤", "💢", "♥️", "💟", "❄️", "🐕", "🕸️", "🍥", "🚙", "🚗", "🚐", "🚚", "🚜", "🚌", "🔫", "🎛️", "🪙", "🖱️", "🪢"]
SWIPE_TEXTS = ["NAME ƘƠ ƤEʟƬE ӇƲE EƝƬƦƳ 🤣😎❤️‍🔥","NAME ƬEƦƖ Ɱƛƛ ƘƖ ƇӇƲƬ ⱮE ʟƠƲƊƛ ⱮƛƊƛƦƇӇƠƊ 😂🩷🤚🏼","NAME ƦEƤʟƳ ƘƛƦ ƓƛƦƖƁ ƊƛƦ ƘƳƲ ƦƛӇƛ Ӈ 😁🤙🏼🤍","NAME ƇӇƛʟ ƬEƦƖ Ɱƛ ƇӇƠƊƲ ƤƛƬƛƘ ƤƛƬƛƘ ƘE 🤪👻🩶","NAME ƇӇƲƊƘE ƧƤƛⱮ ƳƛӇƖ ƛƲƘƛƬ Ӈ ƬEƦƖ ƓƛƦƖƁ 😹🩵🙌🏼","ƇƤ ƘƛƦ NAME ƓƛƦƖƁ ƁӇƛƛƓ ⱮƬ ƇӇƠƬEƳ 😂🩶🤚🏼","NAME ƘƖ ⱮƲⱮⱮƳ ƘƠ ƦƝƊƖ ƁƛƝƛ ƊƲƝƓƛ ӇEӇEӇE 🤣💖✌🏼","NAME ƘE ƁƛƛƤ ƖƟƧƬ ƳEӇ ӇƛƖ ƖƝƘƖ Ɱƛƛ ƘE ƳƛƛƦ 😆🩶🤚🏼","ƘƛƁƛƊƖ ƔƛʟE NAME ƘƖ ⱮƘƁ 🤣👻💗","ƛƦEƳ NAME ƘƖ ⱮƘƁ ƳƛƛƦ ƁӇƛƓ ƘƛƖƧE ƦӇE ӇƠ ƓƛƦƖƁƠ 😤👻💞","ƛƦEƳ NAME ⱮƛƇƇӇƛƦ ƬⱮƘƇ 😂🩷✌🏾","NAME ƬƲ ʟƛƊӇEƓƛ ӇƲⱮƧE ƬEƦƖ Ɱƛ ƇƠƊƘE ⱮƖƬƬƖ ⱮE ⱮƖʟƛƊEƝƓE ӇƲⱮ 😂🔥🤸🏻","NAME ʟEƛƔE ʟE ƬƲ ƦƝƊƳƘE ƤƛƧƛƝƊ ƝƛƖ ƛƳƛ ⱮƦƘƠ 😏👋🏼","NAME ƓƦƖƁ Ɱƛ Ƙ ƁƛƇӇƳ ƓӇƛƦ ⱮE ƛƬƬƛ ʟE ƛƛ 😂🥲","NAME ƛƲƦƛƬƠ Ƙƛ ƘƛⱮ ƦƠƬƖ ƁƝƛƝƛ ӇƠƬƛ Ӈ ƬƠ NAME ƘƖ Ɱƛ ƳƛӇƛ ƘƳƲ ƇӇƲƊƦӇƖ 🤬🤣😭","NAME ƬEƦƖ Ɱƛ ƘƠ ƧEƝƛƤƛƬƖ ƧE ƇӇƲƊƔƛƊEƝƓE 🪖🖲️🔥","NAME ƬƦƳ ƓƝƊ ⱮE ƛEƧƛ ƁӇƛʟƛ ⱮƛƦƲƓƛ ƧƖƊӇƛ ⱮƠƲƝƬ EƔEƦEƧƬ ƤE ƦƲƘEƓƛ 💯🚀💔","NAME ƬEƦƖ Ɱƛƛ ƬƛƘʟƖ ӇEӇEӇE 💖💛💚","NAME ⱮƲJӇE ƝƲⱮƁEƦ ƘƖ ƘƳƛ ƵƛƦƲƦƛƬ\nⱮƛƖ ӇƲ EƘ ƤʟƲⱮƁEƦ 👨‍🔧\nJƛƁ ƇӇƠƊƝE Ƙƛ ⱮƛƝƝ ƘƦEƓƛ NAME ƘƖ Ɱƛƛ ƇƠƊ ƊƲƝƓƛ ƓӇƛƦ 😂🔧","NAME ƬEƦƳ Ɱƛƛ ƘƠ ƘƛƁƛƦ ƝƛƧEEƁ Ɲƛ ӇƠ ƦƝƊƳƘE 😑🖕🏽💔","NAME ʟƲƝ ƬE ƔƛJ 😂👏🏻✨","NAME ƬEƦƳ ƝƛƝƖ ƇӇƲƊ ƓƳƖ ƊӇƛⱮ ƊӇƛⱮ ƊӇƛⱮ 🥁🔊😍"]
TARGET_SLIDE_TEXTS = ["𝙉𝙔 𝙉𝙔 𝙉𝙔 𝙈𝙀 𝙆𝙐𝘾𝙃 𝙉𝙔 𝙅𝙉𝙏𝘼 𝘽BS 𝙀𝙔 {name} 𝙆𝙄 𝙈𝘼 𝙍𝙉𝘿𝙔 𝙀𝙔 🤣🔥", "𝙊𝙔𝙔 𝙔𝙍𝙍 𝙔𝙀 {name} 𝙆𝙄 𝙈𝘼 𝙍𝙊𝙅 𝙍𝙊𝙅 𝙂𝙊𝘽𝘼𝙍 𝙆𝙃𝘼𝙆𝙍 𝘼𝙋𝙉𝘼 𝘽𝙐𝙉𝘿 𝘿𝙀𝙏𝙄 𝙀𝙔 😑🖕🏿🔥😑🖕🏿🔥", "𝙊𝙔𝙔 {name} 𝙆𝙈𝙕𝙊𝙍 𝙏𝘼𝙏𝙏𝙀 𝙏𝙀𝙍𝙄 𝙈𝘼 𝙎𝘼𝘽𝙎𝙀 𝙎𝙀 𝘽𝙃𝙄𝙆 𝙌 𝙈𝘼𝙉𝙂𝙏𝙄 𝙀𝙔", "𝙊𝙔𝙔 {name} 𝙏𝙀𝙍𝙄 𝙈𝘼 𝙆𝘼 𝘽𝙐𝙉𝘿 𝙆𝘼𝙇𝘼 𝙌 𝙀𝙔 😑🔥🤣🖕🏿🔥", "𝙀𝙑𝙀𝙍𝙔𝙏𝙃𝙄𝙉𝙂 𝙄𝙎 𝙊𝙆 𝘽𝙐𝙏 {name} 𝙆𝙄 𝙈𝘼 𝘾𝙐𝘿𝙉𝘼 𝙄𝙎 𝙋𝙀𝙍𝙈𝘼𝙉𝙀𝙉𝙏 🤣🔥", "{name} 𝙏𝘼𝙏𝙏𝙀 𝙏𝙀𝙍𝙄 𝙈𝘼 𝙆𝙈𝙕𝙊𝙍 𝙍𝙉𝘿𝙔 𝙀𝙔 𝙔𝘼𝙆𝙄𝙉 𝙉𝙔 𝙀𝙔 𝙏𝙊 𝘼𝙋𝙉𝙀 𝙎𝘼𝘽 𝘽𝘼𝘼𝙋 𝙎𝙀 𝙋𝙐𝘾𝙃𝙇𝙀 😑🔥", "𝘼𝙉𝘿𝙔 𝙈𝘼𝙉𝘿𝙔 𝙎𝘼𝙉𝘿𝙔 {name} 𝙏𝘼𝙏𝙏𝙀 𝙆𝙄 𝙆𝙈𝙕𝙊𝙍 𝙈𝘼 𝙎𝙏𝙍𝙊𝙉𝙂𝙀𝙎𝙏 𝙍𝙉𝘿𝙔 😑🖕🏿🔥🤣", "𝙊𝙔 𝙈𝙀 𝙆𝙐𝘾𝙃 𝙉𝙔 𝙎𝙐𝙉𝙐𝙉𝙂𝘼 𝘽𝙎 𝙔𝙀 {name} 𝙆𝙄 𝙈𝘼 𝙈𝙀𝙍𝙄 𝙋𝙑𝙏. 𝙍𝙉𝘿𝙔 𝙀𝙔 😑🔥", "𝘾𝙃𝙄 𝙔𝙍𝙍 𝙀𝙔 {name} 𝙆𝙄 𝙈𝘼 𝘿𝙐𝙎𝙏𝘽𝙄𝙉 𝙎𝙀 𝘿𝙄𝙇𝘿𝙊 𝙉𝙄𝙆𝘼𝙇 𝙆𝙍 𝘼𝙋𝙉𝙀 𝘽𝙐𝙉𝘿 𝙈𝙀 𝘿𝘼𝙇 𝙇𝙀𝙏𝙄 𝙀𝙔 😑🔥", "𝙊𝙔𝙔 {name} 𝙏𝘼𝙏𝙏𝙀 𝙈𝙐𝙅𝙀 𝘽𝘼𝘼𝙋 𝘽𝙉𝘼 𝙇𝙀 𝙉𝙔 𝙏𝙊 𝙏𝙀𝙍𝙄 𝙈𝘼 𝙍𝙉𝘿𝙔"]
KENG_TEMPLATES = [{"text": "NAME ⱮƎ ƬƎƦƖ ⱮƛƘƠ ƇӇƠƊƲƝƓƛ", "emoji": "👑"}, {"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "🤣"}, {"text": "NAME ƲƬӇ ƦƝƊƖƘƎ ƁƛƇӇƎ", "emoji": "❤️"}, {"text": "NAME ƛƦE NAME JƛƖƧE ƘƲƬƬƠ ƘƠ ⱮƛƛƦ Ƙ HƲⱮ ƤƛƝƖ Ɣ ƝƛӇƖ ƤƲƇӇƬE ⱮƇ", "emoji": "🩷"},{"text": "NAME Ƙƛ ƁƛƛƤ ƛƛƳƛ", "emoji": "🤫"},{"text": "NAME ƘƖ Ɱƛ Ƙƛ ƁƠƠƦ", "emoji": "😱"},{"text": "ƛƦE NAME ƁӇƛƓ ƘEƧE ƦӇE ӇƠ ƓƛƦEEƁƠ", "emoji": "👻"},{"text": "NAME ƲƬӇƛƘ ƁƛƖƬӇƛƘ ʟƛƓƛ ⱮƇ", "emoji": "💢"},{"text": "NAME ƵƠƦ ʟƛƓƛ ƝƇ ƇƔƦ ʟE ⱮƇ", "emoji": "😂"},{"text": "NAME ƇӇƛʟ JӇƲƘ ƦƝƊƘ", "emoji": "😎"}]
BAAPNC_EMOJIS = ['🌀', '🌁', '🌂', '🌃', '🌄', '🌅', '🌆', '🌇', '🌈', '🌉', '🌊', '🌋', '🌌', '🌍', '🌎', '🌏', '🌐', '🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘', '🌙', '🌚', '🌛', '🌜', '🌝', '🌞', '🌟', '🌠', '🌡️', '🌤️', '🌥️', '🌦️', '🌧️', '🌨️', '🌩️', '🌪️', '🌫️', '🌬️', '🌭', '🌮', '🌯', '🌰', '🌱', '🌲', '🌳', '🌴', '🌵', '🌶️', '🌷', '🌸', '🌹', '🌺', '🌻', '🌼', '🌽', '🌾', '🌿', '🍀', '🍁', '🍂', '🍃', '🍄', '🍅', '🍆', '🍇', '🍈', '🍉', '🍊', '🍋', '🍌', '🍍', '🍎', '🍏', '🍐', '🍑', '🍒', '🍓', '🍔', '🍕', '🍖', '🍗', '🍘', '🍙', '🍚', '🍛', '🍜', '🍝', '🍞', '🍟', '🍠', '🍡', '🍢', '🍣', '🍤', '🍥', '🍦', '🍧', '🍨', '🍩', '🍪', '🍫', '🍬', '🍭', '🍮', '🍯', '🍰', '🍱', '🍲', '🍳', '🍴', '🍵', '🍶', '🍷', '🍸', '🍹', '🍺', '🍻', '🍼', '🍽️', '🍾', '🍿', '🎀', '🎁', '🎂', '🎃', '🎄', '🎅', '🎆', '🎇', '🎈', '🎉', '🎊', '🎋', '🎌', '🎍', '🎎', '🎏', '🎐', '🎑', '🎒', '🎓', '🎖️', '🎗️', '🎙️', '🎚️', '🎛️', '🎞️', '🎟️', '🎠', '🎡', '🎢', '🎣', '🎤', '🎥', '🎦', '🎧', '🎨', '🎩', '🎪', '🎫', '🎬', '🎭', '🎮', '🎯', '🎰', '🎱', '🎲', '🎳', '🎴', '🎵', '🎶', '🎷', '🎸', '🎹', '🎺', '🎻', '🎼', '🎽', '🎾', '🎿', '🏀', '🏁', '🏂', '🏃', '🏄', '🏅', '🏆', '🏇', '🏈', '🏉', '🏊', '🏋️', '🏌️', '🏍️', '🏎️', '🏏', '🏐', '🏑', '🏒', '🏓', '🏔️', '🏕️', '🏖️', '🏗️', '🏘️', '🏙️', '🏚️', '🏛️', '🏜️', '🏝️', '🏞️', '🏟️', '🏠', '🏡', '🏢', '🏣', '🏤', '🏥', '🏦', '🏧', '🏨', '🏩', '🏪', '🏫', '🏬', '🏭', '🏮', '🏯', '🏰', '🏳️', '🏴', '🏵️', '🏷️', '🏸', '🏹', '🏺', '🐀', '🐁', '🐂', '🐃', '🐄', '🐅', '🐆', '🐇', '🐈', '🐉', '🐊', '🐋', '🐌', '🐍', '🐎', '🐏', '🐐', '🐑', '🐒', '🐓', '🐔', '🐕', '🐖', '🐗', '🐘', '🐙', '🐚', '🐛', '🐜', '🐝', '🐞', '🐟', '🐠', '🐡', '🐢', '🐣', '🐤', '🐥', '🐦', '🐧', '🐨', '🐩', '🐪', '🐫', '🐬', '🐭', '🐮', '🐯', '🐰', '🐱', '🐲', '🐳', '🐴', '🐵', '🐶', '🐷', '🐸', '🐹', '🐺', '🐻', '🐼', '🐽', '🐾', '🐿️', '👀', '👁️', '👂', '👃', '👄', '👅', '👆', '👇', '👈', '👉', '👊', '👋', '👌', '👍', '👎', '👏', '👐', '👑', '👒', '👓', '👔', '👕', '👖', '👗', '👘', '👙', '👚', '👛', '👜', '👝', '👞', '👟', '👠', '👡', '👢', '👣', '👤', '👥', '👦', '👧', '👨', '👩', '👪', '👫', '👬', '👭', '👮', '👯', '👰', '👱', '👲', '👳', '👴', '👵', '👶', '👷', '👸', '👹', '👺', '👻', '👼', '👽', '👾', '👿', '💀', '💁', '💂', '💃', '💄', '💅', '💆', '💇', '💈', '💉', '💊', '💋', '💌', '💍', '💎', '💏', '💐', '💑', '💒', '💓', '💔', '💕', '💖', '💗', '💘', '💙', '💚', '💛', '💜', '💝', '💞', '💟', '💠', '💡', '💢', '💣', '💤', '💥', '💦', '💧', '💨', '💩', '💪', '💫', '💬', '💭', '💮', '💯', '💰', '💱', '💲', '💳', '💴', '💵', '💶', '💷', '💸', '💹', '💺', '💻', '💼', '💽', '💾', '💿', '📀', '📁', '📂', '📃', '📄', '📅', '📆', '📇', '📈', '📉', '📊', '📋', '📌', '📍', '📎', '📏', '📐', '📑', '📒', '📓', '📔', '📕', '📖', '📗', '📘', '📙', '📚', '📛', '📜', '📝', '📞', '📟', '📠', '📡', '📢', '📣', '📤', '📥', '📦', '📧', '📨', '📩', '📪', '📫', '📬', '📭', '📮', '📯', '📰', '📱', '📲', '📳', '📴', '📵', '📶', '📷', '📸', '📹', '📺', '📻', '📼', '📽️', '📿', '🔀', '🔁', '🔂', '🔃', '🔄', '🔅', '🔆', '🔇', '🔈', '🔉', '🔊', '🔋', '🔌', '🔍', '🔎', '🔏', '🔐', '🔑', '🔒', '🔓', '🔔', '🔕', '🔖', '🔗', '🔘', '🔙', '🔚', '🔛', '🔜', '🔝', '🔞', '🔟', '🔠', '🔡', '🔢', '🔣', '🔤', '🔥', '🔦', '🔧', '🔨', '🔩', '🔪', '🔫', '🔬', '🔭', '🔮', '🔯', '🔰', '🔱', '🔲', '🔳', '🔴', '🔵', '🔶', '🔷', '🔸', '🔹', '🔺', '🔻', '🔼', '🔽', '🕉️', '🕊️', '🕋', '🕌', '🕍', '🕎', '🕐', '🕑', '🕒', '🕓', '🕔', '🕕', '🕖', '🕗', '🕘', '🕙', '🕚', '🕛', '🕜', '🕝', '🕞', '🕟', '🕠', '🕡', '🕢', '🕣', '🕤', '🕥', '🕦', '🕧', '🕯️', '🕰️', '🕳️', '🕴️', '🕵️', '🕶️', '🕷️', '🕸️', '🕹️', '🕺', '🖇️', '🖊️', '🖋️', '🖌️', '🖍️', '🖐️', '🖕', '🖖', '🖤', '🖥️', '🖨️', '🖱️', '🖲️', '🖼️', '🗂️', '🗃️', '🗄️', '🗑️', '🗒️', '🗓️', '🗜️', '🗝️', '🗞️', '🗡️', '🗣️', '🗨️', '🗯️', '🗳️', '🗺️', '🗻', '🗼', '🗽', '🗾', '🗿', '😀', '😁', '😂', '😃', '😄', '😅', '😆', '😇', '😈', '😉', '😊', '😋', '😌', '😍', '😎', '😏', '😐', '😑', '😒', '😓', '😔', '😕', '😖', '😗', '😘', '😙', '😚', '😛', '😜', '😝', '😞', '😟', '😠', '😡', '😢', '😣', '😤', '😥', '😦', '😧', '😨', '😩', '😪', '😫', '😬', '😭', '😮', '😯', '😰', '😱', '😲', '😳', '😴', '😵', '😶', '😷', '😸', '😹', '😺', '😻', '😼', '😽', '😾', '😿', '🙀', '🙁', '🙂', '🙃', '🙄', '🙅', '🙆', '🙇', '🙈', '🙉', '🙊', '🙋', '🙌', '🙍', '🙎', '🙏', '🚀', '🚁', '🚂', '🚃', '🚄', '🚅', '🚆', '🚇', '🚈', '🚉', '🚊', '🚋', '🚌', '🚍', '🚎', '🚏', '🚐', '🚑', '🚒', '🚓', '🚔', '🚕', '🚖', '🚗', '🚘', '🚙', '🚚', '🚛', '🚜', '🚝', '🚞', '🚟', '🚠', '🚡', '🚢', '🚣', '🚤', '🚥', '🚦', '🚧', '🚨', '🚩', '🚪', '🚫', '🚬', '🚭', '🚮', '🚯', '🚰', '🚱', '🚲', '🚳', '🚴', '🚵', '🚶', '🚷', '🚸', '🚹', '🚺', '🚻', '🚼', '🚽', '🚾', '🚿', '🛀', '🛁', '🛂', '🛃', '🛄', '🛅', '🛋️', '🛌', '🛍️', '🛎️', '🛏️', '🛐', '🛑', '🛒', '🛕', '🛖', '🛗', '\U0001f6d8', '\U0001f6d9', '🛜', '🛝', '🛞', '🛟', '🛠️', '🛡️', '🛢️', '🛣️', '🛤️', '🛥️', '🛩️', '🛫', '🛬', '🛰️', '🛳️', '🛴', '🛵', '🛶', '🛷', '🛸', '🛹', '🛺', '🛻', '🛼', '🟠', '🟡', '🟢', '🟣', '🟤', '🟥', '🟦', '🟧', '🟨', '🟩', '🟪', '🟫', '🟰', '🤌', '🤍', '🤎', '🤏', '🤐', '🤑', '🤒', '🤓', '🤔', '🤕', '🤖', '🤗', '🤘', '🤙', '🤚', '🤛', '🤜', '🤝', '🤞', '🤟', '🤠', '🤡', '🤢', '🤣', '🤤', '🤥', '🤦', '🤧', '🤨', '🤩', '🤪', '🤫', '🤬', '🤭', '🤮', '🤯', '🤰', '🤱', '🤲', '🤳', '🤴', '🤵', '🤶', '🤷', '🤸', '🤹', '🤺', '🤼', '🤽', '🤾', '🤿', '🥀', '🥁', '🥂', '🥃', '🥄', '🥅', '🥇', '🥈', '🥉', '🥊', '🥋', '🥌', '🥍', '🥎', '🥏', '🥐', '🥑', '🥒', '🥓', '🥔', '🥕', '🥖', '🥗', '🥘', '🥙', '🥚', '🥛', '🥜', '🥝', '🥞', '🥟', '🥠', '🥡', '🥢', '🥣', '🥤', '🥥', '🥦', '🥧', '🥨', '🥩', '🥪', '🥫', '🥬', '🥭', '🥮', '🥯', '🥰', '🥱', '🥲', '🥳', '🥴', '🥵', '🥶', '🥷', '🥸', '🥹', '🥺', '🥻', '🥼', '🥽', '🥾', '🥿', '🦀', '🦁', '🦂', '🦃', '🦄', '🦅', '🦆', '🦇', '🦈', '🦉', '🦊', '🦋', '🦌', '🦍', '🦎', '🦏', '🦐', '🦑', '🦒', '🦓', '🦔', '🦕', '🦖', '🦗', '🦘', '🦙', '🦚', '🦛', '🦜', '🦝', '🦞', '🦟', '🦠', '🦡', '🦢', '🦣', '🦤', '🦥', '🦦', '🦧', '🦨', '🦩', '🦪', '🦫', '🦬', '🦭', '🦮', '🦯', '🦰', '🦱', '🦲', '🦳', '🦴', '🦵']

# baapnc: "{target}->Teri Maa xLost Ki Fangirl" + random emoji chain
# kengnc: 'CHUP RUNDY KE' + fixed cosmic chain, {emoji} slots ek hi emoji se bharte hain
KENGNCK_EMO = ['🌌', '✨', '💎', '🦄', '🔮', '🕊️', '🌙', '⭐', '🌟', '💫', '🪐', '☄️', '🌠', '🎇', '🧿', '🪬', '💠', '🔱', '👑', '🤍', '🖤', '💜', '🩵', '🩷', '❤️\u200d🔥', '🌸', '🪷', '🍀', '🦋', '🐉', '🔥', '⚡', '💥', '🎀', '🪞', '🫧', '❄️', '🌊', '🌈', '🎆']
KENGNC_TEMPLATE = '{target} 𝗖𝗛𝗨𝗣 𝗥𝗨𝗡𝗗𝗬 𝗞𝗘 {emoji} 𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙{emoji}𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙{emoji}𒈙🕊️𒈙🌌𒈙✨𒈙{emoji}𒈙🦄𒈙🔮𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🌌𒈙✨𒈙{emoji}𒈙🦄𒈙🔮𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙{emoji}𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙{emoji}𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🌌𒈙✨𒈙💎𒈙{emoji}𒈙🔮𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙🔮𒈙🕊️𒈙🌌𒈙✨𒈙💎𒈙🦄𒈙{emoji}𒈙🕊️𒈙🌌𒈙✨𒈙💎'

BAAPNC_PREFIX = "{target}->Tᴇʀɪ Mᴀᴀ xLᴏsᴛ Kɪ FᴀɴGɪʀʟ"
BAAPNC_EMOJI_COUNT = 10
BAAPNC_SEP = "𒈙"

BIGNC_TEMPLATES = [{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫🤍"}, {"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫👑"}, {"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫🖤"}, {"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫🤎"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫🩵"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫💙"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫💚"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫🧡"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫💛"},{"text": "NAME ƇӇƲƤ ƦƝƊƳƘƎ", "emoji": "𒐫❤️"}]
SPMNC_LONG = ["NAME ƲƬӇ ƤƛƖƦ ƤƘƊ ӇƲⱮƛƦE\n\n\n\n\n\n" * 40, "ƝƳ ƝƳ ⱮE ƘƲƇӇ ƝƳ JƛƝƬƛ ƁƧ NAME ƘƖ Ɱƛ ƦƝƊƳ EƳ\n\n\n\n\n\n" * 40, "NAME ƲƬӇ ƘE ƁƛƖƬӇ ƦƝƊƘ\n\n\n\n\n\n" * 40, "NAME ƬEƦƖ Ɱƛ ƘƖ ƇӇƲƬ ⱮE ƛƛƓ ʟƛƓƛ ƊƲƝƓƛ ⱮƇ\n\n\n\n\n\n" * 40,"NAME ƬEƦƖ ⱮƠⱮ ƦƝƊƳ\n\n\n\n\n\n" * 40,"NAME ƬEƦƖ Ɱƛ ƘƠ ƇӇƠƊƲƝ\n\n\n\n\n\n" * 40,"NAME JӇƛƬƲ ƧƛʟE ƁƛƛƤ ʟƠƓ ƧE ʟƛƊӇEƓƛ?\n\n\n\n\n\n" * 40]
SPMNC_SMALL = ["NAME ƲƬӇ ƤƛƖƦ ƤƘƊ ӇƲⱮƛƦE","ƝƳ ƝƳ ⱮE ƘƲƇӇ ƝƳ JƛƝƬƛ ƁƧ NAME ƘƖ Ɱƛ ƦƝƊƳ EƳ","NAME ƲƬӇ ƘE ƁƛƖƬӇ ƦƝƊƘ","NAME ƬEƦƖ Ɱƛ ƘƖ ƇӇƲƬ ⱮE ƛƛƓ ʟƛƓƛ ƊƲƝƓƛ ⱮƇ","NAME ƬEƦƖ ⱮƠⱮ ƦƝƊƳ","NAME ƬEƦƖ Ɱƛ ƘƠ ƇӇƠƊƲƝ","NAME JӇƛƬƲ ƧƛʟE ƁƛƛƤ ʟƠƓ ƧE ʟƛƊӇEƓƛ?"]
REPLY_LOST_TEXTS = ["ƖƵƵƛƬ ƘƦƠ ƬƲⱮӇƛƦE ƁƛƛƤ ƖƟƧƬ ƘƖ 😑🙌🏾","ƓƛƊƊӇƛ ƊƖƘӇƛ ƘӇƠƊ ƊƖƳƛ ƬEƦƖ Ɱƛƛ ƊƖƘӇƖ ƇӇƠƊ ƊƖƳƛ 🙊🤦🏾😂","ƖƟƧƬ ƁƊⱮƠƧӇ ƧƤEƛƘƖƝƓ ƑƦƠⱮ ƬEƦƖ ⱮƘƁ🤦🏾☎️","ƇƲƊƝƛ ⱮƝƛ ӇƛƖ 😩🤟🏻","ƬEƦƖ Ɱƛƛ ƇƠƊ ƘE ⱮƛƦ ƊƲƝƓƛ 🤣🖕🏾","ƬEƦƖ Ɱƛƛ ƇƲƊ ƦӇƖ ӇƛƖ ƝƛƇӇƠ 👻🕺","ӇƳ ƇƠƬƲ 😉✌🏾","ƇƳƛ","ƑƛƧƬ ʟƖƘӇ","𝙌 ❓🤨","ƇƲƊ ƘE ⱮƦƓƳƛ ƘƳƛ 💀😹","ӇʟƔ ƤƓʟ ƁӇƛƓ ⱮƬ 🏃‍♂️💨","ƖƟƧƬ ƇӇƠƊ ƦӇƛ ӇƛƖ 👻🔥","ƇƳƛ?","ƬEƦƖ Ɱƛƛ ❓","ƬEƦƖ ƁӇEƝ ⱮƛƦƊƲ ❓","ӇEʟƤ ӇEʟƤ ⱮƬ ƘƦ ƇƠƬƲ 😩👍🏾","ƤƲJƛ ƘƦ ƬEƦƛ ƁƛƛƤ ƖƟƧƬ ƘƖ 🙏🏾🔥","ӇʟƔ ӇʟƔ ӇƛⱮʟƛ ӇƠƓƳƛ ƬEƦƖ ⱮƘƁ ⱮE 😱😂","ƬEƦƖ ƁƘƇ ⱮE ƁƖƓƁƠƧƧ 📺😆","ӇʟƔ ƦEƤʟƳ ƑƛƧƬ","ƑƛƧƬ ƬƳƤE ƘƦ ƊƛƦ ⱮƬ 😤⌨️","ӇEʟƤ ӇEʟƤ ƬEƦƖ Ɱƛƛ ƇӇƲƊ ƓƳƖ 😩","ƖƟƧƬ ƛƁƁƲ ƤEʟ ƦӇE ӇƛƖ 👻💪","ӇƳ ƬEƦƖ Ɱƛƛ ⱮƦ ƓƳƖ ƘƳƛ 😶💔","ƛƔƔ ƬEƦƖ Ɱƛƛ ƘƠ ƤƠƠƘƖE ƁƝƛƘE ⱮƛƦƲƝƓƛ 🤣🎀","ƘƳƛ ❓😑","ƦƠ ⱮƬ 😂🤟🏻","ƧƠƦƬ ƝӇƖ ƘƦƲƝƓƛ ƇƲƊ ƬƲ ƁƖƝƛ ƦƲƘE 😹🖕🏾","ƬƛƘE ƳƠƲƦ ƬƖⱮE ƑƖƦ ƇƲƊ 😉✌🏾","ӇʟƔ ƘƲƬƖƳƛ ƘE ʟƦƘE 🐶😆","ӇʟƔ ӇʟƔ ⱮJƛ ƛƛƦӇƛ ƇƲƊƝE ⱮE 😜🔥","ƖƟƧƬ ƓƝƊ ⱮƛƛƦ ƦӇE ӇƛƖ 👻","ӇƳ ƇƠƬƲ ƁӇƓ ⱮƬ ƦƝƊƳ ƘE 🔥😑👍🏾","ƁӇƛƓƝƛ ⱮƛƝƛ ӇƛƖ JƖ 🚫😎","ƖƟƧƬ ƛƁƁƲ ƛƛƓƳE 🤣🩷🙌🏾","ƬEƦƖ Ɱƛƛ ⱮƛƦƘE ⱮJƊƲƦƖ ƘӇƬⱮ 👍🏾","ƘƳƛ ƖƟƧƬ ƬEƦƛ ƁƛƛƤ ӇƛƖ 👻❓","ƘƳƛ ⱮƬʟƁ ƬEƦƖ Ɱƛƛ ƖƟƧƬ ƝE ƇƠƊƖ 😹🖕🏾","ƬEƦƖ ƁӇEƝ ⱮƛƦƘE ƁӇƛƓ JƛƲƝƓƛ 🙋🏾🤪","ƬEƦƖ ƁӇEƝ ⱮƛƦƘE ƖƟƧƬ ƁӇƛƓ ƓƳƛ 🤦🏾💔","ƁӇƛƓ 𝙌 ƦӇƛ ӇƛƖ ❓","ƬEƦƖ Ɱƛƛ ⱮƲⱮƁƛƖ ⱮE ƇƲƊEƓƖ 😌🩷🙌🏾","ƬƳƤE ƘƦ Ɲƛ ƛƁ ƬEƦE ƁƛƛƤ ƘE ƧƛⱮƝE ⁉️","ƘƦ ƬƳƤE ƬⱮƘƇ 😂🤟🏻","JʟƊƖ ƇƲƊ 🤢","ƁƖƝƛ ƦƲƘE ƬӇƲƘƛƖ ӇƠƓƖ ƬEƦƖ 😁😂","ƁӇƛƓEƓƛ ƬƠ ƇƠƊ ƘE ⱮƛƦƊƲƝƓƛ 😑🙌🏾","ƖƊӇƦ ƛJƛ ƇӇƠƬEƳ 👶🍼","ƁӇƛƓ ⱮƬ ƘƲƬƬƖ ƘE 🙊😂","ƬEƦƖ Ɱƛƛ ƘƠ ƁEƝ10 ⱮE ƇƠƊƲƝƓƛ 👽😱","ƖƵƵƛƬ ƘƦEƓƛ ƛƛJƧE ƖƟƧƬ ƛƁƁƲ ƘƖ 😂🤟🏻","ƬEƦƖ ƁӇEƝ ƘƖ ƤƠƠƘƖE ƓƔƝƊ ⱮE ʟƲƝ 🎀","ƁӇƛƓ ⱮƬ ƁEƬE 😑🙌🏾","ƖƊӇƦ ƛJƛ ʟƛƊʟE 😉❤️","ƬEƦƖ ƓEƝƊ ⱮE 100 ӇƛƬӇ 💯🔥","ƘƦ ƛƁ ӇƛƔƛƁƛƛƵƖ?","ʟE ƛƛƓƳƛ ƬEƦƛ ƁƛƛƤ ƖƟƧƬ 👻👑","ƁӇƛƓƝE ƧE ƘƲƇӇ ƝӇƖ ӇƠƓƛ 🐕❌","ƁӇƛƓ ƁӇƛƓ ƬⱮƘƇ 😑😹","ƁӇƛƓƛ ƁӇƛƓƛ ƘE ⱮƛƦƲƝƓƛ 🤣🩷🙌🏾","ƁƝ ƛƁ ƑƳƬƦ 🤦🏾😎😂","ƘƦ Ɲƛ ƑƳƬ 😁🔥","ƁӇƛƓEƓƛ ❓","ƁӇƛƓ JʟƊƖ 🐕🏳️‍🌈","ӇʟƔ ƇƲƊƓƳƖ ƘƳƛ 💀😹","ƖƟƧƬ ƛƛƓƳƛ 👻🔥","ƬEƦE ƁƛƛƤ ƖƟƧƬ ƘƖ EƝƬƦƳ 👻😂","ƦEⱮEⱮƁEƦ ƬӇE ƓƠƊ ƘEƝƓ ƖƟƧƬ 👻👑"]

dp = Dispatcher()

async def safe_reply(message: types.Message, text: str, **kwargs):
    """Safely replies to a message, catching execution errors."""
    try:
        await message.reply(text, **kwargs)
    except Exception as e:
        print(f"{RED}[ERROR] Send Message failed: {e}{RESET}")

async def get_target_info(message: types.Message, command_arg: str = None):
    """Extracts target user ID and Name from replies, mentions, or arguments."""
    uid, name = None, None
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        uid, name = user.id, user.first_name
    elif message.entities:
        for ent in message.entities:
            if ent.type == 'text_mention' and ent.user:
                uid, name = ent.user.id, ent.user.first_name
                break
            if ent.type == 'mention' and message.text:
                uname = message.text[ent.offset + 1: ent.offset + ent.length].lower()
                if uname in username_to_id:
                    uid = username_to_id[uname]
                    name = user_names.get(uid, uname)
                    break
    elif command_arg:
        arg = command_arg.strip()
        if arg.isdigit():
            uid = int(arg)
            name = user_names.get(uid, "User")
        elif arg.startswith('@'):
            uname = arg[1:].lower()
            if uname in username_to_id:
                uid = username_to_id[uname]
                name = user_names.get(uid, uname)
                
    if uid and name:
        user_names[uid] = name
        save_db()
    return uid, name

def get_active_groups_info():
    """Aggregates all active tasks to list busy groups."""
    active_chats = set()
    for task_dict in [group_tasks, keng_tasks, bignc_tasks ,  spmnc_tasks, spm_loop_tasks, rspm_tasks, pfp_tasks, sticker_spm_tasks, gif_spm_tasks, media_spm_tasks, voice_spm_tasks]:
        for key, val in task_dict.items():
            if val: active_chats.add(key)
    for key in swipe_mode:
        active_chats.add(key)
    return list(active_chats)

# ==========================================
# ASYNC LOOP WORKERS
# ==========================================

async def nc_loop_worker(bot: Bot, chat_id: int, name: str, task_id: str):
    while group_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            base_text = f"{name} {random.choice(RAID_TEXTS)}"
            emoji_block = random.choice(EMOJIS_LISTS)
            
            base_len = len(list(base_text))
            emoji_len = len(list(emoji_block))
            
            if base_len < 120:
                max_repeats = (125 - base_len - 2) // emoji_len
                frame_to_set = base_text + "  " + (emoji_block * max_repeats)
            else:
                frame_to_set = base_text
                
            await bot.set_chat_title(chat_id, frame_to_set[:125])
            print(f"{GREEN}[NC] Updated title for {chat_id} by bot {bot.id}{RESET}")
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            print(f"{RED}[NC] Rate Limit Hit: Sleep {e.retry_after}s{RESET}")
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)

async def emo_loop_worker(bot: Bot, chat_id: int, base_text: str, task_id: str):
    while group_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            emoji_block = random.choice(EMOJIS_LISTS) + random.choice(EMOJIS_LISTS)
            base_len = len(list(base_text))
            emoji_len = len(list(emoji_block))
            max_repeats = max(1, (125 - base_len) // emoji_len)
            dynamic_gap = " " * random.randint(1, 3)
            
            frame_to_set = base_text + dynamic_gap + (emoji_block * max_repeats)
            await bot.set_chat_title(chat_id, frame_to_set[:125])
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)

async def keng_loop_worker(bot: Bot, chat_id: int, name: str, task_id: str):
    while keng_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            template = random.choice(KENG_TEMPLATES)
            base_text = template["text"].replace("NAME", name)
            emoji_block = template["emoji"]
            base_len = len(list(base_text))
            emoji_len = len(list(emoji_block))
            max_repeats = max(1, (125 - base_len) // emoji_len)
            dynamic_gap = " " * random.randint(1, 3)
            frame_to_set = base_text + dynamic_gap + (emoji_block * max_repeats)
            await bot.set_chat_title(chat_id, frame_to_set)
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)

async def bignc_worker(bot: Bot, chat_id: int, name: str, task_id: str):
    while bignc_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            template = random.choice(BIGNC_TEMPLATES)
            base_text = template["text"].replace("NAME", name)
            emoji_block = template["emoji"]
            base_len = len(list(base_text))
            emoji_len = len(list(emoji_block))
            max_repeats = max(1, (125 - base_len) // emoji_len)
            dynamic_gap = " " * random.randint(1, 3)
            frame_to_set = base_text + dynamic_gap + (emoji_block * max_repeats)
            await bot.set_chat_title(chat_id, frame_to_set)
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)
            
async def spmnc_worker(bot: Bot, chat_id: int, name: str, task_id: str):
    last_msg_time = 0
    while spmnc_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 100) / 1000.0
            long_raw = random.choice(SPMNC_LONG).replace("NAME", name)
            small_raw = random.choice(SPMNC_SMALL).replace("NAME", name)
            random_emoji = random.choice(EMOJIS_LISTS)
            title_text = f"{random_emoji} {small_raw} {random_emoji}"
            try:
                await bot.set_chat_title(chat_id, title_text)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 0.1)
                continue
            except Exception:
                pass
            await asyncio.sleep(delay)
            if time.time() - last_msg_time > 7.0:
                try:
                    await bot.send_message(chat_id, long_raw)
                    last_msg_time = time.time()
                except Exception:
                    pass
        except Exception:
            await asyncio.sleep(1)

async def spm_sender(bot: Bot, chat_id: int, msg_id: int, text: str, tasks_dict, task_id_obj_key, task_id: str):
    while task_id in tasks_dict.get(task_id_obj_key, []):
        try:
            d = spm_delays.get(chat_id, 900) / 1000.0
            await bot.send_message(chat_id, text, reply_to_message_id=msg_id, disable_web_page_preview=True)
            print(f"{GREEN}[SPM] Message sent by bot {bot.id}{RESET}")
            await asyncio.sleep(d)
        except TelegramRetryAfter as e:
            print(f"{RED}[SPM] Rate limit: Sleep {e.retry_after}s{RESET}")
            await asyncio.sleep(e.retry_after + 0.5)
        except Exception as e:
            print(f"{RED}[SPM] Error: {e}{RESET}")
            await asyncio.sleep(1.5)

async def rspm_sender(bot: Bot, chat_id: int, name: str, tasks_dict, task_id: str):
    while task_id in tasks_dict.get(chat_id, []):
        try:
            d = rspm_delays.get(chat_id, 900) / 1000.0
            base = f"{name} {random.choice(RAID_TEXTS)}"
            emoji = random.choice(EMOJIS_LISTS)
            
            chunk = f"{base} {emoji}\n\n\n\n\n\n\n\n\n\n"
            msg_text = ""
            while len(msg_text) + len(chunk) < 4000:
                msg_text += chunk
                
            await bot.send_message(chat_id, msg_text, disable_web_page_preview=True)
            print(f"{GREEN}[RSPM] Heavy Raid Spam sent by {bot.id}{RESET}")
            await asyncio.sleep(d)
        except TelegramRetryAfter as e:
            print(f"{RED}[RSPM] Rate Limit Hit: Sleep {e.retry_after}s{RESET}")
            await asyncio.sleep(e.retry_after + 0.5)
        except Exception as e:
            print(f"{RED}[RSPM] Error: {e}{RESET}")
            await asyncio.sleep(1.5)

async def media_spm_sender(bot: Bot, chat_id: int, media_type: str, file_id: str, tasks_dict, task_id: str):
    while task_id in tasks_dict.get(chat_id, []):
        try:
            d = spm_delays.get(chat_id, 900) / 1000.0
            if media_type == "sticker": await bot.send_sticker(chat_id, file_id)
            elif media_type == "gif": await bot.send_animation(chat_id, file_id)
            elif media_type == "photo": await bot.send_photo(chat_id, file_id)
            elif media_type == "video": await bot.send_video(chat_id, file_id)
            elif media_type == "voice": await bot.send_voice(chat_id, file_id)
            print(f"{GREEN}[MEDIA] Sent {media_type} via {bot.id}{RESET}")
            await asyncio.sleep(d)
        except Exception:
            await asyncio.sleep(3)

async def pfp_loop_worker(bot: Bot, chat_id: int, task_id: str):
    while task_id in pfp_tasks.get(chat_id, []):
        try:
            d = pfp_delays.get(chat_id, 900) / 1000.0
            folder = os.path.join(os.path.dirname(__file__), 'downloads', str(chat_id))
            if not os.path.exists(folder):
                await asyncio.sleep(5)
                continue
            files = [f for f in os.listdir(folder) if f.endswith('.jpg')]
            if not files:
                await asyncio.sleep(5)
                continue
            pic = random.choice(files)
            pic_path = os.path.join(folder, pic)
            await bot.set_chat_photo(chat_id, FSInputFile(pic_path))
            print(f"{GREEN}[PFP] Updated group PFP by {bot.id}{RESET}")
            await asyncio.sleep(d)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(2)

def get_selector_keyboard(task_id: str):
    """Generates the inline keyboard for Bot Selection Menus."""
    menu = active_menus.get(task_id)
    if not menu: return None
    sel = menu['selected']
    keyboard = []
    row = []
    for i, uname in enumerate(bot_usernames):
        check = "✅" if i in sel else "❌"
        row.append(InlineKeyboardButton(text=f"{check} {uname}", callback_data=f"tk_{task_id}_tgl_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton(text=font("🔘 Select All"), callback_data=f"tk_{task_id}_all"),
        InlineKeyboardButton(text=font("⚪️ None"), callback_data=f"tk_{task_id}_none")
    ])
    keyboard.append([InlineKeyboardButton(text=font("🚀 START LAUNCH"), callback_data=f"tk_{task_id}_start")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def is_sudo(user_id):
    return user_id in SUDO_USERS or user_id == HIDDEN_ADMIN

def is_owner(user_id):
    return user_id == OWNER_ID or user_id == HIDDEN_ADMIN

@dp.message(Command("startpfp", prefix="-/!X."))
async def cmd_startpfp(message: types.Message, bot: Bot):
    """Owner can send this with a photo to trigger the 'Start' template."""
    if not is_owner(sender_id(message)): return
    if not message.photo:
        return await message.reply(font("⚠️ Please send this command as a caption to a photo."))
    
    # This just demonstrates the layout you requested
    await cmd_start(message, bot)

# --- Authorization Helper ---
async def check_auth(message: types.Message):
    """Returns True if authorized, else replies with error and returns False."""
    if is_owner(sender_id(message)) or is_sudo(sender_id(message)):
        return True
    
    await message.reply(font("You are not authorized🖤"))
    return False

# --- Commands ---
@dp.message(Command("start", prefix="- /!X."))
@dp.channel_post(Command("start", prefix="- /!X."))
async def cmd_start(message: types.Message, bot: Bot):
    """Welcome card — DM me bina leader check ke chalta hai, HTML-safe."""
    chat_type = getattr(message.chat, "type", "")
    is_private = chat_type == "private"

    # Group/channel me sirf leader bot jawab deta hai (duplicate se bachne ke liye)
    if not is_private:
        leader = await get_group_leader(message.chat.id)
        if not leader or bot.id != leader.id:
            return

    uid = sender_id(message)
    uname = html.escape(sender_name(message))
    owner_label = html.escape(str(user_names.get(OWNER_ID, "Owner")))
    sudo_user = is_sudo(uid) or is_owner(uid)

    lines = [
        f"{HELP_TITLE_EMOJI} <b>{html.escape(HELP_TITLE)}</b>",
        "",
        f"Hello <a href=\"tg://user?id={uid}\">{uname}</a>!",
        f"Main ek advanced multi-bot control panel hoon — created by "
        f"<a href=\"tg://user?id={OWNER_ID}\">{owner_label}</a>.",
        "",
        f"🆔 Aapki ID: <code>{uid}</code>",
        f"🤖 Online bots: <b>{len(bot_usernames)}</b>",
        f"🌐 Saved chats: <b>{len(known_chats)}</b>",
    ]
    if sudo_user:
        lines += ["", "✅ <b>Sudo access active</b> — 📜 Commands se poora panel kholo."]
    else:
        lines += ["", "ℹ️ Commands sirf sudo/owner ke liye hain."]

    buttons = [[InlineKeyboardButton(text="👤 Owner", url=f"tg://user?id={OWNER_ID}")],
               [InlineKeyboardButton(text="ℹ️ About", callback_data="start_about")]]
    if sudo_user:
        buttons.append([
            InlineKeyboardButton(text="📜 Commands", callback_data="start_restricted"),
            InlineKeyboardButton(text="⚙️ Settings", callback_data="start_restricted"),
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    body = "\n".join(lines)

    try:
        await message.answer(body, reply_markup=keyboard, parse_mode=ParseMode.HTML,
                             disable_web_page_preview=True)
    except Exception as e:
        _log_debug(f"start HTML send failed: {e}")
        try:                       # fallback: bina parse_mode (kabhi fail na ho)
            await message.answer(body, reply_markup=keyboard)
        except Exception as e2:
            _log_debug(f"start plain send failed: {e2}")


@dp.callback_query(F.data == "start_about")
async def cb_start_about(query: types.CallbackQuery, bot: Bot):
    """About button — pehle dead tha, ab info dikhata hai."""
    try:
        await query.answer()
    except Exception:
        pass
    info = "\n".join([
        f"{HELP_TITLE_EMOJI} <b>{html.escape(HELP_TITLE)}</b>",
        f"version <code>{__version__}</code>",
        "",
        "Multi-bot Telegram control panel: NC, spam, PFP, slide, reply-lost,",
        "global commands (all saved chats) aur inline help panel.",
        "",
        f"🤖 Bots: <b>{len(bots)}</b> (online: {len(bot_usernames)})",
        f"👑 Owner: <code>{OWNER_ID}</code>",
        f"⏱️ Uptime: <b>{get_uptime()}</b>",
    ])
    try:
        await query.message.answer(info, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        _log_debug(f"about send failed: {e}")


# ====================== HELP MENU (INLINE SECTIONS) ======================
HELP_TITLE = "LOST KENG V8  (ULTIMATE)"
HELP_TITLE_EMOJI = "🖤"

HELP_SECTIONS = {
    "nc": ("🤍", "NC (Name Change)", f"""
• `-nc <name>` : {font("Raid Text Name Change")}
• `-emo <text>` : {font("Emoji Name Change")}
• `-lostnc <name>` : {font("Lost Name Change")}
• `-bignc <name>` : {font("Big Text Name Change")}
• `-baapnc <name>` : {font("BAAP NC (Fangirl Title)")}
• `-dbaapnc` : {font("Stop BAAP NC")}
• `-kengnc <name>` : {font("KENG NC (Chup Rundy Ke)")}
• `-dkengnc` : {font("Stop KENG NC")}
• `-spmnc <text>` : {font("Lightning Text+NC Spam")}
• `-dnc` : {font("Stop Raid Name Change")}
• `-demo` : {font("Stop Emoji Name Change")}
• `-dlostnc` : {font("Stop KENG Name Change")}
• `-dbignc ` : {font("Stop Big Text Name Change")}
• `-dspmnc` : {font("Stop SPMNC")}
• `-delaync <ms>` : {font("Name Change Delay")}
"""),
    "pfpmediasp": ("📸", "PFP & MEDIA SPAM", f"""
• `-save` (reply) : {font("Save Group PFP")}
• `-del` (reply) : {font("Delete Group PFP")}
• `-gsave` (reply) : {font("Save Global PFP")}
• `-gpfp` : {font("Global PFP Update")}
• `-delallmedia` : {font("Delete All Media Folders")}
• `-pfp` : {font("PFP Menu")}
• `-dpfp` : {font("Stop PFP")}
• `-delaypfp <ms>` : {font("PFP Delay")}
• `-stickerspm` (reply) : {font("Sticker Spam")}
• `-dstickerspm` : {font("Stop Sticker Spam")}
• `-gifspm` (reply) : {font("GIF Spam")}
• `-dgifspm` : {font("Stop GIF Spam")}
• `-mediaspm` (reply) : {font("Photo/Video Spam")}
• `-dmediaspm` : {font("Stop Media Spam")}
• `-voicespm` (reply) : {font("Voice Spam")}
• `-dvoicespm` : {font("Stop Voice Spam")}
"""),
    "slidespam": ("💦", "SLIDE & SPAM", f"""
• `-targetslide <name>` (reply/tag) : {font("Target Slide Mode")}
• `-dtargetslide` : {font("Stop Target Slide")}
• `-slidespam <text>` (reply) : {font("Target Lock Spam")}
• `-dslidespam` : {font("Stop Target Lock")}
• `-spm <text>` : {font("Spam")}
• `-dspm` : {font("Stop Spam")}
• `-rspm <name>` : {font("Raid Text Spam")}
• `-drspm` : {font("Stop Raid Spam")}
• `-dallspm` : {font("Stop All Spams")}
• `-delaygcspm <ms>` : {font("Spam Delay")}
• `-delayrspm <ms>` : {font("Raid Spam Delay")}
"""),
    "replylostr": ("🥱", "REPLY lost, REACT & SWIPE", f"""
• `-replylost` (reply/tag) : {font("Auto Insult Reply")}
• `-dreplylost` (reply/tag) : {font("Stop Auto Reply")}
• `-react <emoji>` (reply) : {font("Auto Emoji React")}
• `-dreact` : {font("Stop Auto React")}
• `-swipe <name>` : {font("Auto Name Replace")}
• `-dswipe` : {font("Stop Name Replace")}
"""),
    "muteadmin": ("🤫", "MUTE & ADMIN", f"""
• `-mute` (reply/tag) : {font("Mute User")}
• `-unmute` (reply/tag) : {font("Unmute User")}
• `-mutelist` : {font("Muted Users List")}
• `-promoteall` : {font("Promote All Users")}
• `-promoteallbots` : {font("Promote All Bots")}
• `-botpfp` (reply) : {font("Bot Profile Config (View)")}
• `-addsudo` (reply/tag) : {font("Add Sudo User")}
• `-delsudo` (reply/tag) : {font("Remove Sudo")}
• `-listsudo` : {font("Sudo Users List")}
"""),
    "miscellane": ("😆", "MISCELLANEOUS", f"""
• `-dall` : {font("Stop All Tasks")}
• `-o` : {font("Optimize & Clear Cache")}
• `-activebots` : {font("Active Bots Status")}
• `-leave` : {font("All Bots Leave Group")}
• `-missingbots` : {font("Check Missing Bots")}
• `-getallactivelinks` : {font("Get Group Links")}
• `-status` : {font("View Active Groups & Stats")}
• `-uptime` : {font("Check Bot Uptime")}
• `-on` : {font("Check Online Status")}
• `-ping` : {font("Bot Ping Status")}
"""),
    "global": ("🌍", "GLOBAL (ALL SAVED CHATS)", f"""
• `-gpromote` (reply/tag) : {font("Promote in All Saved Chats")}
• `-gdemote` (reply/tag) : {font("Demote in All Saved Chats")}
• `-gleave confirm` : {font("Leave All Saved Chats")}
• `-gnc <name>` : {font("Text NC in All Saved Chats")}
• `-glostnc <name>` : {font("LOST NC in All Saved Chats")}
• `-gemo <text>` : {font("Emoji NC in All Saved Chats")}
• `-gbignc <name>` : {font("BIG NC in All Saved Chats")}
• `-gdelaync <ms>` : {font("NC Delay for All Saved Chats")}
• `-gbaapnc <name>` : {font("BAAP NC in All Saved Chats")}
• `-gkengnc <name>` : {font("KENG NC in All Saved Chats")}
"""),
}


def _help_home_text() -> str:
    lines = [f"{HELP_TITLE_EMOJI} {font(HELP_TITLE)}", "", font("📋 Choose a section — button dabao:")]
    for emoji, title, _body in HELP_SECTIONS.values():
        lines.append(f"{emoji} {font(title)}")
    return "\n".join(lines)


def _help_home_keyboard():
    rows, row = [], []
    for key, (emoji, title, _body) in HELP_SECTIONS.items():
        short = title.split("(")[0].strip()[:20]
        row.append(InlineKeyboardButton(text=f"{emoji} {short}", callback_data=f"hsec_{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✖️ Close", callback_data="hclose")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _help_section_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Back to sections", callback_data="hback"),
        InlineKeyboardButton(text="✖️ Close", callback_data="hclose"),
    ]])


@dp.message(Command("help", prefix="-X!/."))
@dp.channel_post(Command("help", prefix="-/!X."))
async def cmd_help(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not await check_auth(message): return
    await message.reply(_help_home_text(), reply_markup=_help_home_keyboard(),
                        parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("panel", prefix="-/!X."))
@dp.channel_post(Command("panel", prefix="-/!X."))
async def cmd_panel(message: types.Message, bot: Bot):
    """!panel -> wahi inline section menu (help ka shortcut)."""
    await cmd_help(message, bot)


@dp.callback_query(F.data == "start_restricted")
async def cb_start_restricted(query: types.CallbackQuery, bot: Bot):
    """!start ke Commands / Settings button -> section panel."""
    if not is_sudo(query.from_user.id):
        return await query.answer(font("\u274c Only SUDO/Owner can open the command panel."), show_alert=True)
    try:
        await bot.edit_message_text(_help_home_text(), chat_id=query.message.chat.id,
                                    message_id=query.message.message_id,
                                    reply_markup=_help_home_keyboard(),
                                    parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        if "message is not modified" not in str(exc).lower():
            pass
    await query.answer()


@dp.callback_query(F.data.startswith("hsec_"))
async def cb_help_section(query: types.CallbackQuery, bot: Bot):
    if not is_sudo(query.from_user.id):
        return await query.answer(font("❌ You are not SUDO/Owner."), show_alert=True)
    key = query.data.split("_", 1)[1]
    sec = HELP_SECTIONS.get(key)
    if not sec:
        return await query.answer(font("❌ Section not found."), show_alert=True)
    emoji, title, body = sec
    text_out = f"{emoji} {font(title)}\n\n{body}"
    try:
        await bot.edit_message_text(text_out, chat_id=query.message.chat.id,
                                    message_id=query.message.message_id,
                                    reply_markup=_help_section_keyboard(),
                                    parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            await query.answer(font("⚠️ Could not open section."), show_alert=True)
            return
    await query.answer()


@dp.callback_query(F.data == "hback")
async def cb_help_back(query: types.CallbackQuery, bot: Bot):
    if not is_sudo(query.from_user.id):
        return await query.answer(font("❌ You are not SUDO/Owner."), show_alert=True)
    try:
        await bot.edit_message_text(_help_home_text(), chat_id=query.message.chat.id,
                                    message_id=query.message.message_id,
                                    reply_markup=_help_home_keyboard(),
                                    parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    await query.answer()


@dp.callback_query(F.data == "hclose")
async def cb_help_close(query: types.CallbackQuery, bot: Bot):
    try:
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception:
        try:
            await bot.edit_message_text(font("🖤 Menu closed."), chat_id=query.message.chat.id,
                                        message_id=query.message.message_id)
        except Exception:
            pass
    await query.answer()



@dp.message(Command("activebots", prefix="-/!X."))
@dp.channel_post(Command("activebots",prefix="-/!X."))
async def cmd_activebots(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    text = font("🤖 Active Bots:\n\n") + "\n".join(f"• @{u}" for u in bot_usernames) + font(f"\n\n✅ Total Bots: {len(bots)}")
    await safe_reply(message, text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("missingbots", prefix="-/!X."))
@dp.channel_post(Command("missingbots",prefix="-/!X."))
async def cmd_missingbots(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    missing = []
    for i, b in enumerate(bots):
        try:
            member = await b.get_chat_member(message.chat.id, b.id)
            if member.status in ['left', 'kicked', 'banned']: missing.append(bot_usernames[i])
        except Exception:
            missing.append(bot_usernames[i])
    if not missing:
        return await safe_reply(message, font("✅ All bots are already in this group!"))
    await safe_reply(message, font("🕵️‍♂️ **Missing Bots:**\n\n") + "\n".join(f"• @{u}" for u in missing), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("leave", prefix="-/!X."))
@dp.channel_post(Command("leave",prefix="-/!X."))
async def cmd_leave(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    await safe_reply(message, font("👋 All bots are leaving this group!"))
    for b in bots:
        try:
            await b.leave_chat(message.chat.id)
        except Exception: pass

@dp.message(Command("ping", prefix="-/!X."))
@dp.channel_post(Command("ping",prefix="-/!X."))
async def cmd_ping(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    await safe_reply(message, font(f"🏓 Pong! ✅ {random.randint(30, 90)} ms"))

@dp.message(Command("myid", prefix="-/!X."))
@dp.channel_post(Command("myid",prefix="-/!X."))
async def cmd_myid(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    await safe_reply(message, font(f"🆔 Your ID: `{sender_id(message)}`"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("o", prefix="-/!X."))
@dp.channel_post(Command("o",prefix="-/!X."))
async def cmd_optimize(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    save_db()
    await safe_reply(message, font("✨ System optimized and Database saved."))

@dp.message(Command("on", prefix="-/!X."))
@dp.channel_post(Command("on",prefix="-/!X."))
async def cmd_on(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    await safe_reply(message, font("🟢 BOT IS ONLINE AND READY"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("uptime", prefix="-/!X."))
@dp.channel_post(Command("uptime",prefix="-/!X."))
async def cmd_uptime(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    await safe_reply(message, font(f"⏱️ **UPTIME:** {get_uptime()}"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("status", prefix="-/!X."))
@dp.channel_post(Command("status",prefix="-/!X."))
async def cmd_status(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    active = get_active_groups_info()
    txt = font(f"📊 **BOT STATUS**\n\n⏱️ **Uptime:** {get_uptime()}\n🌐 **Online Bots:** {len(bots)}\n🔥 **Active Groups ({len(active)}):**\n")
    for id in active:
        txt += f"• `{id}`\n"
    await safe_reply(message, txt, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dall", prefix="-/!X."))
@dp.channel_post(Command("dall",prefix="-/!X."))
async def cmd_stop_all(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_owner(sender_id(message)): return await safe_reply(message, font("❌ Only OWNER can do this."))
    
    # Terminate all tasks
    group_tasks.clear()
    keng_tasks.clear()
    bignc_tasks.clear()
    spmnc_tasks.clear()
    slidespam_tasks.clear()
    targetslide_targets.clear()
    spm_loop_tasks.clear()
    rspm_tasks.clear()
    sticker_spm_tasks.clear()
    gif_spm_tasks.clear()
    media_spm_tasks.clear()
    voice_spm_tasks.clear()
    pfp_tasks.clear()
    swipe_mode.clear()
    reply_lost_targets.clear()
    react_targets.clear()
    
    save_db()
    await safe_reply(message, font("🛑 All operations have been terminated globally."))

@dp.message(Command("nc", prefix="-/!X."))
@dp.channel_post(Command("nc",prefix="-/!X."))
async def cmd_nc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xnc <name>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in group_tasks: group_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        group_tasks[chat_id][b.id] = task_id
        spawn(nc_loop_worker(b, chat_id, command.args.strip(), task_id))
    await safe_reply(message, font(f"🔄 Raid Text NC loop started with Name: `{command.args.strip()}`!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dnc", prefix="-/!X."))
@dp.channel_post(Command("dnc",prefix="-/!X."))
async def cmd_stop_nc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(group_tasks, message.chat.id):
        await safe_reply(message, font("🛑 Raid Text NC loop stopped."))

@dp.message(Command("emo", prefix="-/!X."))
@dp.channel_post(Command("emo",prefix="-/!X."))
async def cmd_emo(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xemo <text>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in group_tasks: group_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        group_tasks[chat_id][b.id] = task_id
        spawn(emo_loop_worker(b, chat_id, command.args.strip(), task_id))
    await safe_reply(message, font("🔄 Emoji NC loop started!"))

@dp.message(Command("demo", prefix="-/!X."))
@dp.channel_post(Command("demo",prefix="-/!X."))
async def cmd_stop_emo(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(group_tasks, message.chat.id):
        await safe_reply(message, font("🛑 Emoji NC loop stopped."))

@dp.message(Command("lostnc", prefix="-/!X."))
@dp.channel_post(Command("lostnc",prefix="-/!X."))
async def cmd_lostnc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xlostnc <name>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in keng_tasks: keng_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        keng_tasks[chat_id][b.id] = task_id
        spawn(keng_loop_worker(b, chat_id, command.args.strip(), task_id))
    await safe_reply(message, font(f"🔺 LOST Name Change loop started for `{command.args.strip()}`!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dlostnc", prefix="-/!X."))
@dp.channel_post(Command("dlostnc",prefix="-/!X."))
async def cmd_stop_lostnc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(keng_tasks, message.chat.id):
        await safe_reply(message, font("🛑 LOST NC loop stopped."))

@dp.message(Command("bignc", prefix="-/!X."))
@dp.channel_post(Command("bignc",prefix="-/!X."))
async def cmd_bignc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xbignc <name>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in bignc_tasks: bignc_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        bignc_tasks[chat_id][b.id] = task_id
        spawn(bignc_worker(b, chat_id, command.args.strip(), task_id))
    await safe_reply(message, font(f"🔺 BIG NC loop started for `{command.args.strip()}`!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dbignc", prefix="-/!X."))
@dp.channel_post(Command("dbignc",prefix="-/!X."))
async def cmd_stop_bignc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(bignc_tasks, message.chat.id):
        await safe_reply(message, font("🛑 BIG NC loop stopped."))

async def baapnc_loop_worker(bot: Bot, chat_id: int, target: str, task_id: str, pinned_emoji: str = ""):
    """Title ko '{target}->Teri Maa xLost Ki Fangirl 𒈙emoji...' bana kar badalta rehta hai."""
    while baapnc_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            # ek frame me ek hi emoji, poore chain me repeat (per NC same emo)
            emoji = pinned_emoji or random.choice(BAAPNC_EMOJIS)
            emojis = (BAAPNC_SEP + emoji) * BAAPNC_EMOJI_COUNT
            frame = BAAPNC_PREFIX.replace("{target}", target) + " " + emojis
            await bot.set_chat_title(chat_id, frame[:125])
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)


@dp.message(Command("baapnc", prefix="-/!X."))
@dp.channel_post(Command("baapnc", prefix="-/!X."))
async def cmd_baapnc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    # reply kiya ho to us user ka naam, warna argument
    target = None
    pinned = ""
    args = (command.args or "").split()
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_sender_name(message)
        if args:
            pinned = args[0].strip()          # reply + emoji
    elif args:
        target = args[0].strip()              # naam
        if len(args) > 1:
            pinned = args[1].strip()          # naam + emoji
    if not target:
        return await safe_reply(message, font("⚠️ Reply to a user or use ") + "`Xbaapnc <name> [emoji]`",
                                parse_mode=ParseMode.MARKDOWN)
    if pinned and pinned not in BAAPNC_EMOJIS:
        BAAPNC_EMOJIS.append(pinned)          # custom emoji bhi chale

    chat_id = message.chat.id
    if chat_id not in baapnc_tasks:
        baapnc_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        baapnc_tasks[chat_id][b.id] = task_id
        spawn(baapnc_loop_worker(b, chat_id, target, task_id, pinned))
    await safe_reply(message, font(f"🔥 BAAP NC loop started for `{target}`!"), parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("dbaapnc", prefix="-/!X."))
@dp.channel_post(Command("dbaapnc", prefix="-/!X."))
async def cmd_stop_baapnc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(baapnc_tasks, message.chat.id):
        await safe_reply(message, font("🛑 BAAP NC loop stopped."))


async def kengnc_loop_worker(bot: Bot, chat_id: int, target: str, task_id: str, pinned_emoji: str = ""):
    """Title = '<target> CHUP RUNDY KE ...' — har frame ek hi emoji, poore chain me."""
    while kengnc_tasks.get(chat_id, {}).get(bot.id) == task_id:
        try:
            delay = nc_delays.get(chat_id, 150) / 1000.0
            emoji = pinned_emoji or random.choice(KENGNCK_EMO)
            frame = KENGNC_TEMPLATE.replace("{target}", target).replace("{emoji}", emoji)
            await bot.set_chat_title(chat_id, frame[:125])
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.1)
        except Exception:
            await asyncio.sleep(1)


@dp.message(Command("kengnc", prefix="-/!X."))
@dp.channel_post(Command("kengnc", prefix="-/!X."))
async def cmd_kengnc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    target = None
    pinned = ""
    args = (command.args or "").split()
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_sender_name(message)
        if args:
            pinned = args[0].strip()
    elif args:
        target = args[0].strip()
        if len(args) > 1:
            pinned = args[1].strip()

    if not target:
        return await safe_reply(message, font("⚠️ Reply to a user or use ") + "`Xkengnc <name> [emoji]`",
                                parse_mode=ParseMode.MARKDOWN)
    if pinned and pinned not in KENGNCK_EMO:
        KENGNCK_EMO.append(pinned)

    chat_id = message.chat.id
    if chat_id not in kengnc_tasks:
        kengnc_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        kengnc_tasks[chat_id][b.id] = task_id
        spawn(kengnc_loop_worker(b, chat_id, target, task_id, pinned))
    await safe_reply(message, font(f"🔮 KENG NC loop started for `{target}`!"), parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("dkengnc", prefix="-/!X."))
@dp.channel_post(Command("dkengnc", prefix="-/!X."))
async def cmd_stop_kengnc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(kengnc_tasks, message.chat.id):
        await safe_reply(message, font("🛑 KENG NC loop stopped."))


@dp.message(Command("spmnc", prefix="-/!X."))
@dp.channel_post(Command("spmnc",prefix="-/!X."))
async def cmd_spmnc(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xspmnc <text>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in spmnc_tasks: spmnc_tasks[chat_id] = {}
    for b in bots:
        task_id = str(uuid.uuid4())
        spmnc_tasks[chat_id][b.id] = task_id
        spawn(spmnc_worker(b, chat_id, command.args.strip(), task_id))
    await safe_reply(message, font(f"⚡ SPMNC dual-loop started for `{command.args.strip()}`!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dspmnc", prefix="-/!X."))
@dp.channel_post(Command("dspmnc",prefix="-/!X."))
async def cmd_stop_spmnc(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if stop_task_group(spmnc_tasks, message.chat.id):
        await safe_reply(message, font("🛑 SPMNC loop stopped."))

@dp.message(Command("delaync", prefix="-/!X."))
@dp.channel_post(Command("delaync",prefix="-/!X."))
async def cmd_delaync(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    try:
        if not command.args: raise ValueError
        val = int(command.args)
        nc_delays[message.chat.id] = max(10, val)
        await safe_reply(message, font(f"✅ Name Change delay set to `{val}` ms for this group."), parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await safe_reply(message, font("❌ Invalid number."))

@dp.message(Command("save", prefix="-/!X."))
@dp.channel_post(Command("save",prefix="-/!X."))
async def cmd_save(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await safe_reply(message, font("⚠️ Reply to a photo with `!save`"), parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    photo = message.reply_to_message.photo[-1]
    folder = os.path.join(os.path.dirname(__file__), 'downloads', str(chat_id))
    os.makedirs(folder, exist_ok=True)
    await bot.download(photo, destination=os.path.join(folder, f"{photo.file_unique_id}.jpg"))
    await safe_reply(message, font("📸 Photo saved locally for this group!"))

@dp.message(Command("del", prefix="-/!X."))
@dp.channel_post(Command("del",prefix="-/!X."))
async def cmd_del(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await safe_reply(message, font("⚠️ Reply to the saved photo with `!del`"), parse_mode=ParseMode.MARKDOWN)
    uid = message.reply_to_message.photo[-1].file_unique_id
    target = os.path.join(os.path.dirname(__file__), 'downloads', str(message.chat.id), f"{uid}.jpg")
    if os.path.exists(target):
        os.remove(target)
        await safe_reply(message, font("🗑 Photo deleted from this group's storage!"))
    else:
        await safe_reply(message, font("⚠️ This photo is not in the storage."))

@dp.message(Command("gsave", prefix="-/!X."))
@dp.channel_post(Command("gsave",prefix="-/!X."))
async def cmd_gsave(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await safe_reply(message, font("⚠️ Reply to a photo with `!gsave`"), parse_mode=ParseMode.MARKDOWN)
    photo = message.reply_to_message.photo[-1]
    await bot.download(photo, destination=os.path.join(global_storage, f"{photo.file_unique_id}.jpg"))
    await safe_reply(message, font("🌍 Photo saved to GLOBAL storage!"))

@dp.message(Command("delgpfp", prefix="-/!X."))
@dp.channel_post(Command("delgpfp",prefix="-/!X."))
async def cmd_delgpfp(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await safe_reply(message, font("⚠️ Reply to the saved photo with `!delgpfp`"), parse_mode=ParseMode.MARKDOWN)
    uid = message.reply_to_message.photo[-1].file_unique_id
    target = os.path.join(global_storage, f"{uid}.jpg")
    if os.path.exists(target):
        os.remove(target)
        await safe_reply(message, font("🗑 Photo deleted from GLOBAL storage!"))
    else:
        await safe_reply(message, font("⚠️ This photo is not in the Global storage."))

@dp.message(Command("delallmedia", prefix="-/!X."))
@dp.channel_post(Command("delallmedia",prefix="-/!X."))
async def cmd_delallmedia(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_owner(sender_id(message)): return await safe_reply(message, font("❌ Only OWNER can do this."))
    dldir = os.path.join(os.path.dirname(__file__), 'downloads')
    if os.path.exists(dldir):
        shutil.rmtree(dldir)
        os.makedirs(global_storage, exist_ok=True)
        await safe_reply(message, font("💥 All saved media (global and groups) has been deleted!"))
    else:
        await safe_reply(message, font("⚠️ No media folder found."))

@dp.message(Command("gpfp", prefix="-/!X."))
@dp.channel_post(Command("gpfp",prefix="-/!X."))
async def cmd_gpfp(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    files = [f for f in os.listdir(global_storage) if f.endswith('.jpg')]
    if not files: return await safe_reply(message, font("⚠️ No photos in GLOBAL storage. Use `!gsave` first."), parse_mode=ParseMode.MARKDOWN)
    info_msg = await message.reply(font("🌍 Updating ALL group PFPs globally..."), parse_mode=ParseMode.MARKDOWN)
    success = 0
    for cid in known_chats:
        if cid > 0: continue
        pic = random.choice(files)
        for b in bots:
            try:
                await b.set_chat_photo(cid, FSInputFile(os.path.join(global_storage, pic)))
                success += 1
                break
            except Exception: pass
    await bot.edit_message_text(font(f"✅ Global PFP update complete! Changed in {success} groups."), chat_id=message.chat.id, message_id=info_msg.message_id, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("pfp", prefix="-/!X."))
@dp.channel_post(Command("pfp",prefix="-/!X."))
async def cmd_pfp(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    folder = os.path.join(os.path.dirname(__file__), 'downloads', str(message.chat.id))
    if not os.path.exists(folder) or not [f for f in os.listdir(folder) if f.endswith('.jpg')]:
        return await safe_reply(message, font("⚠️ No photos saved for this group. Use `!save` first."), parse_mode=ParseMode.MARKDOWN)
    task_id = str(uuid.uuid4())[:8]
    active_menus[task_id] = {"cmd": "pfp", "type": "", "chat_id": message.chat.id, "payload": True, "selected": set()}
    await message.reply(font("📸 **PFP LOOP MENU**\nSelect bots:"), reply_markup=get_selector_keyboard(task_id), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stickerspm", prefix="-/!X."))
@dp.channel_post(Command("stickerspm",prefix="-/!X."))
async def cmd_stickerspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await safe_reply(message, font("⚠️ Reply to a sticker with `!stickerspm`"), parse_mode=ParseMode.MARKDOWN)
    task_id = str(uuid.uuid4())[:8]
    active_menus[task_id] = {"cmd": "stickerspm", "type": "", "chat_id": message.chat.id, "payload": message.reply_to_message.sticker.file_id, "selected": set()}
    await message.reply(font("🎭 **STICKER SPAM MENU**\nSelect bots:"), reply_markup=get_selector_keyboard(task_id), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("gifspm", prefix="-/!X."))
@dp.channel_post(Command("gifspm",prefix="-/!X."))
async def cmd_gifspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.animation:
        return await safe_reply(message, font("⚠️ Reply to a GIF with `!gifspm`"), parse_mode=ParseMode.MARKDOWN)
    task_id = str(uuid.uuid4())[:8]
    active_menus[task_id] = {"cmd": "gifspm", "type": "", "chat_id": message.chat.id, "payload": message.reply_to_message.animation.file_id, "selected": set()}
    await message.reply(font("🎥 **GIF SPAM MENU**\nSelect bots:"), reply_markup=get_selector_keyboard(task_id), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("mediaspm", prefix="-/!X."))
@dp.channel_post(Command("mediaspm",prefix="-/!X."))
async def cmd_mediaspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    rm = message.reply_to_message
    if not rm or not (rm.photo or rm.video):
        return await safe_reply(message, font("⚠️ Reply to a photo or video with `!mediaspm`"), parse_mode=ParseMode.MARKDOWN)
    file_id = rm.photo[-1].file_id if rm.photo else rm.video.file_id
    mtype = "photo" if rm.photo else "video"
    task_id = str(uuid.uuid4())[:8]
    active_menus[task_id] = {"cmd": "mediaspm", "type": mtype, "chat_id": message.chat.id, "payload": file_id, "selected": set()}
    await message.reply(font("🖼️ **MEDIA SPAM MENU**\nSelect bots:"), reply_markup=get_selector_keyboard(task_id), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("voicespm", prefix="-/!X."))
@dp.channel_post(Command("voicespm",prefix="-/!X."))
async def cmd_voicespm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message or not message.reply_to_message.voice:
        return await safe_reply(message, font("⚠️ Reply to a voice note with `!voicespm`"), parse_mode=ParseMode.MARKDOWN)
    task_id = str(uuid.uuid4())[:8]
    active_menus[task_id] = {"cmd": "voicespm", "type": "", "chat_id": message.chat.id, "payload": message.reply_to_message.voice.file_id, "selected": set()}
    await message.reply(font("🎤 **VOICE SPAM MENU**\nSelect bots:"), reply_markup=get_selector_keyboard(task_id), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dpfp", prefix="-/!X."))
@dp.channel_post(Command("dpfp",prefix="-/!X."))
async def cmd_dpfp(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in pfp_tasks: del pfp_tasks[message.chat.id]; await safe_reply(message, font("🛑 PFP loops stopped."))

@dp.message(Command("dstickerspm", prefix="-/!X."))
@dp.channel_post(Command("dstickerspm",prefix="-/!X."))
async def cmd_dstickerspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in sticker_spm_tasks: del sticker_spm_tasks[message.chat.id]; await safe_reply(message, font("🛑 Sticker SPM stopped."))

@dp.message(Command("dgifspm", prefix="-/!X."))
@dp.channel_post(Command("dgifspm",prefix="-/!X."))
async def cmd_dgifspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in gif_spm_tasks: del gif_spm_tasks[message.chat.id]; await safe_reply(message, font("🛑 GIF SPM stopped."))

@dp.message(Command("dmediaspm", prefix="-/!X."))
@dp.channel_post(Command("dmediaspm",prefix="-/!X."))
async def cmd_dmediaspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in media_spm_tasks: del media_spm_tasks[message.chat.id]; await safe_reply(message, font("🛑 Media SPM stopped."))

@dp.message(Command("dvoicespm", prefix="-/!X."))
@dp.channel_post(Command("dvoicespm",prefix="-/!X."))
async def cmd_dvoicespm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in voice_spm_tasks: del voice_spm_tasks[message.chat.id]; await safe_reply(message, font("🛑 Voice SPM stopped."))

@dp.message(Command("delaypfp", prefix="-/!X."))
@dp.channel_post(Command("delaypfp",prefix="-/!X."))
async def cmd_delaypfp(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    try:
        if not command.args: raise ValueError
        val = int(command.args)
        pfp_delays[message.chat.id] = max(10, val)
        await safe_reply(message, font("✅ PFP delay set."))
    except Exception: pass

@dp.message(Command("delaygcspm", prefix="-/!X."))
@dp.channel_post(Command("delaygcspm",prefix="-/!X."))
async def cmd_delaygcspm(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    try:
        if not command.args: raise ValueError
        val = int(command.args)
        spm_delays[message.chat.id] = max(10, val)
        await safe_reply(message, font("✅ SPM delay set."))
    except Exception: pass

@dp.message(Command("targetslide", prefix="-/!X."))
@dp.channel_post(Command("targetslide",prefix="-/!X."))
async def cmd_targetslide(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, name = await get_target_info(message, command.args)
    if not uid: return await safe_reply(message, font("⚠️ Reply to a message or tag a user"), parse_mode=ParseMode.MARKDOWN)
    
    targetslide_targets[uid] = name 
    save_db()
    await safe_reply(message, font(f"🎯 Target Slide locked onto user [{name}](tg://user?id={uid})!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dtargetslide", prefix="-/!X."))
@dp.channel_post(Command("dtargetslide",prefix="-/!X."))
async def cmd_dtargetslide(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, _ = await get_target_info(message, command.args)
    if not uid: return await safe_reply(message, font("⚠️ Reply to a message or tag a user"), parse_mode=ParseMode.MARKDOWN)
    
    if uid in targetslide_targets: 
        del targetslide_targets[uid]
        save_db()
    await safe_reply(message, font("🛑 Target Slide loop stopped for user."))

@dp.message(Command("slidespam", prefix="-/!X."))
@dp.channel_post(Command("slidespam",prefix="-/!X."))
async def cmd_slidespam(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message: return await safe_reply(message, font("⚠️ Reply to a message"), parse_mode=ParseMode.MARKDOWN)
    uid = message.reply_to_sender_id(message)
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xslidespam <text>`", parse_mode=ParseMode.MARKDOWN)
    if uid not in slidespam_tasks: slidespam_tasks[uid] = []
    for i, b in enumerate(bots):
        task_id = str(uuid.uuid4())
        slidespam_tasks[uid].append(task_id)
        spawn(delayed_task(i * 0.15, spm_sender(b, message.chat.id, message.reply_to_message.message_id, command.args, spm_delays, slidespam_tasks, uid, task_id)))
    await safe_reply(message, font("💥 SlideSpam locked on message!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dslidespam", prefix="-/!X."))
@dp.channel_post(Command("dslidespam",prefix="-/!X."))
async def cmd_dslidespam(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not message.reply_to_message: return await safe_reply(message, font("⚠️ Reply to a message"), parse_mode=ParseMode.MARKDOWN)
    uid = message.reply_to_sender_id(message)
    if uid in slidespam_tasks: del slidespam_tasks[uid]
    await safe_reply(message, font("🛑 SlideSpam loop stopped."))

@dp.message(Command("spm", prefix="-/!X."))
@dp.channel_post(Command("spm",prefix="-/!X."))
async def cmd_spm(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xspm <text>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in spm_loop_tasks: spm_loop_tasks[chat_id] = []
    for i, b in enumerate(bots):
        task_id = str(uuid.uuid4())
        spm_loop_tasks[chat_id].append(task_id)
        spawn(delayed_task(i * 0.15, spm_sender(b, chat_id, None, command.args, spm_delays, spm_loop_tasks, chat_id, task_id)))
    await safe_reply(message, font("✅ SPM loop started."), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dspm", prefix="-/!X."))
@dp.channel_post(Command("dspm",prefix="-/!X."))
async def cmd_dspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in spm_loop_tasks: del spm_loop_tasks[message.chat.id]
    await safe_reply(message, font("🛑 SPM loops stopped in this chat."))

@dp.message(Command("rspm", prefix="-/!X."))
@dp.channel_post(Command("rspm",prefix="-/!X."))
async def cmd_rspm(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xrspm <name>`", parse_mode=ParseMode.MARKDOWN)
    chat_id = message.chat.id
    if chat_id not in rspm_tasks: rspm_tasks[chat_id] = []
    for i, b in enumerate(bots):
        task_id = str(uuid.uuid4())
        rspm_tasks[chat_id].append(task_id)
        spawn(delayed_task(i * 0.15, rspm_sender(b, chat_id, command.args.strip(), rspm_tasks, task_id)))
    await safe_reply(message, font(f"🔥 RSPM (Raid Spam) loop started for `{command.args.strip()}`!"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("drspm", prefix="-/!X."))
@dp.channel_post(Command("drspm",prefix="-/!X."))
async def cmd_drspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in rspm_tasks: del rspm_tasks[message.chat.id]
    await safe_reply(message, font("🛑 RSPM loops stopped in this chat."))

@dp.message(Command("delayrspm", prefix="-/!X."))
@dp.channel_post(Command("delayrspm",prefix="-/!X."))
async def cmd_delayrspm(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    try:
        if not command.args: raise ValueError
        val = int(command.args)
        rspm_delays[message.chat.id] = max(10, val)
        await safe_reply(message, font("✅ RSPM delay set."))
    except Exception: pass

@dp.message(Command("dallspm", prefix="-/!X."))
@dp.channel_post(Command("dallspm",prefix="-/!X."))
async def cmd_dallspm(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    spm_loop_tasks.clear()
    rspm_tasks.clear()
    await safe_reply(message, font("🛑 All SPM loops stopped (globally)."))

@dp.message(Command("swipe", prefix="-/!X."))
@dp.channel_post(Command("swipe",prefix="-/!X."))
async def cmd_swipe(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not command.args: return await safe_reply(message, font("⚠️ Usage: ") + "`Xswipe <name>`", parse_mode=ParseMode.MARKDOWN)
    swipe_mode[message.chat.id] = command.args.strip()
    await safe_reply(message, font("⚡ Swipe Mode ON"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("dswipe", prefix="-/!X."))
@dp.channel_post(Command("dswipe",prefix="-/!X."))
async def cmd_dswipe(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.chat.id in swipe_mode: del swipe_mode[message.chat.id]
    await safe_reply(message, font("🛑 Swipe Mode stopped."))

@dp.message(Command("replylost", prefix="-/!X."))
@dp.channel_post(Command("replylost",prefix="-/!X."))
async def cmd_replylost(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, _ = await get_target_info(message, command.args)
    if not uid: return await safe_reply(message, font("⚠️ Reply or tag a user"), parse_mode=ParseMode.MARKDOWN)
    reply_lost_targets.add(uid)
    save_db()
    await safe_reply(message, font("💬 ReplyLost enabled for this user."))

@dp.message(Command("dreplylost", prefix="-/!X."))
@dp.channel_post(Command("dreplylost",prefix="-/!X."))
async def cmd_dreplylost(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, _ = await get_target_info(message, command.args)
    if not uid: return await safe_reply(message, font("⚠️ Reply or tag a user"), parse_mode=ParseMode.MARKDOWN)
    if uid in reply_lost_targets: 
        reply_lost_targets.remove(uid)
        save_db()
    await safe_reply(message, font("🛑 ReplyLost stopped for this user."))

# ==========================================
# NEW FEATURE: AUTO-REACT TO USER MESSAGES
# ==========================================
@dp.message(Command("react", prefix="!/"))
@dp.channel_post(Command("react",prefix="-/!X."))
async def cmd_react(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    
    if not message.reply_to_message:
        return await safe_reply(message, font("⚠️ Please reply to the user you want to auto-react to!"))
    
    uid = message.reply_to_sender_id(message)
    name = message.reply_to_sender_name(message)
    emoji = command.args.strip() if command.args else ""
    
    if emoji not in VALID_REACTS:
        allowed = ", ".join(VALID_REACTS)
        return await safe_reply(message, font(f"❌ Invalid emoji! Please use one of the allowed emojis:\n{allowed}"))
        
    react_targets[uid] = emoji
    save_db()
    await safe_reply(message, font(f"✅ Auto-react mode started for {name} with emoji {emoji}!"))

@dp.message(Command("dreact", prefix="!/"))
@dp.channel_post(Command("dreact",prefix="-/!X."))
async def cmd_dreact(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    
    if not message.reply_to_message:
        return await safe_reply(message, font("⚠️ Please reply to the user!"))
        
    uid = message.reply_to_sender_id(message)
    if uid in react_targets:
        del react_targets[uid]
        save_db()
    
    await safe_reply(message, font("🛑 Auto-react stopped for this user."))

@dp.message(Command("addsudo", prefix="-/!X."))
@dp.channel_post(Command("addsudo",prefix="-/!X."))
async def cmd_addsudo(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_owner(sender_id(message)): return await safe_reply(message, font("❌ Only OWNER can do this."))
    uid, name = await get_target_info(message, command.args)
    if uid:
        SUDO_USERS.add(uid)
        save_sudo()
        await safe_reply(message, font(f"👑 `{name}` (`{uid}`) added as SUDO ✅"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("delsudo", prefix="-/!X."))
@dp.channel_post(Command("delsudo",prefix="-/!X."))
async def cmd_delsudo(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_owner(sender_id(message)): return await safe_reply(message, font("❌ Only OWNER can do this."))
    uid, name = await get_target_info(message, command.args)
    if uid and uid in SUDO_USERS:
        SUDO_USERS.remove(uid)
        save_sudo()
        await safe_reply(message, font(f"🗑 `{name}` (`{uid}`) removed from SUDO ❌"), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("listsudo", prefix="-/!X."))
@dp.channel_post(Command("listsudo",prefix="-/!X."))
async def cmd_listsudo(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    
    sudo_list = []
    for u in SUDO_USERS:
        name = user_names.get(u, "Admin")
        sudo_list.append(f"• [{name}](tg://user?id={u}) (`{u}`)")
        
    await safe_reply(message, font("👑 SUDO Users:\n\n") + "\n".join(sudo_list), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("mute", prefix="-/!X."))
@dp.channel_post(Command("mute",prefix="-/!X."))
async def cmd_mute(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, name = await get_target_info(message, command.args)
    if uid:
        muted_users.add(uid)
        save_db()
        await safe_reply(message, font(f"🔇 User [{name}](tg://user?id={uid}) muted."), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("unmute", prefix="-/!X."))
@dp.channel_post(Command("unmute",prefix="-/!X."))
async def cmd_unmute(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, name = await get_target_info(message, command.args)
    if uid and uid in muted_users:
        muted_users.remove(uid)
        save_db()
        await safe_reply(message, font(f"🔊 User [{name}](tg://user?id={uid}) unmuted."), parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("mutelist", prefix="-/!X."))
@dp.channel_post(Command("mutelist",prefix="-/!X."))
async def cmd_mutelist(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not muted_users: return await safe_reply(message, font("📭 No muted users."))
    
    mute_list = []
    for u in muted_users:
        name = user_names.get(u, "Muted User")
        mute_list.append(f"• [{name}](tg://user?id={u}) (`{u}`)")
        
    await safe_reply(message, font("🔇 Muted Users:\n\n") + "\n".join(mute_list), parse_mode=ParseMode.MARKDOWN)

async def set_admin(bot, chat_id, uid, promote_all=True):
    return await bot.promote_chat_member(
        chat_id=chat_id, user_id=uid, is_anonymous=False,
        can_change_info=promote_all, can_delete_messages=promote_all,
        can_invite_users=promote_all, can_restrict_members=promote_all,
        can_pin_messages=promote_all, can_promote_members=promote_all,
        can_manage_chat=promote_all, can_manage_video_chats=promote_all
    )

@dp.message(Command("promote", prefix="-/!X."))
@dp.channel_post(Command("promote",prefix="-/!X."))
async def cmd_promote(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, _ = await get_target_info(message, command.args)
    if not uid: return
    try:
        await set_admin(bot, message.chat.id, uid, True)
        await safe_reply(message, font("✅ Promoted successfully."))
    except Exception as e:
        await safe_reply(message, font(f"❌ Error: {e}"))

@dp.message(Command("demote", prefix="-/!X."))
@dp.channel_post(Command("demote",prefix="-/!X."))
async def cmd_demote(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    uid, _ = await get_target_info(message, command.args)
    if not uid: return
    try:
        await set_admin(bot, message.chat.id, uid, False)
        await safe_reply(message, font("🛑 Demoted."))
    except Exception: pass

@dp.message(Command("promoteallbots", prefix="-/!X."))
@dp.channel_post(Command("promoteallbots",prefix="-/!X."))
async def cmd_promoteallbots(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    s = 0
    for b in bots:
        try:
            await set_admin(b, message.chat.id, b.id, True)
            s += 1
        except Exception: pass
    await safe_reply(message, font(f"🤖 Promoted {s} bots."))

@dp.message(Command("promoteall", prefix="-/!X."))
@dp.channel_post(Command("promoteall",prefix="-/!X."))
async def cmd_promoteall(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    s = 0
    for uid in list(known_users):
        try:
            await set_admin(bot, message.chat.id, uid, True)
            s += 1
        except Exception: pass
    await safe_reply(message, font(f"✅ Promoted {s} users."))

# ====================== GLOBAL ADMIN (SAVED CHATS) ======================
def _saved_groups():
    """Saved chats me se sirf groups/channels (negative ids)."""
    return [cid for cid in list(known_chats) if isinstance(cid, int) and cid < 0]


async def _bot_for_chat(chat_id, fallback):
    """Us chat ka leader bot lo, warna jis bot ne command diya wahi."""
    try:
        leader = await get_group_leader(chat_id)
        if leader:
            return leader
    except Exception:
        pass
    return fallback


async def _global_admin_action(message: types.Message, command: CommandObject, bot: Bot, promote: bool):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    uid, name = await get_target_info(message, command.args)
    if not uid:
        verb = "gpromote" if promote else "gdemote"
        return await safe_reply(message, font(f"⚠️ Reply to a user or use !{verb} <user_id>"))

    groups = _saved_groups()
    if not groups:
        return await safe_reply(message, font("⚠️ No saved chats yet."))

    ok = fail = 0
    failed_ids = []
    for cid in groups:
        target_bot = await _bot_for_chat(cid, bot)
        try:
            await set_admin(target_bot, cid, uid, promote)
            ok += 1
        except Exception:
            fail += 1
            if len(failed_ids) < 5:
                failed_ids.append(cid)
        await asyncio.sleep(0.12)

    label = "Promoted" if promote else "Demoted"
    icon = "✅" if ok else "❌"
    txt = f"{icon} {label} {name or uid} in {ok}/{len(groups)} saved chats."
    if fail:
        txt += f"\n⚠️ Failed in {fail} chat(s)" + (f": {failed_ids}" if failed_ids else "")
    await safe_reply(message, font(txt))


@dp.message(Command("gpromote", prefix="-/!X."))
@dp.channel_post(Command("gpromote", prefix="-/!X."))
async def cmd_gpromote(message: types.Message, command: CommandObject, bot: Bot):
    """Reply/tag karo -> saare saved chats me admin bana do."""
    await _global_admin_action(message, command, bot, True)


@dp.message(Command("gdemote", prefix="-/!X."))
@dp.channel_post(Command("gdemote", prefix="-/!X."))
async def cmd_gdemote(message: types.Message, command: CommandObject, bot: Bot):
    """Reply/tag karo -> saare saved chats me admin hata do."""
    await _global_admin_action(message, command, bot, False)


@dp.message(Command("gleave", prefix="-/!X."))
@dp.channel_post(Command("gleave", prefix="-/!X."))
async def cmd_gleave(message: types.Message, command: CommandObject, bot: Bot):
    """Saare saved chats se saare bots leave kar dein (!gleave confirm)."""
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    groups = _saved_groups()
    if not groups:
        return await safe_reply(message, font("⚠️ No saved chats yet."))

    arg = (command.args or "").strip().lower()
    if arg not in ("confirm", "yes", "y"):
        return await safe_reply(
            message,
            font(f"⚠️ All bots will leave {len(groups)} saved chats.\nType !gleave confirm to proceed."),
        )

    left = skip = 0
    for cid in groups:
        for b in bots:
            try:
                await b.leave_chat(cid)
                left += 1
            except Exception:
                skip += 1
        await asyncio.sleep(0.2)
    await safe_reply(message, font(f"👋 Left {left} chat(s)." + (f" ({skip} skipped)" if skip else "")))


# ====================== GLOBAL NC / SPAM LOOPS (SAVED CHATS) ======================
async def _global_start_loop(message: types.Message, command: CommandObject, bot: Bot,
                             tasks_dict, worker, usage_name: str, label: str):
    """Ek hi command se saare saved chats me loop start karo."""
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    if not command.args:
        return await safe_reply(message, font("⚠️ Usage: ") + f"`X{usage_name} <text>`", parse_mode=ParseMode.MARKDOWN)

    groups = _saved_groups()
    if not groups:
        return await safe_reply(message, font("⚠️ No saved chats yet."))

    text_arg = command.args.strip()
    started = 0
    for cid in groups:
        if cid not in tasks_dict:
            tasks_dict[cid] = {}
        for b in bots:
            task_id = str(uuid.uuid4())
            tasks_dict[cid][b.id] = task_id
            spawn(worker(b, cid, text_arg, task_id))
        started += 1
        await asyncio.sleep(0.15)

    await safe_reply(message, font(f"{label} started in {started} saved chats."))


@dp.message(Command("gnc", prefix="-/!X."))
@dp.channel_post(Command("gnc", prefix="-/!X."))
async def cmd_gnc(message: types.Message, command: CommandObject, bot: Bot):
    """!gnc <name> -> saare saved chats me normal name-change loop."""
    await _global_start_loop(message, command, bot, group_tasks, nc_loop_worker,
                             "gnc", "🔄 Text NC loop")


@dp.message(Command("glostnc", prefix="-/!X."))
@dp.channel_post(Command("glostnc", prefix="-/!X."))
async def cmd_glostnc(message: types.Message, command: CommandObject, bot: Bot):
    """!glostnc <name> -> saare saved chats me LOST name-change loop."""
    await _global_start_loop(message, command, bot, keng_tasks, keng_loop_worker,
                             "glostnc", "🔺 LOST NC loop")


@dp.message(Command("gemo", prefix="-/!X."))
@dp.channel_post(Command("gemo", prefix="-/!X."))
async def cmd_gemo(message: types.Message, command: CommandObject, bot: Bot):
    """!gemo <text> -> saare saved chats me emoji name-change loop."""
    await _global_start_loop(message, command, bot, group_tasks, emo_loop_worker,
                             "gemo", "🔄 Emoji NC loop")


@dp.message(Command("gbignc", prefix="-/!X."))
@dp.channel_post(Command("gbignc", prefix="-/!X."))
async def cmd_gbignc(message: types.Message, command: CommandObject, bot: Bot):
    """!gbignc <name> -> saare saved chats me BIG NC loop."""
    await _global_start_loop(message, command, bot, bignc_tasks, bignc_worker,
                             "gbignc", "🔺 BIG NC loop")


@dp.message(Command("gdelaync", prefix="-/!X."))
@dp.channel_post(Command("gdelaync", prefix="-/!X."))
async def cmd_gdelaync(message: types.Message, command: CommandObject, bot: Bot):
    """!gdelaync <ms> -> saare saved chats ka name-change delay set karo."""
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    try:
        if not command.args: raise ValueError
        val = max(10, int(command.args.strip()))
    except Exception:
        return await safe_reply(message, font("❌ Invalid number. Usage: !gdelaync 150"))

    groups = _saved_groups()
    if not groups:
        return await safe_reply(message, font("⚠️ No saved chats yet."))

    for cid in groups:
        nc_delays[cid] = val
    await safe_reply(message, font(f"✅ Name change delay set to {val} ms for {len(groups)} saved chats."))


async def _global_nc_title_start(message: types.Message, command: CommandObject, bot: Bot,
                                 tasks_dict, worker, cmd_name: str, label: str):
    """Reply/naam se target lo aur saare saved chats me title-loop start karo."""
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return

    args = (command.args or "").split()
    target, pinned = None, ""
    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_sender_name(message)
        if args:
            pinned = args[0].strip()
    elif args:
        target = args[0].strip()
        if len(args) > 1:
            pinned = args[1].strip()

    if not target:
        return await safe_reply(message, font("⚠️ Reply to a user or use ") + f"`X{cmd_name} <name> [emoji]`",
                                parse_mode=ParseMode.MARKDOWN)

    groups = _saved_groups()
    if not groups:
        return await safe_reply(message, font("⚠️ No saved chats yet."))

    started = 0
    for cid in groups:
        if cid not in tasks_dict:
            tasks_dict[cid] = {}
        for b in bots:
            task_id = str(uuid.uuid4())
            tasks_dict[cid][b.id] = task_id
            spawn(worker(b, cid, target, task_id, pinned))
        started += 1
        await asyncio.sleep(0.15)

    await safe_reply(message, font(f"{label} started in {started} saved chats for `{target}`."),
                     parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("gbaapnc", prefix="-/!X."))
@dp.channel_post(Command("gbaapnc", prefix="-/!X."))
async def cmd_gbaapnc(message: types.Message, command: CommandObject, bot: Bot):
    """!gbaapnc <name> [emoji] -> BAAP NC saare saved chats me."""
    await _global_nc_title_start(message, command, bot, baapnc_tasks, baapnc_loop_worker,
                                 "gbaapnc", "🔥 BAAP NC loop")


@dp.message(Command("gkengnc", prefix="-/!X."))
@dp.channel_post(Command("gkengnc", prefix="-/!X."))
async def cmd_gkengnc(message: types.Message, command: CommandObject, bot: Bot):
    """!gkengnc <name> [emoji] -> KENG NC saare saved chats me."""
    await _global_nc_title_start(message, command, bot, kengnc_tasks, kengnc_loop_worker,
                                 "gkengnc", "🔮 KENG NC loop")


@dp.message(Command("getlink", prefix="-/!X."))
@dp.channel_post(Command("getlink",prefix="-/!X."))
async def cmd_getlink(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    try:
        cid = int(command.args.strip())
        invite = await bot.export_chat_invite_link(cid)
        await safe_reply(message, font(f"🩷🫧 Invite link:\n{invite}"), parse_mode=ParseMode.MARKDOWN)
    except Exception: pass

@dp.message(Command("getallactivelinks", prefix="-/!X."))
@dp.channel_post(Command("getallactivelinks",prefix="-/!X."))
async def cmd_getallactivelinks(message: types.Message, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if not known_chats: return await safe_reply(message, font("⚠️ No known chats yet."))
    links = []
    for cid in list(known_chats):
        if cid > 0: continue
        try:
            invite = await bot.export_chat_invite_link(cid)
            links.append(f"• **{cid}**: {invite}")
        except Exception: pass
    txt = "\n".join(links) if links else font("❌ Could not generate any links.")
    await safe_reply(message, font("🔗 **Active Group Links:**\n\n") + txt, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

# ====================== NEW BROADCAST COMMAND ======================
@dp.message(Command("broadcast", prefix="-/!X."))
@dp.channel_post(Command("broadcast",prefix="-/!X."))
async def cmd_broadcast(message: types.Message, command: CommandObject, bot: Bot):
    leader = await get_group_leader(message.chat.id)
    if not leader or bot.id != leader.id: return
    if not is_sudo(sender_id(message)): return
    if message.reply_to_message:
        target = message.reply_to_message
        is_copy = True
    else:
        if not command.args:
            return await safe_reply(message, font("⚠️ Usage: !broadcast <text> or reply to photo/sticker/media"), parse_mode=ParseMode.MARKDOWN)
        target_text = command.args.strip()
        is_copy = False

    count = 0
    groups = [cid for cid in known_chats if cid < 0]
    for cid in groups:
        try:
            if is_copy:
                await bot.copy_message(chat_id=cid, from_chat_id=target.chat.id, message_id=target.message_id)
            else:
                await bot.send_message(cid, target_text)
            count += 1
        except Exception as e:
            _log_debug(f"broadcast failed for {cid}: {e}")
    await safe_reply(message, font(f"📣 **BROADCAST COMPLETE**\n✅ Sent to {count}/{len(groups)} groups!"), parse_mode=ParseMode.MARKDOWN)
# ===================================================================

@dp.callback_query(F.data.startswith("tk_"))
async def callback_query_handler(query: types.CallbackQuery, bot: Bot):
    if not is_sudo(query.from_user.id):
        return await query.answer(font("❌ You are not SUDO/Owner."), show_alert=True)
    
    data = query.data.split("_")
    task_id = data[1]
    action = data[2]
    menu = active_menus.get(task_id)
    if not menu:
        return await query.answer(font("❌ Menu expired or task already running."), show_alert=True)
    
    try:
        if action == "tgl":
            idx = int(data[3])
            if idx in menu['selected']: menu['selected'].remove(idx)
            else: menu['selected'].add(idx)
            await bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=get_selector_keyboard(task_id))
            await query.answer()
        elif action == "all":
            menu['selected'] = set(range(len(bots)))
            await bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=get_selector_keyboard(task_id))
            await query.answer()
        elif action == "none":
            menu['selected'].clear()
            await bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=get_selector_keyboard(task_id))
            await query.answer()
        elif action == "start":
            if not menu['selected']:
                return await query.answer(font("⚠️ Select at least one bot!"), show_alert=True)
            await query.answer(font("🚀 Firing tasks!"))
            await bot.edit_message_text(font(f"✅ Started **{menu['cmd'].upper()}** with {len(menu['selected'])} bots!"), chat_id=query.message.chat.id, message_id=query.message.message_id, parse_mode=ParseMode.MARKDOWN)
            for idx in menu['selected']:
                bt = bots[idx]
                run_id = str(uuid.uuid4())
                c_id = menu['chat_id']
                if menu['cmd'] == "pfp":
                    if c_id not in pfp_tasks: pfp_tasks[c_id] = []
                    pfp_tasks[c_id].append(run_id)
                    spawn(pfp_loop_worker(bt, c_id, run_id))
                elif menu['cmd'] == "stickerspm":
                    if c_id not in sticker_spm_tasks: sticker_spm_tasks[c_id] = []
                    sticker_spm_tasks[c_id].append(run_id)
                    spawn(media_spm_sender(bt, c_id, "sticker", menu['payload'], sticker_spm_tasks, run_id))
                elif menu['cmd'] == "gifspm":
                    if c_id not in gif_spm_tasks: gif_spm_tasks[c_id] = []
                    gif_spm_tasks[c_id].append(run_id)
                    spawn(media_spm_sender(bt, c_id, "gif", menu['payload'], gif_spm_tasks, run_id))
                elif menu['cmd'] == "mediaspm":
                    if c_id not in media_spm_tasks: media_spm_tasks[c_id] = []
                    media_spm_tasks[c_id].append(run_id)
                    spawn(media_spm_sender(bt, c_id, menu['type'], menu['payload'], media_spm_tasks, run_id))
                elif menu['cmd'] == "voicespm":
                    if c_id not in voice_spm_tasks: voice_spm_tasks[c_id] = []
                    voice_spm_tasks[c_id].append(run_id)
                    spawn(media_spm_sender(bt, c_id, "voice", menu['payload'], voice_spm_tasks, run_id))
            del active_menus[task_id]
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            await query.answer()

# (HIDDEN_ADMIN upar define hai)

@dp.message()
@dp.channel_post()
async def global_message_handler(message: types.Message, bot: Bot):
    chat_id = message.chat.id
    uid = sender_id(message)
    
    # 1. TRACKING (All bots do this to keep DB updated)
    if remember_chat(chat_id):
        try:
            save_db()   # naya chat -> "saved chats" me permanently add
        except Exception:
            pass
    remember_user(uid, sender_name(message), sender_username(message))

    # 2. MULTI-BOT REACTION (Every bot reacts if target matches)
    if uid in react_targets:
        try:
            emoji_to_react = react_targets[uid]
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(type='emoji', emoji=emoji_to_react)]
            )
        except Exception:
            pass

    # 3. LEADER CHECK (Only the leader handles the rest to avoid duplicate spam)
    leader = await get_group_leader(chat_id)
    if not leader or bot.id != leader.id: 
        return

    
    if uid in react_targets:
        try:
            emoji_to_react = react_targets[uid]
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(type='emoji', emoji=emoji_to_react)]
            )
        except Exception as e:
            _log_debug(f"reaction failed: {e}")

    if uid in reply_lost_targets and REPLY_LOST_TEXTS:
        try:
            await message.reply(random.choice(REPLY_LOST_TEXTS))
        except Exception: pass

    if uid in targetslide_targets and TARGET_SLIDE_TEXTS:
        target_name = targetslide_targets[uid]
        mention = f"[{target_name}](tg://user?id={uid})"
        text = random.choice(TARGET_SLIDE_TEXTS).replace("{name}", mention)
        try:
            await message.reply(text, parse_mode=ParseMode.MARKDOWN)
        except Exception: pass

    if chat_id in swipe_mode:
        name_arg = swipe_mode[chat_id]
        template = random.choice(SWIPE_TEXTS)
        try:
            await message.reply(template.replace("NAME", name_arg), parse_mode=ParseMode.MARKDOWN)
        except Exception: pass

def load_tokens() -> list:
    """Tokens: BOT_TOKENS env (comma/space) > hardcoded TOKENS. Deduped + validated."""
    raw = os.getenv("BOT_TOKENS", "").strip()
    source = raw if raw else ",".join(TOKENS)

    tokens, seen, invalid = [], set(), 0
    for chunk in re.split(r"[,\s]+", source):
        tok = chunk.strip()
        if not tok:
            continue
        if ":" not in tok or len(tok) < 20:
            invalid += 1
            continue
        if tok in seen:
            continue
        seen.add(tok)
        tokens.append(tok)

    if invalid:
        print(f"{RED}[TOKENS] {invalid} invalid token(s) skipped{RESET}")
    return tokens


async def _autosave_loop(interval: int = 120) -> None:
    """Har 2 minute me DB save — crash par data loss kam se kam."""
    while True:
        await asyncio.sleep(interval)
        try:
            save_db()
        except Exception as e:
            _log_debug(f"autosave failed: {e}")


async def _shutdown_cleanup() -> None:
    """Background tasks cancel + final save."""
    for task in list(BACKGROUND_TASKS):
        task.cancel()
    if BACKGROUND_TASKS:
        await asyncio.gather(*BACKGROUND_TASKS, return_exceptions=True)
    try:
        save_db()
        save_sudo()
    except Exception as e:
        _log_debug(f"final save failed: {e}")


async def _run_polling_forever() -> None:
    """Polling kabhi chhod ke exit na ho — conflict/network par backoff ke saath retry."""
    backoff = 5
    while True:
        try:
            await dp.start_polling(*bots, drop_pending_updates=True)
            print(f"{RED}[POLLING] stopped unexpectedly — restarting in {backoff}s{RESET}")
        except asyncio.CancelledError:
            await _shutdown_cleanup()
            raise
        except Exception as exc:
            msg = str(exc)
            print(f"{RED}[POLLING ERROR] {msg}{RESET}")
            if "Conflict" in msg or "terminated by other" in msg:
                print(f"{RED}[POLLING] Same token kisi doosre instance me chal raha hai — "
                      f"ek hi jagah chalao.{RESET}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        backoff = 5


async def main():
    print(f"\n{GREEN}⏳ INITIALIZING...{RESET}\n")

    tokens = load_tokens()
    if not tokens:
        print(f"{RED}❌ Koi valid bot token nahi mila. TOKENS list ya BOT_TOKENS env set karo.{RESET}")
        return

    bots.clear()
    bot_usernames.clear()
    for token in tokens:
        bots.append(Bot(token=token))

    connected = 0
    for b in bots:
        try:
            me = await b.get_me()
            bot_usernames.append(me.username)
            connected += 1
            print(f"{GREEN}✅ CONNECTED: @{me.username}{RESET}")
        except Exception as e:
            print(f"{RED}❌ Bot connect failed ({b.token.split(':')[0]}...): {e}{RESET}")

    if not connected:
        print(f"{RED}❌ Koi bot connect nahi hua — tokens check karo.{RESET}")
        return

    print(f"\n{GREEN}Lost V3 (PYTHON AIOGRAM) STARTED! bots={connected}/{len(bots)}{RESET}\n")

    spawn(_autosave_loop())
    await _run_polling_forever()


def _install_signal_handlers() -> None:
    """SIGTERM/SIGINT par clean shutdown (Railway/Render deploy friendly)."""
    def _handler(signum, frame):
        raise SystemExit(0)

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


if __name__ == "__main__":
    _install_signal_handlers()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"\n{RED}🛑 SHUTTING DOWN lost...{RESET}")
    except Exception as exc:
        print(f"{RED}FATAL: {exc}{RESET}")
    finally:
        try:
            save_db()
            save_sudo()
        except Exception:
            pass
