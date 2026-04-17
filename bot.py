import discord
from discord.ext import commands, tasks
from views import AcceptView, SellView, XISelect, PackSelectView, PackActionView, PackShopView, init_db
import sqlite3
import os
import random
import asyncio
import traceback
import time
import difflib
from datetime import datetime
from functools import wraps
from pathlib import Path
import ast
from PIL import Image, ImageDraw, ImageFont
from card_generator import generate_card, create_player_embed
from scorecard import score_embed, generate_final_scorecard_image
import io
from io import BytesIO
from players import players, price_by_ovr, get_price_by_ovr  # your players list and pricing
from match import Match
from types import SimpleNamespace

# ===== RESPONSE GUARD DECORATOR =====
# Prevents commands from sending multiple responses in a single invocation.
# Usage: @prevent_double_response on any command function.
def prevent_double_response(func):
    """Decorator to prevent a command from sending multiple responses."""
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        # Track response state on the context object
        ctx._response_sent = False
        original_send = ctx.send
        original_reply = getattr(ctx, "reply", None)
        
        async def guarded_send(*send_args, **send_kwargs):
            if not ctx._response_sent:
                await original_send(*send_args, **send_kwargs)
                ctx._response_sent = True
            # Silently ignore subsequent sends in the same command invocation
        
        async def guarded_reply(*reply_args, **reply_kwargs):
            if not ctx._response_sent:
                if original_reply:
                    await original_reply(*reply_args, **reply_kwargs)
                else:
                    await original_send(*reply_args, **reply_kwargs)
                ctx._response_sent = True
        
        ctx.send = guarded_send
        if original_reply:
            ctx.reply = guarded_reply
        try:
            return await func(ctx, *args, **kwargs)
        finally:
            # Restore original send/reply methods
            ctx.send = original_send
            if original_reply:
                ctx.reply = original_reply
    
    return wrapper

def parse_player_entries_from_source():
    source_path = Path(__file__).resolve().parent / "players.py"
    try:
        text = source_path.read_text(encoding='utf-8')
        module = ast.parse(text)
    except Exception:
        return [(key, players[key]) for key in players.keys()]

    entries = []
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "players":
                    if isinstance(node.value, ast.Dict):
                        for key_node, val_node in zip(node.value.keys, node.value.values):
                            try:
                                key = ast.literal_eval(key_node)
                                value = ast.literal_eval(val_node)
                                if isinstance(key, str) and isinstance(value, dict):
                                    entries.append((key, value))
                            except Exception:
                                continue
                    break
    if not entries:
        entries = [(key, players[key]) for key in players.keys()]
    else:
        for key, entry in entries:
            price = entry.get("price")
            if not isinstance(price, (int, float)):
                ovr_val = entry.get("ovr")
                if ovr_val is None:
                    ovr_val = int((entry.get("bat_ovr", 0) + entry.get("bowl_ovr", 0)) / 2)
                try:
                    ovr_val = int(ovr_val)
                except Exception:
                    ovr_val = 0
                entry["price"] = get_price_by_ovr(ovr_val, entry.get("category"))
    return entries

all_player_entries = parse_player_entries_from_source()
all_player_keys = [key for key, _ in all_player_entries]
all_players = [entry for _, entry in all_player_entries]


def normalize_player_name(name):
    if not isinstance(name, str):
        return ""
    return name.strip().lower()


def get_player_key_from_name(name):
    normalized = normalize_player_name(name)
    if not normalized:
        return None

    # Exact key or name match (case-sensitive)
    if normalized in players:
        return normalized

    # Case-insensitive key match
    normalized_key = normalized.replace(" ", "_")
    for key in players.keys():
        if key.lower() == normalized_key:
            return key

    # Find by display name
    for key, pdata in players.items():
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == normalized:
            return key

    # Try underscore/space alternates
    normalized_underscore = normalized.replace(" ", "_")
    if normalized_underscore in players:
        return normalized_underscore

    # Partial match
    for key, pdata in players.items():
        pdata_name = pdata.get("name", "").strip().lower()
        if normalized == pdata_name or normalized in pdata_name or pdata_name in normalized:
            return key

    return None


def get_player_display_name(player_name):
    """Get the display name for a player (e.g., 'Virat Kohli' instead of 'virat_kohli' or key)"""
    if not player_name:
        return player_name
    key = get_player_key_from_name(player_name)
    if key:
        return players[key].get("name", player_name)
    return player_name


def find_player_key_and_variant(name, category_hint=None):
    normalized = normalize_player_name(name)
    if not normalized:
        return None, None

    exact_matches = []
    for key, entry in all_player_entries:
        entry_name = entry.get("name", "").strip().lower()
        if normalized == key.lower() or normalized == entry_name:
            exact_matches.append((key, entry))

    if category_hint:
        category_hint = category_hint.upper()
        for key, entry in exact_matches:
            if entry.get("category", "").upper() == category_hint:
                return key, entry

        # Fallback: if no exact key/name match was found, search all exact display-name variants.
        for key, entry in all_player_entries:
            entry_name = entry.get("name", "").strip().lower()
            if entry_name == normalized and entry.get("category", "").upper() == category_hint:
                return key, entry
        return None, None

    if exact_matches:
        # Default to Normal (N) when no category hint is provided.
        # If the user explicitly types S, the category_hint branch above will return it.
        exact_matches.sort(key=lambda x: x[1].get("category", "N") == "S")
        return exact_matches[0]

    return None, None


def generate_fancy_stats_image(player_name, owner_name, value, potms, batting_data, bowling_data, card_img=None):
    # Constants
    width = 500
    stats_y_start = 210
    row_height = 40
    num_rows = 8
    
    # 1. Calculate required height dynamically
    # Space for header + stats + some padding
    stats_end_y = stats_y_start + 45 + (num_rows * row_height)
    
    if card_img:
        target_width = 480
        aspect_ratio = card_img.height / card_img.width
        target_height = int(target_width * aspect_ratio)
        # Final canvas = stats end + card height + bottom margin
        canvas_height = stats_end_y + target_height + 40 
    else:
        canvas_height = stats_end_y + 40

    # 2. Create Image
    bg_color = (18, 19, 21)
    img = Image.new('RGBA', (width, canvas_height), bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font_lg = ImageFont.truetype("Arial.ttf", 34)
        font_md = ImageFont.truetype("Arial.ttf", 22)
        font_sm = ImageFont.truetype("Arial.ttf", 18)
        font_bold = ImageFont.truetype("Arial.ttf", 24)
    except:
        font_lg = font_md = font_sm = font_bold = ImageFont.load_default()

    # --- Header ---
    draw.rounded_rectangle([15, 15, 485, 95], radius=15, fill=(32, 34, 37))
    draw.text((35, 35), f"Player Stats: {player_name}", fill=(255, 255, 255), font=font_lg)

    draw.text((25, 120), f"Owner: {owner_name}", fill=(160, 160, 160), font=font_md)
    draw.text((25, 160), f"Value: {value:,} CC", fill=(255, 215, 0), font=font_bold)
    draw.text((310, 160), f"POTM(s): {potms}", fill=(255, 255, 255), font=font_md)

    # --- Stats Tables ---
    def draw_stat_row(draw, x, y, label, val):
        draw.rounded_rectangle([x, y, x + 225, y + 34], radius=5, fill=(35, 39, 42))
        draw.text((x + 12, y + 7), label, fill=(190, 190, 190), font=font_sm)
        v_text = str(val)
        if hasattr(draw, "textlength"):
            w = draw.textlength(v_text, font=font_sm)
        elif hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), v_text, font=font_sm)
            w = bbox[2] - bbox[0]
        elif hasattr(font_sm, "getsize"):
            w = font_sm.getsize(v_text)[0]
        else:
            w = len(v_text) * 10
        draw.text((x + 225 - w - 12, y + 7), v_text, fill=(255, 255, 255), font=font_sm)

    bat_rows = [
        ("Innings", batting_data['inn']), ("Runs", batting_data['runs']),
        ("50s", batting_data['50s']), ("100s", batting_data['100s']),
        ("4s/6s", f"{batting_data['4s']}/{batting_data['6s']}"),
        ("Avg", f"{batting_data['avg']:.2f}"), ("SR", f"{batting_data['sr']:.2f}"),
        ("HS", batting_data['hs'])
    ]
    bowl_rows = [
        ("Innings", bowling_data['inn']), ("Wickets", bowling_data['wkts']),
        ("3-Fers", bowling_data['3w']), ("5-Fers", bowling_data['5w']),
        ("Hattricks", bowling_data['hat']), ("Avg", f"{bowling_data['avg']:.2f}"),
        ("Economy", f"{bowling_data['eco']:.2f}"), ("BBF", bowling_data['best'])
    ]

    # Section Labels
    draw.text((25, stats_y_start), "🏏 BATTING", fill=(255, 255, 255), font=font_bold)
    draw.text((260, stats_y_start), "🎯 BOWLING", fill=(255, 255, 255), font=font_bold)

    for i in range(num_rows):
        y_pos = stats_y_start + 40 + (i * row_height)
        draw_stat_row(draw, 20, y_pos, bat_rows[i][0], bat_rows[i][1])
        draw_stat_row(draw, 255, y_pos, bowl_rows[i][0], bowl_rows[i][1])

    # --- Card Overlay ---
    if card_img:
        card_resized = card_img.resize((target_width, target_height), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
        img.paste(card_resized, (10, stats_end_y + 10), card_resized if card_resized.mode == 'RGBA' else None)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def get_current_player_ovr(player_name):
    """Get player OVR dynamically from players.py"""
    key = get_player_key_from_name(player_name)
    if not key:
        return None
    ov = players.get(key, {}).get("ovr")
    return int(ov) if isinstance(ov, (int, float)) else None


def refresh_squad_ovr(userid):
    cursor.execute("SELECT rowid, player_key, ovr FROM squad WHERE userid=?", (userid,))
    rows = cursor.fetchall()
    updated = False
    for rowid, player_key, stored_ovr in rows:
        if player_key in players:
            current_ovr = players[player_key].get("ovr", 80)
            if current_ovr != stored_ovr:
                cursor.execute("UPDATE squad SET ovr=? WHERE rowid=?", (current_ovr, rowid))
                updated = True
    if updated:
        db.commit()


def get_squad_count(userid):
    cursor.execute("SELECT COUNT(*) FROM squad WHERE userid=?", (userid,))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_rank_position(user_id):
    cursor.execute("SELECT id FROM users ORDER BY points DESC, balance DESC, id ASC")
    rows = [row[0] for row in cursor.fetchall()]
    if user_id in rows:
        return rows.index(user_id) + 1
    return len(rows) + 1


def get_monthly_pack_info(rank):
    if rank == 1:
        return {
            "tier": "Top 1",
            "pack_type": "top1",
            "coins": 100000,
            "description": "5 players: 85-88, 80-83, 78-80, 80, 75"
        }
    if rank == 2:
        return {
            "tier": "Top 2",
            "pack_type": "top2",
            "coins": 60000,
            "description": "3 players: 85-88, 80, 80-82"
        }
    if rank == 3:
        return {
            "tier": "Top 3",
            "pack_type": "top3",
            "coins": 40000,
            "description": "2 players: 85-87, 82"
        }
    if 4 <= rank <= 10:
        return {
            "tier": "Top 4-10",
            "pack_type": "top4_10",
            "coins": 20000,
            "description": "1 player: 85-87"
        }
    return {
        "tier": "Rest",
        "pack_type": "rest",
        "coins": 0,
        "description": "1 player: 85"
    }


def format_seconds(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


# Global auction variables
auction_players = []
auction_active = False
auction_card = None
current_bid = 0
highest_bidder = None
last_bid_time = None
base_price = 0
auction_countdown_active = False
countdown_start_time = None
last_user_bid = {}
auction_results = []

# Auction Channel ID - Replace with your actual general channel ID
AUCTION_CHANNEL_ID = 1490665336943677502  # Put your channel id here

# Category IDs where this bot should tell users to use bot 1 and bot 2 for commands
BOT_COMMAND_CATEGORY_IDS = [
    1490663579781955644, #general
    1490659104648204419, #support
]

# Bot command channel IDs for clickable redirect mentions
BOT_COMMAND_CHANNEL_IDS = [
    1490662432442417304, #bot 1
    1490662511723286669, #bot 2
]

# Channel IDs for custom command restrictions
CHANNELS_EXCEPT_CCPLAY = [
    1490662432442417304, #bot 1
    1490662511723286669 #bot 2
]

CHANNELS_AUCTION_ONLY = [
    1490665336943677502
]

# IDs allowed to start auctions
AUCTION_STARTER_IDS = [
    1393453463173730394,
    1322917808438509664,
    907880181811773440
]

CHANNELS_EXCEPT_CCID_CCPLAY_CCJOIN = [
    1490662432442417304, #bot 1
    1490662511723286669, #bot 2
    1490663197185675345,
    1490663311967129710
]

intents = discord.Intents.all()
intents.message_content = True

# ====== Database Setup ======
db = sqlite3.connect("database.db")
cursor = db.cursor()

# Initialize views module with database connection
init_db(db, cursor)

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    teamname TEXT,
    balance INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS squad(
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    userid INTEGER,
    player_key TEXT,
    ovr INTEGER,
    category TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS xi(
    userid INTEGER,
    player TEXT,
    PRIMARY KEY (userid, player)
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS ccreward_claimed(
    userid INTEGER PRIMARY KEY
)
""")

# Table to permanently disable ccreward for users who cross 82 OVR
cursor.execute("""
CREATE TABLE IF NOT EXISTS ccreward_disabled(
    userid INTEGER PRIMARY KEY
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ccmonthly_claims(
    userid INTEGER PRIMARY KEY,
    last_claim INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS monthly_packs(
    pack_id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid INTEGER,
    name TEXT,
    tier TEXT,
    status TEXT DEFAULT 'unopened',
    created_at INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_inventory (
    inv_id INTEGER PRIMARY KEY AUTOINCREMENT,
    userid INTEGER,
    pack_type TEXT,
    pack_name TEXT
)
""")

# Drops table for cooldowns
cursor.execute("""
CREATE TABLE IF NOT EXISTS drops(
    userid INTEGER PRIMARY KEY,
    last_drop INTEGER
)
""")

# Daily rewards table for tracking streaks and claims
cursor.execute("""
CREATE TABLE IF NOT EXISTS daily_rewards(
    userid INTEGER PRIMARY KEY,
    last_claim INTEGER,
    streak INTEGER DEFAULT 0
)
""")

# Add points column for leaderboard tracking
try:
    cursor.execute("ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass  # Column already exists

# Rename squad column from player to player_key if exists
try:
    cursor.execute("ALTER TABLE squad RENAME COLUMN player TO player_key")
except sqlite3.OperationalError:
    pass  # Column already renamed

# Migrate squad player to player_key
cursor.execute("SELECT rowid, player_key FROM squad")
rows = cursor.fetchall()
for rowid, player in rows:
    if player not in players:  # it's a name, not key
        key = get_player_key_from_name(player)
        if key:
            cursor.execute("UPDATE squad SET player_key = ? WHERE rowid = ?", (key, rowid))
db.commit()

# Add category column for squad variants if missing
try:
    cursor.execute("ALTER TABLE squad ADD COLUMN category TEXT")
except sqlite3.OperationalError:
    pass  # Column already exists

cursor.execute("""
CREATE TABLE IF NOT EXISTS player_stats (
    player TEXT PRIMARY KEY,

    bat_innings INTEGER DEFAULT 0,
    bat_runs INTEGER DEFAULT 0,
    bat_balls INTEGER DEFAULT 0,
    bat_outs INTEGER DEFAULT 0,
    bat_50s INTEGER DEFAULT 0,
    bat_100s INTEGER DEFAULT 0,
    bat_best INTEGER DEFAULT 0,
    bat_best_notout INTEGER DEFAULT 0,

    bowl_innings INTEGER DEFAULT 0,
    bowl_balls INTEGER DEFAULT 0,
    bowl_wickets INTEGER DEFAULT 0,
    bowl_3w INTEGER DEFAULT 0,
    bowl_5w INTEGER DEFAULT 0,
    bowl_runs INTEGER DEFAULT 0,
    bowl_best_wkts INTEGER DEFAULT 0,
    bowl_best_runs INTEGER DEFAULT 999
)
""")

# Add bat_balls column if it doesn't exist
try:
    cursor.execute("ALTER TABLE player_stats ADD COLUMN bat_balls INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass  # Column already exists

# Add bowl_balls column if it doesn't exist
try:
    cursor.execute("ALTER TABLE player_stats ADD COLUMN bowl_balls INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass  # Column already exists

db.commit()

# Leaderboard point helper

def add_user_points(user_id, amount):
    if not isinstance(amount, int) or amount == 0:
        return
    cursor.execute(
        "UPDATE users SET points = COALESCE(points, 0) + ? WHERE id = ?",
        (amount, user_id)
    )
    db.commit()

# Price Logic
def get_base_price(ovr):
    if 78 <= ovr <= 82:
        return 10000
    if 83 <= ovr <= 85:
        return 40000
    if 86 <= ovr <= 88:
        return 100000
    if 89 <= ovr <= 90:
        return 300000
    if 91 <= ovr <= 93:
        return 600000
    if 94 <= ovr <= 95:
        return 1000000
    if 96 <= ovr <= 97:
        return 1500000
    if 98 <= ovr <= 99:
        return 2000000
    return 100000


def get_auction_minimum(ovr, category=None):
    """Return the auction starting bid based on card value percentage."""
    card_value = get_price_by_ovr(ovr, category)
    if card_value <= 0:
        return get_base_price(ovr)

    if str(category or "").upper() == "S":
        return max(1, (card_value * 60 + 99) // 100)

    return max(1, (card_value * 40 + 99) // 100)


def get_player_card_paths(player_key, player, player_id=None):
    paths = []

    image = player.get('image')
    if image:
        image_path = Path(image)
        if not image_path.is_absolute():
            image_path = Path(__file__).resolve().parent / image
        if image_path.exists() and str(image_path) not in paths:
            paths.append(str(image_path))

    try:
        if player_id is None:
            player_id = all_player_keys.index(player_key) if player_key in all_player_keys else 0
        generated_path = generate_card(player_id, player, player_key=player_key)
        if generated_path and generated_path not in paths:
            paths.append(generated_path)
    except Exception:
        pass

    return paths


def get_player_card_path(player_key, player):
    paths = get_player_card_paths(player_key, player)
    return paths[0] if paths else None


def get_player_variant_entries(player_key, player):
    target_name = player.get("name", "").strip().lower()
    if not target_name:
        return [(player_key, player)]

    variant_entries = [
        (key, entry)
        for key, entry in all_player_entries
        if entry.get("name", "").strip().lower() == target_name
    ]

    if not variant_entries:
        return [(player_key, player)]

    variant_entries.sort(key=lambda item: item[1].get("category", "S") == "S")
    return variant_entries


def get_player_variant_entries_with_id(player_key, player):
    target_name = player.get("name", "").strip().lower()
    if not target_name:
        exact_index = next((idx for idx, (key, entry) in enumerate(all_player_entries)
                            if key == player_key and entry == player), 0)
        return [(exact_index, player_key, player)]

    variant_entries = [
        (idx, key, entry)
        for idx, (key, entry) in enumerate(all_player_entries)
        if entry.get("name", "").strip().lower() == target_name
    ]

    if not variant_entries:
        exact_index = next((idx for idx, (key, entry) in enumerate(all_player_entries)
                            if key == player_key and entry == player), 0)
        return [(exact_index, player_key, player)]

    variant_entries.sort(key=lambda item: item[2].get("category", "S") == "S")
    return variant_entries


def get_player_variant_card_paths(player_key, player):
    variant_entries = get_player_variant_entries_with_id(player_key, player)
    paths = []
    seen = set()

    for variant_id, key, entry in variant_entries:
        card_paths = get_player_card_paths(key, entry, player_id=variant_id)
        if card_paths:
            first_path = card_paths[0]
            if first_path and first_path not in seen:
                seen.add(first_path)
                paths.append(first_path)

    return paths


def resolve_player_variant(player_key, player, desired_ovr=None):
    variant_entries = get_player_variant_entries_with_id(player_key, player)
    if not variant_entries:
        return (
            all_player_keys.index(player_key) if player_key in all_player_keys else 0,
            player_key,
            player
        )

    if desired_ovr is not None:
        for variant_id, variant_key, variant_player in variant_entries:
            if variant_player.get("ovr") == desired_ovr:
                return variant_id, variant_key, variant_player

    for variant_id, variant_key, variant_player in variant_entries:
        if player is not None and variant_player.get("category") == player.get("category"):
            return variant_id, variant_key, variant_player

    return variant_entries[0]


def get_player_variants_by_key(player_key):
    player = players.get(player_key)
    if player:
        return get_player_variant_entries_with_id(player_key, player)

    target_name = player_key.replace("_", " ").strip().lower()
    return [
        (idx, key, entry)
        for idx, (key, entry) in enumerate(all_player_entries)
        if entry.get("name", "").strip().lower() == target_name
    ]


def get_player_category_by_ovr(player_key, ovr):
    if player_key is None:
        return None
    for _, _, entry in get_player_variants_by_key(player_key):
        try:
            if int(entry.get("ovr", 0)) == int(ovr):
                return entry.get("category")
        except Exception:
            continue
    return players.get(player_key, {}).get("category")


def user_owns_player_category(user_id, player_key, category):
    if not category or not player_key:
        return False
    cursor.execute("SELECT category, ovr FROM squad WHERE userid=? AND player_key=?", (user_id, player_key))
    for cat, ovr in cursor.fetchall():
        if cat and cat.upper() == category.upper():
            return True
        if not cat and get_player_category_by_ovr(player_key, ovr) == category:
            return True
    return False


def user_owns_player_variant(user_id, player_key, category=None, ovr=None):
    if ovr is not None:
        cursor.execute(
            "SELECT 1 FROM squad WHERE userid=? AND player_key=? AND ovr=?",
            (user_id, player_key, ovr)
        )
        return cursor.fetchone() is not None
    if category:
        cursor.execute(
            "SELECT category, ovr FROM squad WHERE userid=? AND player_key=?",
            (user_id, player_key)
        )
        for cat, ovr in cursor.fetchall():
            if cat and cat.upper() == category.upper():
                return True
            if not cat and get_player_category_by_ovr(player_key, ovr) == category:
                return True
        return False
    cursor.execute("SELECT 1 FROM squad WHERE userid=? AND player_key=?", (user_id, player_key))
    return cursor.fetchone() is not None


def get_player_variant_entry(player_key, category=None, ovr=None):
    player_obj = players.get(player_key)
    if not player_obj:
        return None

    variant_entries = get_player_variant_entries_with_id(player_key, player_obj)
    if category:
        for _, _, entry in variant_entries:
            if entry.get("category", "").upper() == category.upper():
                return entry
    if ovr is not None:
        for _, _, entry in variant_entries:
            try:
                if int(entry.get("ovr", 0)) == int(ovr):
                    return entry
            except Exception:
                continue
    return variant_entries[0][2] if variant_entries else player_obj


def get_conflicting_player_keys(user_id):
    cursor.execute("SELECT player_key, ovr, category FROM squad WHERE userid=?", (user_id,))
    rows = cursor.fetchall()
    conflict_keys = {}
    for player_key, ovr, category in rows:
        if category:
            conflict_category = category.upper()
        else:
            conflict_category = get_player_category_by_ovr(player_key, ovr)
        if not conflict_category:
            continue
        conflict_keys.setdefault(player_key, set()).add(conflict_category)

    return [key for key, categories in conflict_keys.items() if "S" in categories and "N" in categories]


def build_card_files(card_paths):
    files = []
    for idx, path in enumerate(card_paths):
        if isinstance(path, str) and (path.startswith('http://') or path.startswith('https://')):
            continue
        files.append(discord.File(path, filename=f'card_{idx}.png'))
    return files


class CardNavigationView(discord.ui.View):
    def __init__(self, card_paths=None, embed=None, timeout=120):
        super().__init__(timeout=timeout)
        self.card_paths = card_paths or []
        self.card_index = 0
        self.embed = embed
        self.update_navigation_buttons()

        # Only show navigation buttons when there are multiple card variants.
        if len(self.card_paths) <= 1:
            if hasattr(self, 'prev_card'):
                try:
                    self.remove_item(self.prev_card)
                except Exception:
                    pass
            if hasattr(self, 'next_card'):
                try:
                    self.remove_item(self.next_card)
                except Exception:
                    pass

    def update_card_image(self):
        if not self.card_paths or not self.embed:
            return

        current_path = self.card_paths[self.card_index]
        if isinstance(current_path, str) and (current_path.startswith('http://') or current_path.startswith('https://')):
            self.embed.set_image(url=current_path)
        else:
            self.embed.set_image(url=f'attachment://card_{self.card_index}.png')

    def update_navigation_buttons(self):
        has_variants = len(self.card_paths) > 1
        if hasattr(self, 'prev_card'):
            self.prev_card.disabled = not has_variants
        if hasattr(self, 'next_card'):
            self.next_card.disabled = not has_variants
        if has_variants:
            page_label = f"({self.card_index+1}/{len(self.card_paths)})"
            if hasattr(self, 'prev_card'):
                self.prev_card.label = f"⬅️ Previous {page_label}"
            if hasattr(self, 'next_card'):
                self.next_card.label = f"Next ➡️ {page_label}"

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def prev_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.card_paths:
            await interaction.response.send_message("No additional card variants available.", ephemeral=True)
            return

        self.card_index = (self.card_index - 1) % len(self.card_paths)
        self.update_card_image()
        self.update_navigation_buttons()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.card_paths:
            await interaction.response.send_message("No additional card variants available.", ephemeral=True)
            return

        self.card_index = (self.card_index + 1) % len(self.card_paths)
        self.update_card_image()
        self.update_navigation_buttons()
        await interaction.response.edit_message(embed=self.embed, view=self)

# Select Random Auction Card

def get_random_card_by_range(min_ovr, max_ovr):
    eligible = [
        (name, data)
        for name, data in players.items()
        if min_ovr <= data.get("ovr", 0) <= max_ovr
    ]
    return random.choice(eligible) if eligible else None


def get_random_card():
    return random.choice(list(players.items())) if players else (None, None)

# Auction Scheduler
@tasks.loop(seconds=10)
async def auction_scheduler():
    global auction_countdown_active, countdown_start_time, auction_players, auction_active
    
    if not auction_countdown_active or countdown_start_time is None:
        return
    
    try:
        now = datetime.now()
        elapsed = (now - countdown_start_time).total_seconds()
        countdown_duration = 300  # 5 minutes
        
        # Check if countdown has finished
        if elapsed >= countdown_duration:
            auction_countdown_active = False
            countdown_start_time = None
            
            channel = bot.get_channel(AUCTION_CHANNEL_ID)
            if channel is None:
                return
            
            # Check if minimum players reached
            if len(auction_players) >= 3:
                await channel.send(f"✅ **Countdown finished!** {len(auction_players)} players joined. Starting auction...")
                await run_full_auction(channel)
            else:
                await channel.send(f"❌ **Countdown finished!** Only {len(auction_players)} players joined. Minimum 3 required. Auction cancelled.")
                auction_players.clear()
    except Exception as e:
        print(f"Error in auction_scheduler: {e}")
        auction_countdown_active = False
        countdown_start_time = None

@auction_scheduler.before_loop
async def before_auction_scheduler():
    await bot.wait_until_ready()

async def start_auction():
    global auction_active, auction_card, current_bid
    global highest_bidder, base_price, last_bid_time, auction_players

    # Prevent multiple auctions running simultaneously
    if auction_active:
        return

    channel = bot.get_channel(AUCTION_CHANNEL_ID)
    
    # Prevent crash if channel doesn't exist
    if channel is None:
        return

    # Clear and check player count
    if len(auction_players) < 3:
        await channel.send("❌ Auction cancelled. Not enough players.")
        auction_players.clear()
        return

    auction_active = True

    await channel.send("READY...")
    await asyncio.sleep(1)

    await channel.send("3")
    await asyncio.sleep(1)

    await channel.send("2")
    await asyncio.sleep(1)

    await channel.send("1")
    await asyncio.sleep(1)

    card = get_random_card()
    if not card or card[0] is None:
        await channel.send("❌ No auction card is available. Auction cancelled.")
        auction_active = False
        auction_players.clear()
        return

    name, data = card
    auction_card = name
    ovr = data.get("ovr", 0)
    category = data.get("category", "N")

    base_price = get_auction_minimum(ovr, category)
    current_bid = base_price
    highest_bidder = None

    last_bid_time = datetime.now()

    embed = discord.Embed(
        title="🏏 LIVE AUCTION",
        description=f"**{data.get('name', name.replace('_',' ').title())}**\nOVR: {ovr}\nCategory: **{data.get('category', 'N')}**",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="Base Price",
        value=f"{base_price:,} CC"
    )

    card_paths = get_player_variant_card_paths(name, data)
    view = AuctionView(
        card_paths=card_paths,
        embed=embed,
        auction_key=name,
        auction_ovr=ovr,
        auction_category=data.get("category", "N")
    )

    if card_paths:
        first_path = card_paths[0]
        files = build_card_files(card_paths)
        if isinstance(first_path, str) and (first_path.startswith("http://") or first_path.startswith("https://")):
            embed.set_image(url=first_path)
            await channel.send(embed=embed, view=view)
        else:
            try:
                embed.set_image(url="attachment://card_0.png")
                await channel.send(embed=embed, files=files, view=view)
            except Exception:
                await channel.send(embed=embed, view=view)
    else:
        await channel.send(embed=embed, view=view)

    bot.loop.create_task(check_auction_timeout(channel))

class AuctionView(CardNavigationView):
    def __init__(self, card_paths=None, embed=None, auction_key=None, auction_ovr=None, auction_category=None):
        self.auction_key = auction_key
        self.auction_ovr = auction_ovr
        self.auction_category = auction_category
        super().__init__(card_paths=card_paths, embed=embed, timeout=120)

    @discord.ui.button(label="Bid", style=discord.ButtonStyle.green)
    async def bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        global current_bid, highest_bidder, last_bid_time, last_user_bid

        if not auction_active:
            await interaction.response.send_message(
                "❌ Auction already ended.",
                ephemeral=True
            )
            return

        if interaction.user.id not in auction_players:
            await interaction.response.send_message(
                "You didn't join the auction.",
                ephemeral=True
            )
            return

        now = time.time()

        if interaction.user.id in last_user_bid:
            if now - last_user_bid[interaction.user.id] < 2:
                await interaction.response.send_message(
                    "⏳ Slow down! Wait before bidding again.",
                    ephemeral=True
                )
                return

        last_user_bid[interaction.user.id] = now

        try:
            cursor.execute(
                "SELECT COUNT(*) FROM squad WHERE userid=?",
                (interaction.user.id,)
            )
            squad_count = cursor.fetchone()[0]
            if squad_count >= 22:
                await interaction.response.send_message(
                    "❌ Your squad already has 22 or more players. You cannot bid in the auction.",
                    ephemeral=True
                )
                return

            if self.auction_key and self.auction_ovr is not None:
                if user_owns_player_variant(interaction.user.id, self.auction_key, ovr=self.auction_ovr):
                    await interaction.response.send_message(
                        "❌ You already own this exact auctioned variant.",
                        ephemeral=True
                    )
                    return

            cursor.execute(
                "SELECT balance FROM users WHERE id=?",
                (interaction.user.id,)
            )

            result = cursor.fetchone()
            if result is None:
                await interaction.response.send_message(
                    "You are not registered. Use ccdeb first.",
                    ephemeral=True
                )
                return

            balance = result[0]

            next_bid = current_bid + 10000

            # Allow bidding max balance if they can't afford normal increment
            if balance < next_bid:
                if balance > current_bid:
                    current_bid = balance
                else:
                    await interaction.response.send_message(
                        "Not enough CC.",
                        ephemeral=True
                    )
                    return
            else:
                current_bid = next_bid
            
            highest_bidder = interaction.user.id
            last_bid_time = datetime.now()

            await interaction.response.send_message(
                f"💰 {interaction.user.mention} bid **{current_bid:,} CC**!\n"
                f"👑 Highest bidder: <@{highest_bidder}>"
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error placing bid: {str(e)}",
                ephemeral=True
            )

    @discord.ui.button(label="Next Card", style=discord.ButtonStyle.secondary)
    async def next_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in auction_players:
            await interaction.response.send_message(
                "❌ You didn't join the auction.",
                ephemeral=True
            )
            return

        if not self.card_paths:
            await interaction.response.send_message(
                "No additional card variants available.",
                ephemeral=True
            )
            return

        self.card_index = (self.card_index + 1) % len(self.card_paths)
        self.update_card_image()
        button.label = f"Next Card ({self.card_index+1}/{len(self.card_paths)})"
        await interaction.response.edit_message(embed=self.embed, view=self)

async def run_single_auction(channel, name, data):
    global auction_active, auction_card, current_bid, highest_bidder, base_price, last_bid_time

    auction_card = name
    ovr = data.get("ovr", 0)
    category = data.get("category", "N")
    base_price = get_auction_minimum(ovr, category)
    current_bid = base_price
    highest_bidder = None
    last_bid_time = datetime.now()
    auction_active = True

    player_cat = data.get("category", "N")
    embed = discord.Embed(
        title="🏏 LIVE AUCTION",
        description=f"**{data.get('name', name.replace('_',' ').title())}**\nOVR: {ovr}\nCategory: **{player_cat}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="Base Price", value=f"{base_price:,} CC")

    # FIX: Get the specific card path for this variant only, avoiding extra attachments
    card_path = get_player_card_path(name, data)
    view = AuctionView(
        card_paths=[card_path] if card_path else [],
        embed=embed,
        auction_key=name,
        auction_ovr=ovr,
        auction_category=player_cat
    )

    if card_path:
        if isinstance(card_path, str) and (card_path.startswith('http://') or card_path.startswith('https://')):
            embed.set_image(url=card_path)
            await channel.send(embed=embed, view=view)
        else:
            # FIX: Send only the one correct image file to prevent "Base Card" overlays
            file = discord.File(card_path, filename="auction_card.png")
            embed.set_image(url="attachment://auction_card.png")
            await channel.send(embed=embed, file=file, view=view)
    else:
        await channel.send(embed=embed, view=view)

    winner, final_price = await wait_for_auction_end(channel)
    return winner, final_price

async def wait_for_auction_end(channel):
    global highest_bidder, last_bid_time

    start_time = datetime.now()

    while True:
        await asyncio.sleep(5)

        if highest_bidder:
            elapsed = (datetime.now() - last_bid_time).total_seconds()
        else:
            elapsed = (datetime.now() - start_time).total_seconds()

        if elapsed >= 60:
            return await finish_single_auction(channel)

async def check_auction_timeout(channel):
    global auction_active, highest_bidder, last_bid_time

    while auction_active:
        await asyncio.sleep(5)

        if highest_bidder:
            elapsed = (datetime.now() - last_bid_time).total_seconds()
        else:
            elapsed = 60

        if elapsed >= 60:
            await finish_single_auction(channel)
            break

# deprecated compatibility helper (uses single auction finish function)
# async def finish_single_auction(channel):
#     global auction_active
#     await finish_single_auction(channel)
#     auction_active = False
#     return highest_bidder


async def send_auction_results(channel):
    embed = discord.Embed(
        title="🏁 AUCTION RESULTS",
        color=discord.Color.green()
    )

    for result in auction_results:
        player = result["player"].replace("_", " ").title()
        category = result.get("category", "N")
        winner = result["winner"]
        price = result["price"]

        if winner:
            try:
                user = await bot.fetch_user(winner)
                name = user.name
            except Exception:
                name = f"<@{winner}>"

            value = f"👤 {name}\n💰 {price:,} CC"
        else:
            value = "❌ No bids"

        embed.add_field(
            name=f"{player} ({category})",
            value=value,
            inline=False
        )

    await channel.send(embed=embed)

async def run_full_auction(channel):
    global auction_active, auction_results

    auction_active = True
    auction_results = []

    ranges = [
        (78, 82),
        (83, 85),
        (86, 88),
        (89, 92),
        (91, 95)
    ]

    for min_ovr, max_ovr in ranges:
        await channel.send(f"🎯 **Next Player ({min_ovr}-{max_ovr} OVR)**")
        await asyncio.sleep(2)

        card = get_random_card_by_range(min_ovr, max_ovr)
        if not card:
            continue

        name, data = card

        winner, price = await run_single_auction(channel, name, data)

        auction_results.append({
            "player": name,
            "category": data.get("category", "N"),
            "winner": winner,
            "price": price
        })

        await asyncio.sleep(3)

    await send_auction_results(channel)

    auction_active = False
    auction_players.clear()

async def finish_single_auction(channel):
    global auction_active, current_bid, highest_bidder, auction_card

    auction_active = False
    winner_id = highest_bidder
    final_bid = current_bid

    if not winner_id:
        await channel.send(f"No bids placed for **{auction_card.replace('_',' ').title() if auction_card else 'this player'}**. Auction ended.")
        return None, 0

    try:
        cursor.execute("SELECT balance FROM users WHERE id=?", (winner_id,))
        result = cursor.fetchone()
        if not result or result[0] < final_bid:
            await channel.send("❌ Winner found but balance is insufficient. Auction cancelled.")
            return None, 0

        player_data = players[auction_card]
        player_ovr = player_data.get("ovr", 75)
        player_cat = player_data.get("category", "N")

        # FIX: Explicitly include 'category' in the INSERT to ensure 'S' cards are added correctly
        cursor.execute(
            "INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
            (winner_id, auction_card, player_ovr, player_cat)
        )
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id=?", (final_bid, winner_id))
        
        db.commit()
        add_user_points(winner_id, 3)

        winner_name = player_data.get('name', auction_card.replace('_',' ').title())
        embed = discord.Embed(
            title="🏆 AUCTION WINNER",
            description=f"<@{winner_id}> won **{winner_name} ({player_cat})** for **{final_bid:,} CC**!",
            color=discord.Color.green()
        )
        
        # Display the winning card image clearly
        card_path = get_player_card_path(auction_card, player_data)
        if card_path:
            if isinstance(card_path, str) and card_path.startswith('http'):
                embed.set_image(url=card_path)
                await channel.send(embed=embed)
            else:
                file = discord.File(card_path, filename="winner.png")
                embed.set_image(url="attachment://winner.png")
                await channel.send(embed=embed, file=file)
        else:
            await channel.send(embed=embed)

    except Exception as e:
        await channel.send(f"❌ Database Error: {str(e)}")
        db.rollback()
    finally:
        current_bid = 0
        highest_bidder = None
        auction_card = None
        base_price = 0

    return winner_id, final_bid

def get_prefix(bot, message):
    # no prefix, but ignore non-CC text and bots
    if message.author.bot:
        return None
    return ""

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

@bot.event
async def on_command_error(ctx, error):
    if getattr(ctx, "_response_sent", False):
        return
    if bot.is_closed():
        print("Ignored command error because bot session is closed.")
        return

    async def safe_send(message):
        try:
            await ctx.send(message)
        except RuntimeError as send_error:
            if "Session is closed" in str(send_error):
                print("Failed to send error response: session is closed.")
            else:
                raise
        except Exception as send_error:
            print(f"Failed to send error response: {send_error}")

    if isinstance(error, commands.BadArgument):
        await safe_send("❌ Invalid argument. Example: `ccswap 1 2`")
    elif isinstance(error, commands.MissingRequiredArgument):
        await safe_send("❌ Missing argument. Example: `ccswap <pos1> <pos2>`")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        await safe_send("❌ An unexpected error occurred while processing the command.")
        traceback.print_exception(type(error), error, error.__traceback__)

@bot.command(aliases=["ccstart"])
async def start(ctx, arg=None):
    global auction_players, auction_active, auction_countdown_active, countdown_start_time
    responded = False
    
    # Only allow permitted auction starters
    if ctx.author.id not in AUCTION_STARTER_IDS:
        if not responded:
            await ctx.send("❌ Only authorized users can start the auction.")
            responded = True
        return
    if arg == "auction":
        if auction_active or auction_countdown_active:
            if not responded:
                await ctx.send("❌ An auction is already in progress or countdown is active.")
                responded = True
            return

        # Clear previous auction participants and start countdown
        auction_players.clear()
        auction_countdown_active = True
        countdown_start_time = datetime.now()
        
        channel = bot.get_channel(AUCTION_CHANNEL_ID)
        if channel:
            await channel.send("<@&1490681648155594883>")
            embed = discord.Embed(
                title="🏏 AUCTION COUNTDOWN STARTED! ⏱️",
                description=(
                    "⏳ **5 minutes to join**\n"
                    "Use `ccjoin auction` to participate now!\n\n"
                    "📊 Requirements:\n"
                    "Minimum players: 3\n"
                    "Maximum players: 15\n\n"
                    "After 5 minutes, if 3+ players joined, auction will start automatically!"
                ),
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)
        
        # Start the scheduler if it's not running
        if not auction_scheduler.is_running():
            auction_scheduler.start()
    else:
        if not responded:
            await ctx.send("Usage: ccstart auction")
            responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccgift(ctx, amount: int = None, member: discord.Member = None):
    # Only allow admin user @uueeaa (replace with actual user ID for security)
    responded = False
    
    admin_ids = [1393453463173730394, 1322917808438509664, 1294966910986883093, 907880181811773440]  # Replace with @uueeaa's actual Discord user ID
    if ctx.author.id not in admin_ids:
        if not responded:
            await ctx.send("❌ Only the admin can gift CC.")
            responded = True
        return
    
    if amount is None or member is None:
        if not responded:
            await ctx.send("Usage: ccgift <amount> @user")
            responded = True
        return
    
    if member.id == ctx.author.id:
        if not responded:
            await ctx.send("❌ You cannot use ccgift on yourself.")
            responded = True
        return
    
    if amount <= 0:
        if not responded:
            await ctx.send("❌ Amount must be positive.")
            responded = True
        return
    
    # Check if recipient exists in database
    cursor.execute("SELECT balance FROM users WHERE id=?", (member.id,))
    user = cursor.fetchone()
    if not user:
        if not responded:
            await ctx.send(f"❌ {member.mention} is not registered. They need to use ccdeb first.")
            responded = True
        return
    
    try:
        current_balance = user[0] if user[0] is not None else 0
        new_balance = current_balance + amount
        
        # Update balance with explicit value instead of arithmetic
        cursor.execute(
            "UPDATE users SET balance = ? WHERE id=?",
            (new_balance, member.id)
        )
        
        # Check if update was successful
        if cursor.rowcount == 0:
            raise Exception("User not found in database")
        
        db.commit()
        
        if not responded:
            await ctx.send(f"✅ Successfully gifted **{amount:,} CC** to {member.mention}!")
            responded = True
        
    except Exception as e:
        db.rollback()
        if not responded:
            await ctx.send(f"❌ Error gifting CC: {str(e)}")
            responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccadd(ctx, member: discord.Member = None, *, player_name: str = None):
    """Admin command to add a player to a user's squad. Usage: ccadd @user <player name>"""
    responded = False
    
    # Only allow admin
    admin_ids = [1393453463173730394, 907880181811773440, 1322917808438509664, 1294966910986883093]
    if ctx.author.id not in admin_ids:
        if not responded:
            await ctx.send("❌ Only the admin can use this command.")
            responded = True
        return
    
    if member is None or player_name is None:
        if not responded:
            await ctx.send("Usage: ccadd @user <player name>")
            responded = True
        return
    
    if member.id == ctx.author.id:
        if not responded:
            await ctx.send("❌ You cannot add a player to your own account.")
            responded = True
        return
    
    # Check if recipient is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (member.id,))
    user = cursor.fetchone()
    if not user:
        if not responded:
            await ctx.send(f"❌ {member.mention} is not registered. They need to use ccdeb first.")
            responded = True
        return
    
    try:
        raw_name = player_name.strip()
        parts = raw_name.split()
        category_hint = None

        # Check if user manually typed N or S at the end
        if len(parts) > 1:
            suffix = parts[-1].upper().strip('.,!?')
            if suffix in {"S", "N"}:
                category_hint = suffix
                normalized_name = " ".join(parts[:-1]).strip()
            else:
                normalized_name = raw_name
        else:
            normalized_name = raw_name

        # This will now pick N by default when no category suffix is provided.
        player_key, selected_player = find_player_key_and_variant(normalized_name, category_hint)
        
        if not player_key:
            if not responded:
                await ctx.send(f"❌ Player '{normalized_name}' not found.")
                responded = True
            return

        # Use the specific OVR and Category from the selected variant
        player_display_name = selected_player.get("name", normalized_name)
        player_ovr = int(selected_player.get("ovr", 75))
        player_category = selected_player.get("category")

        # Prevent duplicates of the same variant/category
        current_cat = (selected_player.get("category") or "").upper()
        if current_cat in {"S", "N"}:
            if user_owns_player_category(member.id, player_key, current_cat):
                if not responded:
                    await ctx.send(f"❌ {member.mention} already has {player_display_name} ({current_cat}) in their squad.")
                    responded = True
                return
        else:
            cursor.execute(
                "SELECT 1 FROM squad WHERE userid=? AND player_key=?",
                (member.id, player_key)
            )
            if cursor.fetchone():
                if not responded:
                    await ctx.send(f"❌ {member.mention} already has {player_display_name} in their squad.")
                    responded = True
                return

        # Add player to squad
        player_category = selected_player.get("category") if selected_player else None
        cursor.execute(
            "INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
            (member.id, player_key, player_ovr, player_category)
        )
        db.commit()

        if not responded:
            await ctx.send(f"✅ Added **{player_display_name}** ({player_ovr} OVR) to {member.mention}'s squad!")
            responded = True

    except Exception as e:
        db.rollback()
        if not responded:
            await ctx.send(f"❌ Error adding player: {str(e)}")


@bot.command(aliases=[])
@prevent_double_response
async def ccaddp(ctx, member: discord.Member = None, amount: int = None):
    """Admin command to add leaderboard points to a user. Usage: ccaddp @user <points>"""
    responded = False

    admin_ids = [1393453463173730394, 1322917808438509664, 1294966910986883093, 907880181811773440]
    if ctx.author.id not in admin_ids:
        if not responded:
            await ctx.send("❌ Only the admin can use this command.")
            responded = True
        return

    if member is None or amount is None:
        if not responded:
            await ctx.send("Usage: ccaddp @user <points>")
            responded = True
        return

    if amount <= 0:
        if not responded:
            await ctx.send("❌ Points must be a positive integer.")
            responded = True
        return

    cursor.execute("SELECT id FROM users WHERE id=?", (member.id,))
    if not cursor.fetchone():
        if not responded:
            await ctx.send(f"❌ {member.mention} is not registered. They need to use ccdeb first.")
            responded = True
        return

    try:
        add_user_points(member.id, amount)
        if not responded:
            await ctx.send(f"✅ Added **{amount}** points to {member.mention}. Their leaderboard points have been updated.")
            responded = True
    except Exception as e:
        if not responded:
            await ctx.send(f"❌ Error adding points: {str(e)}")
            responded = True
            responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccremove(ctx, member: discord.Member = None, *, player_name: str = None):
    """Admin command to remove a player from a user's squad. Use S or N when category is required."""
    responded = False

    admin_ids = [1393453463173730394, 907880181811773440, 1322917808438509664, 1294966910986883093]
    if ctx.author.id not in admin_ids:
        if not responded:
            await ctx.send("❌ Only the admin can use this command.")
            responded = True
        return

    if member is None or player_name is None:
        if not responded:
            await ctx.send("Usage: ccremove @user <player name> [S|N]")
            responded = True
        return

    # Check if recipient is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (member.id,))
    user = cursor.fetchone()
    if not user:
        if not responded:
            await ctx.send(f"❌ {member.mention} is not registered. They need to use ccdeb first.")
            responded = True
        return

    raw_name = player_name.strip()
    parts = raw_name.split()
    category_hint = None
    if len(parts) > 1 and parts[-1].upper() in {"S", "N"}:
        category_hint = parts[-1].upper()
        normalized_name = " ".join(parts[:-1]).strip()
    else:
        normalized_name = raw_name

    variant_entries = [
        (key, entry)
        for key, entry in all_player_entries
        if entry.get("name", "").strip().lower() == normalized_name
    ]

    if not variant_entries:
        candidate_key = get_player_key_from_name(normalized_name)
        if candidate_key:
            candidate_name = players.get(candidate_key, {}).get("name", "").strip().lower()
            variant_entries = [
                (key, entry)
                for key, entry in all_player_entries
                if entry.get("name", "").strip().lower() == candidate_name
            ]
            if not variant_entries:
                variant_entries = [
                    (key, entry)
                    for key, entry in all_player_entries
                    if key == candidate_key
                ]

    if category_hint:
        variant_entries = [
            (key, entry)
            for key, entry in variant_entries
            if entry.get("category", "").upper() == category_hint
        ]

    if not variant_entries:
        if not responded:
            await ctx.send(f"❌ Player '{player_name}' not found in database.")
            responded = True
        return

    variant_keys = [key for key, _ in variant_entries]
    placeholders = ",".join("?" for _ in variant_keys)
    cursor.execute(
        f"SELECT rowid, player_key, ovr FROM squad WHERE userid=? AND player_key IN ({placeholders})",
        (member.id, *variant_keys)
    )
    rows = cursor.fetchall()
    if not rows:
        if not responded:
            if category_hint:
                await ctx.send(f"❌ {member.mention} does not have category {category_hint} of {normalized_name} in their squad.")
            else:
                await ctx.send(f"❌ {member.mention} does not have {normalized_name} in their squad.")
            responded = True
        return

    if len(rows) > 1 and category_hint is None:
        if not responded:
            await ctx.send(
                f"❌ This player has multiple categories. Use `ccremove @user {normalized_name} S` or `ccremove @user {normalized_name} N`."
            )
            responded = True
        return

    target_row = rows[0]

    if target_row is None:
        if not responded:
            await ctx.send(f"❌ {member.mention} does not have the requested player variant in their squad.")
            responded = True
        return

    try:
        cursor.execute("DELETE FROM squad WHERE rowid=?", (target_row[0],))
        db.commit()
        if not responded:
            await ctx.send(f"✅ Removed **{normalized_name}** from {member.mention}'s squad.")
            responded = True
    except Exception as e:
        db.rollback()
        if not responded:
            await ctx.send(f"❌ Error removing player: {str(e)}")
            responded = True

@bot.command(aliases=["ccbal"])
@prevent_double_response
async def ccinfo(ctx, member: discord.Member = None):
    user_id = member.id if member else ctx.author.id
    print(f"ccinfo called by {ctx.author} for user {user_id}")  # Debug print
    responded = False
    cursor.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    if not user:
        if member:
            embed = discord.Embed(description="That user is not registered.", color=discord.Color.red())
        else:
            embed = discord.Embed(description="Use ccdeb first to register your team.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    teamname = user[1]
    balance = user[2]
    embed = discord.Embed(title=teamname, description=f"Balance: {balance:,} CC")
    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=["ccdail"])
@prevent_double_response
async def ccdaily(ctx):
    """Claim daily 5000 CC reward. 7-day streak gives a random player card (78-83 OVR)."""
    now = int(time.time())
    responded = False
    
    # Check if user is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    if not cursor.fetchone():
        embed = discord.Embed(description="❌ Use ccdeb first to register your team.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    # Check daily rewards table
    cursor.execute("SELECT last_claim, streak FROM daily_rewards WHERE userid=?", (ctx.author.id,))
    row = cursor.fetchone()
    
    if row:
        last_claim, streak = row
        time_since_claim = now - last_claim
        
        # Check if 24 hours (86400 seconds) have passed
        if time_since_claim < 86400:
            remaining = 86400 - time_since_claim
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            
            embed = discord.Embed(
                title="⏳ Daily Reward Cooldown",
                description=f"You already claimed today!\n\nNext claim in **{hours}h {minutes}m**",
                color=discord.Color.orange()
            )
            embed.add_field(name="📊 Current Streak", value=f"🔥 **{streak} day(s)**", inline=False)
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return
        
        # More than 24 hours have passed - check if consecutive
        if time_since_claim >= 172800:  # More than 48 hours
            # Streak broken, reset to 1
            new_streak = 1
        else:
            # Consecutive day, increment streak
            new_streak = streak + 1
    else:
        # First time claiming
        new_streak = 1
        cursor.execute("INSERT INTO daily_rewards(userid, last_claim, streak) VALUES(?,?,?)", 
                      (ctx.author.id, now, new_streak))
    
    # Update or insert daily reward
    cursor.execute("INSERT OR REPLACE INTO daily_rewards(userid, last_claim, streak) VALUES(?,?,?)",
                  (ctx.author.id, now, new_streak))
    
    # Add 5000 CC
    cursor.execute("UPDATE users SET balance = balance + 5000 WHERE id=?", (ctx.author.id,))
    db.commit()
    add_user_points(ctx.author.id, 2)
    
    # Check if 7-day streak achieved
    streak_reward = None
    if new_streak == 7:
        # Give random player 78-83 OVR
        # 80% chance for 78-81, 20% chance for 82-83
        if random.random() < 0.8:
            ovr_range = "78-81"
            low, high = 78, 81
        else:
            ovr_range = "82-83"
            low, high = 82, 83
        
        # Find eligible players
        eligible = [
            (idx, p) for idx, p in enumerate(all_players)
            if low <= int(p.get("ovr", 0)) <= high
            and not user_owns_player_variant(ctx.author.id, all_player_keys[idx], p.get("category"))
        ]
        if eligible:
            idx, player = random.choice(eligible)
            player_ovr = int(player.get("ovr", 75))
            player_key = all_player_keys[idx]
            player_category = player.get("category")
            cursor.execute("INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
                          (ctx.author.id, player_key, player_ovr, player_category))
            db.commit()
            streak_reward = player
            # Reset streak after reward
            cursor.execute("UPDATE daily_rewards SET streak = 0 WHERE userid=?", (ctx.author.id,))
            db.commit()
    
    # Build response embed
    embed = discord.Embed(
        title="🎉 Daily Reward Claimed!",
        description="You received your daily bonus!",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="💰 CC Reward",
        value="**+ 5,000 CC**",
        inline=False
    )
    
    embed.add_field(
        name="🔥 Streak Count",
        value=f"**{new_streak} / 7 days**",
        inline=False
    )
    
    if streak_reward:
        player_name = streak_reward["name"].replace("_", " ").title()
        player_ovr = int(streak_reward.get("ovr", 75))
        embed.add_field(
            name="🏆 7-Day Streak Bonus!",
            value=f"**{player_name}** ({player_ovr} OVR)\n✨ Added to your squad!",
            inline=False
        )
        embed.color = discord.Color.gold()
    
    embed.set_footer(text="🏏 Come back tomorrow for more rewards!")
    
    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def cclb(ctx):
    responded = False
    cursor.execute("SELECT points FROM users WHERE id=?", (ctx.author.id,))
    row = cursor.fetchone()
    if not row:
        embed = discord.Embed(description="❌ You are not registered. Use ccdeb first.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    user_points = row[0] or 0
    cursor.execute(
        "SELECT id, teamname, points FROM users ORDER BY points DESC, balance DESC LIMIT 10"
    )
    top_users = cursor.fetchall()

    leaderboard_lines = []
    for index, (user_id, teamname, points) in enumerate(top_users, start=1):
        display_name = teamname or f"<@{user_id}>"
        if len(display_name) > 20:
            display_name = display_name[:17] + "..."
        leaderboard_lines.append(f"{index:>2}. {display_name:<20} {points or 0:>5}")

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE points > ?",
        (user_points,)
    )
    rank = cursor.fetchone()[0] + 1

    cursor.execute("SELECT teamname FROM users WHERE id=?", (ctx.author.id,))
    teamname = cursor.fetchone()[0] or ctx.author.name

    user_line = f"**{teamname}** — **{user_points}** pts — Rank **#{rank}**"

    header = "RANK USERNAME              POINTS"
    separator = "---- -------------------- ------"
    leaderboard_text = "\n".join(leaderboard_lines) or "No users yet."

    embed = discord.Embed(
        title="🏆 CC Leaderboard",
        description="Top 10 users by points",
        color=discord.Color.gold()
    )
    embed.add_field(name="Top 10", value=f"```\n{header}\n{separator}\n{leaderboard_text}\n```", inline=False)
    embed.add_field(name="Your Rank", value=user_line, inline=False)

    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccpoints(ctx):
    responded = False
    cursor.execute("SELECT points FROM users WHERE id=?", (ctx.author.id,))
    row = cursor.fetchone()
    if not row:
        embed = discord.Embed(description="❌ You are not registered. Use ccdeb first.", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    user_points = row[0] or 0
    cursor.execute("SELECT COUNT(*) FROM users WHERE points > ?", (user_points,))
    rank = cursor.fetchone()[0] + 1

    embed = discord.Embed(
        title="🏅 CC Points",
        description="Your current points and leaderboard rank.",
        color=discord.Color.gold()
    )
    embed.add_field(name="Your Points", value=f"**{user_points}**", inline=False)
    embed.add_field(name="Your Rank", value=f"**#{rank}**", inline=False)
    embed.add_field(
        name="How to earn points",
        value="• Play matches\n• Claim daily rewards\n• Buy players \n• Win auctions",
        inline=False
    )
    embed.set_footer(text="Use cclb to view the full top 10 leaderboard.")

    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccdrop(ctx):
    # Drop logic (separate command)
    now = int(time.time())
    
    # Flag to prevent double responses
    responded = False

    # Check cooldown
    cursor.execute("SELECT last_drop FROM drops WHERE userid=?", (ctx.author.id,))
    row = cursor.fetchone()

    if row:
        last = row[0]
        remaining = 3600 - (now - last)

        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            if not responded:
                await ctx.send(f"⏳ Next drop in **{minutes}m {seconds}s**")
                responded = True
            return

    # update cooldown
    cursor.execute(
        "INSERT OR REPLACE INTO drops(userid,last_drop) VALUES(?,?)",
        (ctx.author.id, now)
    )
    db.commit()

    # 50/50 chance
    drop_type = random.choice(["money", "player"])

    # ---------------- MONEY DROP ----------------
    if drop_type == "money":

        money_values = [1000,1500,2000,3000,60000]
        weights = [35,10,4,0.7,0.3]

        amount = random.choices(money_values, weights=weights)[0]

        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE id=?",
            (amount, ctx.author.id)
        )
        db.commit()

        if not responded:
            await ctx.send(
                f"💰 **DROP REWARD**\nYou received **{amount} CC**!"
            )
            responded = True

        return

    # ---------------- PLAYER DROP ----------------

    # rarity roll
    rarity = random.choices(
        ["75-82","83-85","86-87","88-90","91-93","94-95"],
        weights=[45,3,1,0.75,0.20,0.05]
    )[0]

    low, high = map(int, rarity.split("-"))

    # find players in that range
    pool = []

    for p in all_players:
        # Standardize OVR access
        ovr = p.get("ovr") or p.get("bat_ovr") or p.get("batovr") or p.get("bowl_ovr") or p.get("bowlovr") or max(p.get("batovr",0), p.get("bowlovr",0))
        if low <= ovr <= high:
            pool.append(p)

    if not pool:
        await ctx.send("No players available in that range.")
        return

    player = random.choice(pool)

    ovr = player.get("ovr") or player.get("bat_ovr") or player.get("batovr") or player.get("bowl_ovr") or player.get("bowlovr") or max(player.get("batovr",0), player.get("bowlovr",0))

    # Find player key
    try:
        idx = all_players.index(player)
        player_key = all_player_keys[idx]
    except ValueError:
        player_key = player.get("name", "Unknown").replace(" ", "_").lower()

    drop_embed = discord.Embed(
        title="🃏 DROP CARD",
        description=f"You pulled **{player['name']} ({ovr} OVR)**!",
        color=discord.Color.blue()
    )

    player_key = None
    for k, v in players.items():
        if v is player:
            player_key = k
            break
    if not player_key:
        player_key = get_player_key_from_name(player.get("name", "")) or player_key

    card_paths = get_player_card_paths(player_key or "", player)
    card_path = card_paths[0] if card_paths else None
    if card_paths:
        first_path = card_paths[0]
        files = build_card_files(card_paths)
        if isinstance(first_path, str) and (first_path.startswith('http://') or first_path.startswith('https://')):
            drop_embed.set_image(url=first_path)
        else:
            try:
                drop_embed.set_image(url='attachment://card_0.png')
            except Exception:
                pass
    else:
        files = []

    # If player already exists in squad, only auto-release exact same category duplicates
    duplicate = None
    if player_key:
        cursor.execute("SELECT rowid, ovr FROM squad WHERE userid=? AND LOWER(player_key)=?", (ctx.author.id, player_key.lower()))
        for rowid, existing_ovr in cursor.fetchall():
            existing_cat = get_player_category_by_ovr(player_key, existing_ovr)
            new_cat = player.get("category")
            if existing_cat and new_cat and existing_cat == new_cat:
                duplicate = rowid
                break

    if duplicate:
        from players import price_by_ovr, get_price_by_ovr
        buy_price = player.get("price") or get_price_by_ovr(ovr, player.get("category"))
        sell_value = buy_price // 2
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (sell_value, ctx.author.id))
        db.commit()

        content = f"⚠️ {ctx.author.mention} {player['name']} is already in your squad. The duplicate drop was released for {sell_value} CC."
        if files:
            await ctx.send(content=content, embed=drop_embed, files=files)
        else:
            await ctx.send(content=content, embed=drop_embed)
        return

    # Check squad size
    cursor.execute("SELECT COUNT(*) FROM squad WHERE userid=?", (ctx.author.id,))
    squad_count = cursor.fetchone()[0]

    if squad_count >= 22:
        # Get first 22 squad players
        cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 22", (ctx.author.id,))
        squad_players = [row[0] for row in cursor.fetchall()]
        
        from views import DropFullView
        view = DropFullView(ctx.author.id, player, ovr, player_key, card_path, drop_embed, squad_players)
    else:
        from views import DropView
        view = DropView(ctx.author.id, player, ovr, player_key, card_path, drop_embed)

    # Send the message with view
    if files:
        message = await ctx.send(embed=drop_embed, files=files, view=view)
    else:
        message = await ctx.send(embed=drop_embed, view=view)

    # Store message reference for timeout handling
    try:
        view.message = message
    except Exception:
        pass

@bot.command(aliases=[])
@prevent_double_response
async def ccreward(ctx):
    """Claim a random XI (5 batters, 5 bowlers, 1 allrounder, once only). 10% chance for each player to be 86+ ovr."""
    
    # Flag to prevent double responses
    responded = False
    
    # Check if user is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()
    if not user:
        embed = discord.Embed(description="Use ccdeb first to register your team.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Check if already claimed or disabled
    cursor.execute("SELECT * FROM ccreward_claimed WHERE userid=?", (ctx.author.id,))
    if cursor.fetchone():
        embed = discord.Embed(description="You already claimed your ccreward!", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    cursor.execute("SELECT * FROM ccreward_disabled WHERE userid=?", (ctx.author.id,))
    if cursor.fetchone():
        embed = discord.Embed(description="❌ You cannot claim ccreward because your team has crossed 82 OVR. This command is permanently disabled for you.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Get all players user owns
    cursor.execute("SELECT player_key FROM squad WHERE userid=?", (ctx.author.id,))
    owned = cursor.fetchall()
    owned_names = set(players.get(p[0], {}).get("name", p[0].replace('_', ' ').title()) for p in owned)

    # 1. Block if user has more than 10 players
    if len(owned) > 10:
        embed = discord.Embed(description="❌ You cannot claim ccreward if you have more than 10 players in your squad. (Empty squad required)", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # 2. Block and permanently disable if team OVR > 82
    if owned:
        cursor.execute("SELECT ovr FROM squad WHERE userid=?", (ctx.author.id,))
        owned_ovrs = [int(row[0]) for row in cursor.fetchall()]
        team_ovr = sum(owned_ovrs) / len(owned_ovrs)
        if team_ovr > 82:
            # Mark as disabled forever
            cursor.execute("INSERT OR IGNORE INTO ccreward_disabled(userid) VALUES(?)", (ctx.author.id,))
            db.commit()
            embed = discord.Embed(description="❌ You cannot claim ccreward because your team OVR has crossed 82. This command is now permanently disabled for you.", color=discord.Color.red())
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return

    # Convert all player entries to a list for filtering, preserving S/N variants
    all_player_entries_list = all_player_entries

    # 1. Four batters 75-80 OVR
    eligible_batters = [
        entry for key, entry in all_player_entries_list
        if entry.get("role") == "Batter"
        and 75 <= int(entry.get("ovr", 0)) <= 80
        and not user_owns_player_variant(ctx.author.id, key, entry.get("category"))
    ]
    if len(eligible_batters) < 4:
        embed = discord.Embed(description="❌ Not enough eligible batters to generate reward XI.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    batters = random.sample(eligible_batters, 4)

    # 2. Four bowlers 75-80 OVR
    eligible_bowlers = [
        entry for key, entry in all_player_entries_list
        if entry.get("role") == "Bowler"
        and 75 <= int(entry.get("ovr", 0)) <= 80
        and not user_owns_player_variant(ctx.author.id, key, entry.get("category"))
    ]
    if len(eligible_bowlers) < 4:
        embed = discord.Embed(description="❌ Not enough eligible bowlers to generate reward XI.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    bowlers = random.sample(eligible_bowlers, 4)

    # 3. One allrounder 75-80 OVR
    eligible_ars = [
        entry for key, entry in all_player_entries_list
        if entry.get("role") == "Allrounder"
        and 75 <= int(entry.get("ovr", 0)) <= 80
        and not user_owns_player_variant(ctx.author.id, key, entry.get("category"))
    ]
    if len(eligible_ars) < 1:
        embed = discord.Embed(description="❌ Not enough eligible allrounders to generate reward XI.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    allrounder = random.sample(eligible_ars, 1)

    # 4. One wicketkeeper 80-85 OVR
    eligible_wks = [
        entry for key, entry in all_player_entries_list
        if entry.get("role") == "Wicketkeeper"
        and 80 <= int(entry.get("ovr", 0)) <= 85
        and not user_owns_player_variant(ctx.author.id, key, entry.get("category"))
    ]
    if len(eligible_wks) < 1:
        embed = discord.Embed(description="❌ Not enough eligible wicketkeepers to generate reward XI.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    wk = random.sample(eligible_wks, 1)

    # 5. One any player 85-90 OVR
    eligible_any = [
        entry for key, entry in all_player_entries_list
        if 85 <= int(entry.get("ovr", 0)) <= 90
        and not user_owns_player_variant(ctx.author.id, key, entry.get("category"))
    ]
    if len(eligible_any) < 1:
        embed = discord.Embed(description="❌ Not enough eligible high OVR players to generate reward XI.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    anyplayer = random.sample(eligible_any, 1)

    xi = batters + bowlers + allrounder + wk + anyplayer
    random.shuffle(xi)

    # Add XI to squad
    for p in xi:
        player_name = p.get("name", "Unknown")
        player_ovr = int(p.get("ovr", 75))
        try:
            idx = all_players.index(p)
            player_key = all_player_keys[idx]
        except ValueError:
            player_key = player_name.replace(" ", "_").lower()
        category = p.get("category")
        cursor.execute(
            "INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
            (ctx.author.id, player_key, player_ovr, category)
        )
    db.commit()

    # Mark as claimed
    cursor.execute("INSERT INTO ccreward_claimed(userid) VALUES(?)", (ctx.author.id,))
    db.commit()

    # Format output with display names from live database
    text = "\n".join(f"{i+1}. {p.get('name', 'Unknown')} ({int(p.get('ovr', 0))}, {p.get('role', 'Unknown')})" for i, p in enumerate(xi))
    embed = discord.Embed(title="🎁 You received a random XI!", description=text, color=discord.Color.green())
    if not responded:
        await ctx.send(embed=embed)
        responded = True


@bot.command(aliases=[])
@prevent_double_response
async def ccmonthly(ctx):
    cursor.execute("SELECT balance, points FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()
    if not user:
        await ctx.send(embed=discord.Embed(description="Use ccdeb first to register your team.", color=discord.Color.red()))
        return

    balance, points = user
    points = points or 0
    if points < 800:
        remaining = 800 - points
        embed = discord.Embed(
            description=f"❌ Required criteria not met. You need {remaining} more points to claim monthly rewards. Claim after criteria is fulfilled.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    now = int(time.time())
    cursor.execute("SELECT last_claim FROM ccmonthly_claims WHERE userid=?", (ctx.author.id,))
    row = cursor.fetchone()
    if row and now - row[0] < 2592000:
        remaining = 2592000 - (now - row[0])
        wait_text = format_seconds(remaining)
        embed = discord.Embed(
            description=f"❌ You have already claimed your monthly reward. You can claim again in {wait_text}.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    rank = get_rank_position(ctx.author.id)
    pack_info = get_monthly_pack_info(rank)
    coins = pack_info["coins"]
    tier_name = pack_info["tier"]
    pack_type = pack_info["pack_type"]

    if coins > 0:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?", (coins, ctx.author.id))

    cursor.execute(
        "INSERT OR REPLACE INTO ccmonthly_claims(userid, last_claim) VALUES(?,?)",
        (ctx.author.id, now)
    )
    cursor.execute(
        "INSERT INTO monthly_packs(userid, name, tier, status, created_at) VALUES(?,?,?,?,?)",
        (ctx.author.id, "Monthly Claim", tier_name, "unopened", now)
    )
    db.commit()

    awarded = f"\nYou have been awarded **{coins} CC** and a **Monthly Claim** pack." if coins else "\nYou have been awarded a **Monthly Claim** pack."
    embed = discord.Embed(
        title="🎉 Monthly Claim Successful!",
        description=(
            f"You qualified for monthly rewards with **{points} points** and rank **{rank}**.\n"
            f"Tier: **{tier_name}**\n"
            f"Pack contents: {pack_info['description']}.{awarded}\n"
            "Use **ccpacks** to open your Monthly Claim pack."
        ),
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(aliases=[])
@prevent_double_response
async def ccpacks(ctx):
    cursor.execute(
        "SELECT pack_id, name, tier FROM monthly_packs WHERE userid=? AND status='unopened' ORDER BY created_at ASC",
        (ctx.author.id,)
    )
    monthly_rows = cursor.fetchall()

    cursor.execute(
        "SELECT inv_id, pack_type, pack_name FROM user_inventory WHERE userid=? ORDER BY inv_id ASC",
        (ctx.author.id,)
    )
    inventory_rows = cursor.fetchall()

    if not monthly_rows and not inventory_rows:
        embed = discord.Embed(
            title="📦 My Packs",
            description="You have no unopened packs.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return

    description = "Select a pack from the dropdown to open it."
    if monthly_rows:
        description += "\n\n**Monthly Claim Packs:**"
        for pack_id, name, tier in monthly_rows:
            description += f"\n• **{name}** — {tier} (ID: {pack_id})"

    if inventory_rows:
        description += "\n\n**Shop Packs:**"
        for inv_id, pack_type, pack_name in inventory_rows:
            description += f"\n• **{pack_name}** — {pack_type.replace('_', ' ').title()} (Shop ID: {inv_id})"

    embed = discord.Embed(
        title="📦 My Packs",
        description=description,
        color=discord.Color.blue()
    )
    view = PackSelectView(ctx.author.id, monthly_rows, inventory_rows)
    await ctx.send(embed=embed, view=view)


@bot.command(name="ccpack", aliases=["ccshop"])
@prevent_double_response
async def ccpack(ctx):
    cursor.execute("SELECT balance FROM users WHERE id=?", (ctx.author.id,))
    balance_row = cursor.fetchone()
    balance = balance_row[0] if balance_row else 0

    embed = discord.Embed(
        title="🏪 Cric Core Pack Shop",
        description=(
            "Buy packs with your CC using `ccpack` (alias: `ccshop`), then open them later from `ccpacks`.\n\n"
            f"Your balance: **{balance:,} CC**\n\n"
            "**Available Packs:**"
        ),
        color=discord.Color.gold()
    )
    embed.add_field(name="IPL Legends Pack", value="2,500,000 CC", inline=False)
    embed.add_field(name="WPL 2026 Pack", value="1,200,000 CC", inline=False)
    embed.add_field(name="T20 World Cup Pack", value="1,800,000 CC", inline=False)
    embed.add_field(name="SA20 Pack", value="1,300,000 CC", inline=False)
    embed.set_footer(text="Select a pack from the dropdown to purchase it.")

    view = PackShopView(ctx.author.id)
    await ctx.send(embed=embed, view=view)


class SquadView(discord.ui.View):
    def __init__(self, squad, team_name):
        super().__init__(timeout=30)
        self.squad = squad
        self.team_name = team_name
        self.page = 0
        self.max_page = 1 if len(squad) > 11 else 0
        self.total_ovr = sum(int(ovr) for _, _, ovr in squad) if squad else 0
        self.avg_ovr = self.calculate_avg_ovr()
        self.update_embed()

    def calculate_avg_ovr(self):
        # Simplified, assuming first 11 for avg
        if self.squad:
            xi_ovr = sum(int(ovr) for _, _, ovr in self.squad[:11])
            return xi_ovr // 11
        return 0

    def update_embed(self):
        start = self.page * 11
        end = start + 11
        page_squad = self.squad[start:end]
        
        player_list = []
        for pos, (_rowid, player_name, ovr) in enumerate(page_squad, start=start+1):
            display_name = player_name.replace('_', ' ').title()
            role = get_player_role(player_name)
            entry = f"{pos:>2}. {display_name:<24} {ovr:>3}   {role}"
            player_list.append(entry)
        
        embed = discord.Embed(
            title=f"🏏 {self.team_name.upper()} SQUAD 🏏 (Page {self.page+1})",
            color=discord.Color.blue()
        )
        
        if player_list:
            header = f"{'No.':<4} {'Player':<24} {'OVR':<4} Role"
            separator = f"{'---':<4} {'-'*24} {'---':<4} {'-'*13}"
            players_text = "```\n" + "\n".join([header, separator] + player_list) + "\n```"
            embed.add_field(
                name="📋 PLAYERS",
                value=players_text,
                inline=False
            )
        
        stats = f"**Total:** `{len(self.squad)}/22`  **Avg OVR:** `{self.avg_ovr}`  **Squad OVR:** `{self.total_ovr}`"
        embed.add_field(
            name="📊 STATS",
            value=stats,
            inline=False
        )
        
        embed.set_footer(text="🏏 Cric Core 🏏")
        
        self.embed = embed

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_embed()
            await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            self.update_embed()
            await interaction.response.edit_message(embed=self.embed, view=self)

    async def on_timeout(self):
        try:
            await self.message.edit(view=None)
        except:
            pass


## Removed duplicate DB setup

class BuyView(CardNavigationView):
    def __init__(self, ctx, variants, card_paths=None, embed=None):
        self.ctx = ctx
        self.variants = variants
        self.card_index = 0
        self.variant_id, self.player_key, self.player, self.card_path = self.variants[0]
        self.player_id = self.variant_id if self.variant_id is not None else (all_player_keys.index(self.player_key) if self.player_key in all_player_keys else 0)
        self.embed_file = None

        super().__init__(card_paths=card_paths, embed=embed, timeout=120)
        self.update_variant_state()
        self.update_card_image()

    def get_current_attachment(self):
        if self.card_path and isinstance(self.card_path, str) and not (self.card_path.startswith('http://') or self.card_path.startswith('https://')):
            return discord.File(self.card_path, filename=f'card_{self.card_index}.png')
        if self.embed_file:
            return self.embed_file
        return None

    def update_variant_state(self):
        if self.player.get("category") == "S":
            self.buy.disabled = True
            self.buy.style = discord.ButtonStyle.gray
        else:
            self.buy.disabled = False
            self.buy.style = discord.ButtonStyle.green

    def update_card_image(self):
        if not self.variants:
            return

        self.variant_id, self.player_key, self.player, self.card_path = self.variants[self.card_index]
        self.player_id = self.variant_id if self.variant_id is not None else (all_player_keys.index(self.player_key) if self.player_key in all_player_keys else 0)
        self.embed, self.embed_file = create_player_embed(self.player, self.player_id, self.player_key, include_category=False)

        if self.card_path and isinstance(self.card_path, str) and self.card_path.startswith(('http://', 'https://')):
            self.embed.set_image(url=self.card_path)
        elif self.card_path:
            self.embed.set_image(url=f'attachment://card_{self.card_index}.png')
        elif self.embed_file:
            self.embed.set_image(url='attachment://card.png')

        self.embed.set_footer(text=f"Variant {self.card_index+1}/{len(self.variants)}")
        self.update_variant_state()
        self.update_navigation_buttons()

    async def _safe_edit(self, interaction: discord.Interaction, attachments=None):
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=self.embed, view=self, attachments=attachments)
        else:
            await interaction.edit_original_response(embed=self.embed, view=self, attachments=attachments)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_finished():
            await interaction.response.send_message("This card selection is no longer active.", ephemeral=True)
            return

        if not self.card_paths:
            await interaction.response.send_message("No additional card variants available.", ephemeral=True)
            return

        self.card_index = (self.card_index - 1) % len(self.card_paths)
        self.update_card_image()

        attachment = self.get_current_attachment()
        attachments = [attachment] if attachment else None
        try:
            await self._safe_edit(interaction, attachments=attachments)
        except Exception:
            if hasattr(self, 'message') and self.message:
                try:
                    await self.message.edit(embed=self.embed, view=self, attachments=attachments)
                except Exception:
                    pass

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_finished():
            await interaction.response.send_message("This card selection is no longer active.", ephemeral=True)
            return

        if not self.card_paths:
            await interaction.response.send_message("No additional card variants available.", ephemeral=True)
            return

        self.card_index = (self.card_index + 1) % len(self.card_paths)
        self.update_card_image()

        attachment = self.get_current_attachment()
        attachments = [attachment] if attachment else None
        try:
            await self._safe_edit(interaction, attachments=attachments)
        except Exception:
            if hasattr(self, 'message') and self.message:
                try:
                    await self.message.edit(embed=self.embed, view=self, attachments=attachments)
                except Exception:
                    pass

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):

        current_id, current_key, current_player, current_card_path = self.variants[self.card_index]
        cursor.execute("SELECT balance FROM users WHERE id=?", (self.ctx.author.id,))
        bal = cursor.fetchone()[0]

        price = current_player.get("price")
        if isinstance(price, str) and price.isdigit():
            price = int(price)
        elif isinstance(price, float):
            price = int(price)

        if price is None:
            price = 0

        cursor.execute("SELECT COUNT(*) FROM squad WHERE userid=?", (self.ctx.author.id,))
        squad_count = cursor.fetchone()[0]

        if squad_count >= 22:
            await interaction.response.send_message("❌ Squad full (22 players).", ephemeral=True)
            return

        if bal < price:
            await interaction.response.send_message("❌ Not enough CC.", ephemeral=True)
            return

        current_cat = (current_player.get("category") or "").upper()
        if current_cat in {"S", "N"}:
            if user_owns_player_category(self.ctx.author.id, current_key, current_cat):
                await interaction.response.send_message(
                    "❌ You already own this card category for this player.",
                    ephemeral=True
                )
                return
            if current_cat == "N" and user_owns_player_category(self.ctx.author.id, current_key, "S"):
                await interaction.response.send_message(
                    "❌ You already own the S variant of this player. You cannot buy the N card.",
                    ephemeral=True
                )
                return
        else:
            cursor.execute(
                "SELECT 1 FROM squad WHERE userid=? AND player_key=?",
                (self.ctx.author.id, current_key)
            )
            if cursor.fetchone():
                await interaction.response.send_message("❌ You already own this player.", ephemeral=True)
                return

        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE id=?",
            (price, self.ctx.author.id)
        )

        ovr = current_player.get("ovr") or max(current_player.get("batovr", 0), current_player.get("bowlovr", 0))

        cursor.execute(
            "INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
            (self.ctx.author.id, current_key, ovr, current_player.get("category"))
        )

        db.commit()

        await interaction.response.edit_message(
            content=f"✅ Bought **{current_player['name']}** for **{price:,} CC**",
            view=None
        )

    @discord.ui.button(label="❌", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Purchase cancelled.",
            view=None
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

# ====== Commands ======
@bot.command(aliases=[])
@prevent_double_response
async def ccplay(ctx, overs: int):
    """Start a match for the given overs (1-20)."""
    responded = False
    
    if overs < 1 or overs > 20:
        embed = discord.Embed(description="❌ Overs must be between 1 and 20.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    views_module = __import__('views')
    if ctx.channel.id in views_module.current_matches:
        # If match object is actually finished but not cleared for some reason, reset it and allow new match
        current_match = views_module.current_matches[ctx.channel.id]
        if hasattr(current_match, 'innings_over') and current_match.innings_over() == 'MATCH_DONE':
            del views_module.current_matches[ctx.channel.id]
        else:
            embed = discord.Embed(description="A match is already in progress in this channel.", color=discord.Color.red())
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return


    # Check if user is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()
    if not user:
        embed = discord.Embed(description="Use ccdeb first to register your team.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Check squad requirements
    from views import get_squad_counts
    roles, squad_players = get_squad_counts(ctx.author.id)
    errors = []
    if not (3 <= roles["bat"] <= 5):
        errors.append(f"You have {roles['bat']} batters. You need **3-5 batters**.")
    if not (3 <= roles["bowl"] <= 5):
        errors.append(f"You have {roles['bowl']} bowlers. You need **3-5 bowlers**.")
    if not (1 <= roles["alr"] <= 3):
        errors.append(f"You have {roles['alr']} all-rounders. You need **1-3 all-rounders**.")
    if not (1 <= roles["wk"] <= 2):
        errors.append(f"You have {roles['wk']} wicketkeepers. You need **1-2 wicketkeepers**.")
    if errors:
        embed = discord.Embed(
            title="Squad Requirements Not Met",
            description=(
                "To play a match, your squad must meet all of the following requirements:\n"
                "- 3 to 5 batters\n"
                "- 3 to 5 bowlers\n"
                "- 1 to 3 all-rounders\n"
                "- 1 to 2 wicketkeepers\n\n"
                "Issues:\n" + "\n".join(errors)
            ),
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    conflicting_keys = get_conflicting_player_keys(ctx.author.id)
    if conflicting_keys:
        conflict_names = []
        for key in conflicting_keys:
            entry = players.get(key)
            if entry:
                conflict_names.append(entry.get("name", key.replace("_", " ").title()))
            else:
                conflict_names.append(key.replace("_", " ").title())

        embed = discord.Embed(
            title="Cannot start match with both S and N variants",
            description=(
                "You currently own both S and N variants of the following player(s).\n"
                "Sell one variant before starting a match."
            ),
            color=discord.Color.red()
        )
        embed.add_field(name="Conflicting players", value="\n".join(conflict_names), inline=False)
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    embed = discord.Embed(description=f"{ctx.author.mention} has challenged everyone to a {overs}-over match!\nWho will accept?", color=discord.Color.blue())
    if not responded:
        await ctx.send(embed=embed, view=AcceptView(ctx.author, overs))
        responded = True

@bot.command(aliases=["ccgp"])
@prevent_double_response
async def ccgameplay(ctx):
    """Show the CC gameplay guide for pace, spin, and pitch strategy."""
    embed = discord.Embed(
        title="CC Gameplay Guide",
        description="Professional batting and bowling guidance for pace, spin, and pitches.",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="Pace Guide",
        value=(
            "**INSWING**\n"
            "Good Length → (Def/Drive)\n"
            "Yorker → (Def/Drive)\n"
            "Bouncer → (Def/Pull)\n"
            "Full Length → (Def/Loft)\n"
            "Back Length → (Def/Pull)\n"
            "Wide Yorker → (Def/Drive)\n\n"
            "**SLOW**\n"
            "Good Length → (Def/Cut)\n"
            "Yorker → (Def/Drive)\n"
            "Bouncer → (Def/Pull)\n"
            "Full Length → (Drive/Loft)\n"
            "Back Length → (Def/Cut)\n"
            "Wide Yorker → (Def/Cut)\n\n"
            "**FAST**\n"
            "Good Length → (Def/Drive)\n"
            "Yorker → (Def/Drive)\n"
            "Bouncer → (Def/Pull)\n"
            "Full Length → (Drive/Loft)\n"
            "Back Length → (Def/Pull)\n"
            "Wide Yorker → (Def/Cut)\n\n"
            "**OUTSWING**\n"
            "Good Length → (Def/Cut)\n"
            "Yorker → (Def/Drive)\n"
            "Bouncer → (Def/Pull)\n"
            "Full Length → (Def/Loft)\n"
            "Back Length → (Def/Cut)\n"
            "Wide Yorker → (Def/Cut)"
        ),
        inline=False
    )

    embed.add_field(
        name="Spin Guide",
        value=(
            "**OFFSPIN**\n"
            "Off Break → (Def/Pull)\n"
            "Doosra → (Cut/Def)\n"
            "Arm Ball → (Drive/Def)\n"
            "Flighted → (Loft)\n"
            "Quicker → (Pull)\n\n"
            "**LEGSPIN**\n"
            "Leg Break → (Cut/Loft)\n"
            "Top Spinner → (Loft/Drive)\n"
            "Googly → (Pull/Loft)\n"
            "Flipper → (Cut/Drive)\n"
            "Slider → (Loft/Drive)"
        ),
        inline=False
    )

    embed.add_field(
        name="Pitch Details",
        value=(
            "**Green Pitch** — Pacer paradise: more wickets, more dots, fewer 4s, spinners must work harder.\n"
            "**Dry Pitch** — Spinner paradise: spin gets extra reward and wicket chances, boundaries tighten for spin.\n"
            "**Flat Pitch** — Batter paradise: fewer wickets, more 4s/6s, and sharper scoring opportunities."
        ),
        inline=False
    )

    embed.set_footer(text="Use ccplay <overs> to launch a match with these tactics.")
    await ctx.send(embed=embed)

@bot.command(aliases=["ccdebut"])
@prevent_double_response
async def ccdeb(ctx):
    responded = False
    
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()

    if user:
        embed = discord.Embed(description="You already debuted.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Insert user
    try:
        cursor.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (ctx.author.id, ctx.author.name, 10000, 0)
        )

        # Give starter squad: 5 random players 70-80 OVR
        eligible = [p for p in all_players if 70 <= int(p.get("ovr", 0)) <= 80]
        if len(eligible) >= 5:
            starters = random.sample(eligible, 5)
            for p in starters:
                player_key = all_player_keys[all_players.index(p)]
                ovr = int(p.get("ovr", 75))
                category = p.get("category")
                cursor.execute("INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)", (ctx.author.id, player_key, ovr, category))

        db.commit()
        embed = discord.Embed(title="🏏 Welcome to CC — Cric Core", description=f"Commands:\n\nccinfo — team info\nccteam — view squad\nccxi — playing XI\nccplay <overs> — play match\nccbuy <player> — buy player\nccname <name> — rename team\n\nYou received {10000:,} CC 💰 and a starter squad of 5 players!\nAccount created.", color=discord.Color.green())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
    except Exception as e:
        db.rollback()
        embed = discord.Embed(description=f"❌ An error occurred during debut: {e}", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True

@bot.command(aliases=["ccsquad"])
@prevent_double_response
async def ccteam(ctx, member: discord.Member = None):
    responded = False
    user_id = member.id if member else ctx.author.id
    refresh_squad_ovr(user_id)
    cursor.execute("SELECT rowid, player_key, ovr FROM squad WHERE userid=? ORDER BY rowid", (user_id,))
    squad = cursor.fetchall()
    if not squad:
        embed = discord.Embed(
            title="🏏 THEIR SQUAD" if member else "🏏 YOUR SQUAD",
            description="**Squad is EMPTY**",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    # Check if user is registered
    cursor.execute("SELECT teamname FROM users WHERE id=?", (user_id,))
    user = cursor.fetchone()
    if not user:
        embed = discord.Embed(description="That user is not registered.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    team_name = user[0] if user[0] else ("Their Team" if member else "Your Team")
    
    # Create player list with rankings (1-indexed by position in squad)
    player_list = []
    for pos, (_rowid, player_name, ovr) in enumerate(squad, start=1):
        display_name = player_name.replace('_', ' ').title()
        role = get_player_role(player_name)
        entry = f"{pos:>2}. {display_name:<24} {ovr:>3}   {role}"
        player_list.append(entry)
    
    # Create main embed
    embed = discord.Embed(
        title=f"🏏 {team_name.upper()} SQUAD 🏏",
        color=discord.Color.blue()
    )
    
    # Add stats
    total_ovr = sum(int(ovr) for _, _, ovr in squad) if squad else 0
    
    # Get XI players' OVRs if XI exists
    cursor.execute("""
        SELECT s.ovr FROM xi x 
        JOIN squad s ON x.player = s.player_key AND x.userid = s.userid 
        WHERE x.userid = ? 
        ORDER BY x.rowid
    """, (user_id,))
    xi_ovrs = [int(row[0]) for row in cursor.fetchall()]
    
    if xi_ovrs:
        avg_ovr = sum(xi_ovrs) // 11
    elif len(squad) >= 11:
        xi_ovr = sum(int(ovr) for _, _, ovr in squad[:11])
        avg_ovr = xi_ovr // 11
    else:
        avg_ovr = int(total_ovr / len(squad)) if squad else 0
    
    stats = f"**Total:** `{len(squad)}/22`  **Avg OVR:** `{avg_ovr}`  **Squad OVR:** `{total_ovr}`"
    
    if len(squad) <= 11:
        # Create main embed
        embed = discord.Embed(
            title=f"🏏 {team_name.upper()} SQUAD 🏏",
            color=discord.Color.blue()
        )
        
        # Add players in one or more fields with strict alignment and Discord limits
        if player_list:
            header = f"{'No.':<4} {'Player':<24} {'OVR':<4} Role"
            separator = f"{'---':<4} {'-'*24} {'---':<4} {'-'*13}"
            def build_field(lines):
                return "```\n" + "\n".join([header, separator] + lines) + "\n```"

            field_lines = []
            current_chunk = []
            for entry in player_list:
                candidate = build_field(current_chunk + [entry])
                if len(candidate) > 1024:
                    if current_chunk:
                        field_lines.append(build_field(current_chunk))
                    current_chunk = [entry]
                else:
                    current_chunk.append(entry)

            if current_chunk:
                field_lines.append(build_field(current_chunk))

            for index, field_value in enumerate(field_lines, start=1):
                field_name = "📋 PLAYERS" if index == 1 else f"📋 PLAYERS (cont.)"
                embed.add_field(name=field_name, value=field_value, inline=False)
        
        embed.add_field(
            name="📊 STATS",
            value=stats,
            inline=False
        )
        
        embed.set_footer(text="🏏 Cric Core 🏏")
        
        await ctx.send(embed=embed)
    else:
        view = SquadView(squad, team_name)
        message = await ctx.send(embed=view.embed, view=view)
        view.message = message
        responded = True


def get_player_role(player_name):
    """
    Get player role with intelligent name matching.
    Handles:
    - Case-insensitive key matches including spaces/underscores
    - Last name matching (for abbreviations like V Chakravarthy)
    - Substring/partial matching (for common variations)
    Returns role string or "Unknown"
    """
    if not player_name:
        return "Unknown"
    
    player_name_normalized = player_name.strip().lower()
    alt_key = player_name_normalized.replace(" ", "_")
    alt_key_space = player_name_normalized.replace("_", " ")

    for key, pdata in players.items():
        if not pdata:
            continue
        key_norm = key.strip().lower()
        if key_norm == player_name_normalized or key_norm == alt_key or key_norm == alt_key_space:
            return pdata.get("role", "Unknown")

    # Strategy 1: Exact normalized match by display name
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == player_name_normalized:
            return pdata.get("role", "Unknown")
    
    # Strategy 2: Last name match (handles "Varun Chakravarthy" vs "V Chakravarthy")
    player_parts = player_name_normalized.split()
    if len(player_parts) > 1:
        last_name = player_parts[-1]
        for key, pdata in players.items():
            if not pdata:
                continue
            pdata_name = pdata.get("name", "").strip().lower()
            pdata_parts = pdata_name.split()
            if len(pdata_parts) > 1 and pdata_parts[-1] == last_name:
                # Last name matches - check if first name is a substring or abbreviation
                first_part = player_parts[0]
                pdata_first = pdata_parts[0]
                if first_part in pdata_first or pdata_first in first_part:
                    return pdata.get("role", "Unknown")
    
    # Strategy 3: Check if player name contains or is contained in a players dict entry
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        # If squad player name is part of dict entry or vice versa
        if player_name_normalized in pdata_name or pdata_name in player_name_normalized:
            return pdata.get("role", "Unknown")
    
    # Strategy 4: Fuzzy match by display name
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if difflib.SequenceMatcher(None, player_name_normalized, pdata_name).ratio() > 0.8:
            return pdata.get("role", "Unknown")
    
    return "Unknown"

# Country code to flag emoji mapping
COUNTRY_FLAGS = {
    "IND": "🇮🇳",   # India
    "ENG": "🇬🇧",   # England
    "AUS": "🇦🇺",   # Australia
    "NZ": "🇳🇿",    # New Zealand
    "SA": "🇿🇦",    # South Africa
    "PAK": "🇵🇰",   # Pakistan
    "PK": "🇵🇰",    # Pakistan (alternate)
    "WI": "🇧🇧",    # West Indies
    "SL": "🇱🇰",    # Sri Lanka
    "AFG": "🇦🇫",   # Afghanistan
    "IRE": "🇮🇪",   # Ireland
    "ZIM": "🇿🇼",   # Zimbabwe
    "BAN": "🇧🇩",   # Bangladesh
    "USA": "🇺🇸",   # USA
    "CAN": "🇨🇦",   # Canada
}

def get_player_country_code(player_name):
    """
    Get player's country code by matching against players database.
    Returns country code or default emoji if not found.
    """
    if not player_name:
        return "❓"
    
    player_name_normalized = player_name.strip().lower()
    
    # Strategy 1: Direct key match
    if player_name_normalized in players:
        return players[player_name_normalized].get("country", "❓")
    
    # Strategy 2: Underscore/space alternate key match
    alt_key = player_name_normalized.replace(" ", "_")
    if alt_key in players:
        return players[alt_key].get("country", "❓")
    
    alt_key = player_name_normalized.replace("_", " ")
    if alt_key in players:
        return players[alt_key].get("country", "❓")
    
    # Strategy 3: Match by display name
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == player_name_normalized:
            return pdata.get("country", "❓")
    
    # Strategy 4: Last name match
    player_parts = player_name_normalized.split()
    if len(player_parts) > 1:
        last_name = player_parts[-1]
        for key, pdata in players.items():
            if not pdata:
                continue
            pdata_name = pdata.get("name", "").strip().lower()
            pdata_parts = pdata_name.split()
            if len(pdata_parts) > 1 and pdata_parts[-1] == last_name:
                first_part = player_parts[0]
                pdata_first = pdata_parts[0]
                if first_part in pdata_first or pdata_first in first_part:
                    return pdata.get("country", "❓")
    
    # Strategy 5: Contains match
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if player_name_normalized in pdata_name or pdata_name in player_name_normalized:
            return pdata.get("country", "❓")
    
    return "❓"

def get_country_flag_emoji(country_code):
    """
    Convert country code to flag emoji.
    """
    if not country_code:
        return "❓"
    return COUNTRY_FLAGS.get(country_code, "❓")

import discord
from discord.ext import commands

# Assuming these are defined globally or imported elsewhere in your bot setup
# cursor = your_db_connection.cursor()
# players = { ... player data ... }
# @prevent_double_response is a custom decorator

@bot.command(aliases=['cc11'])
@prevent_double_response
async def ccxi(ctx, member: discord.Member = None):
    user_id = member.id if member else ctx.author.id
    
    # Database fetching
    cursor.execute("SELECT player_key, ovr, category FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
    xi_rows = cursor.fetchall()
    
    if not xi_rows:
        embed = discord.Embed(
            description="❌ **Your XI is currently empty.**\nUse `ccbuy` to recruit players.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return

    cursor.execute("SELECT teamname FROM users WHERE id=?", (user_id,))
    user_data = cursor.fetchone()
    team_name = (user_data[0] if user_data and user_data[0] else "UNNAMED XI").upper()

    def bold_mono(text):
        """Converts text to Unicode mathematical bold monospace."""
        bold_map = {
            **{chr(i): chr(0x1D400 + i - 65) for i in range(65, 91)},
            **{chr(i): chr(0x1D41A + i - 97) for i in range(97, 123)},
            **{str(i): chr(0x1D7CE + i) for i in range(10)}
        }
        return ''.join(bold_map.get(ch, ch) for ch in text)

    # Grid Configuration - PURE ASCII FOR PIXEL-PERFECT ALIGNMENT
    name_w = 15  
    stat_w = 2   

    # Grouping logic
    sections = {
        "BATTER": [],
        "WICKETKEEPER": [],
        "ALLROUNDER": [],
        "BOWLER": []
    }

    for player_key, ovr, category in xi_rows:
        entry = get_player_variant_entry(player_key, category=category, ovr=ovr)
        p_info = entry if entry is not None else players.get(player_key, {})
        role = get_player_role(player_key).upper()
        raw_name = p_info.get("name", player_key.split('_')[-1].replace('_', ' ').title())
        # Consistent Padding
        clean_name = raw_name[:name_w].upper().ljust(name_w)
        ovr_str = str(ovr)[:stat_w].rjust(stat_w)
        bat_str = str(p_info.get("bat_ovr", 0))[:stat_w].rjust(stat_w)
        bowl_str = str(p_info.get("bowl_ovr", 0))[:stat_w].rjust(stat_w)
        
        # Grid line
        line = f"{clean_name} | {ovr_str} | {bat_str} | {bowl_str} |"
        entry = f"` {line} `"
        
        # Categorize
        if role in sections:
            sections[role].append(entry)
        else:
            sections["BATTER"].append(entry)

    avg_ovr = sum(row[1] for row in xi_rows) // 11 if xi_rows else 0

    # Building description segments
    desc_segments = [
        f"🏆 **{bold_mono(team_name)}**",
        f"✨ **{bold_mono('OVR')}: {avg_ovr}**",
        ""
    ]

    # Category display mapping
    display_meta = [
        ("BATTER","<:cbat:1492021026174009454>", "BATTERS"),
        ("WICKETKEEPER", "🧤", "WICKET-KEEPERS"),
        ("ALLROUNDER", "🏏", "ALL-ROUNDERS"),
        ("BOWLER","<:cball:1492020800968982598>", "BOWLERS")
    ]

    for key, emoji, label in display_meta:
        if sections[key]:
            desc_segments.append(f"{emoji} **{bold_mono(label)}**")
            desc_segments.extend(sections[key])
            desc_segments.append("")

    embed = discord.Embed(
        description="\n".join(desc_segments).strip(),
        color=discord.Color.green()
    )
    
    embed.set_author(name=f"{ctx.author.display_name}'s Squad", icon_url=ctx.author.display_avatar.url)
    embed.set_footer(text="Cric Core • XI Management System")

    await ctx.send(embed=embed)

@bot.command(aliases=[])
@prevent_double_response
async def ccname(ctx, *, name):
    responded = False
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()

    if not user:
        embed = discord.Embed(description="Use ccdeb first.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    cursor.execute("UPDATE users SET teamname=? WHERE id=?", (name, ctx.author.id))
    db.commit()
    embed = discord.Embed(description=f"✅ Team renamed to {name}", color=discord.Color.green())
    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccswap(ctx, pos1: int, pos2: int):
    responded = False
    refresh_squad_ovr(ctx.author.id)
    cursor.execute("SELECT rowid, player_key, ovr FROM squad WHERE userid=? ORDER BY rowid", (ctx.author.id,))
    squad = cursor.fetchall()

    max_squad = len(squad)

    if max_squad == 0:
        embed = discord.Embed(description="You have no squad positions to swap.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    if pos1 < 1 or pos2 < 1 or pos1 > max_squad or pos2 > max_squad:
        embed = discord.Embed(description="Invalid positions.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    if pos1 == pos2:
        embed = discord.Embed(description="Please provide two different positions.", color=discord.Color.orange())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    rowid1, player_key1, ovr1 = squad[pos1-1]
    rowid2, player_key2, ovr2 = squad[pos2-1]

    cursor.execute("UPDATE squad SET player_key=?, ovr=? WHERE rowid=?", (player_key2, ovr2, rowid1))
    cursor.execute("UPDATE squad SET player_key=?, ovr=? WHERE rowid=?", (player_key1, ovr1, rowid2))

    db.commit()

    embed = discord.Embed(description=f"🔄 Swapped squad positions {pos1} and {pos2} (ccxi auto-updates from top 11 squad).", color=discord.Color.green())
    if not responded:
        await ctx.send(embed=embed)
        responded = True

from io import BytesIO

@bot.command(aliases=[])
@prevent_double_response
async def ccbuy(ctx, *, name_or_id):
    print(f"ccbuy called by {ctx.author}")  # Debug print
    responded = False

    player = None
    player_id = None
    player_key = None

    if name_or_id.isdigit():
        idx = int(name_or_id)
        if 0 <= idx < len(all_players):
            player = all_players[idx]
            player_id = idx
            player_key = all_player_keys[idx]
        else:
            embed = discord.Embed(description="❌ Invalid player ID.", color=discord.Color.red())
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return

    if player is None:
        normalized_query = name_or_id.lower().strip()
        matches = []
        for key, entry in all_player_entries:
            entry_name = entry.get("name", "").lower()
            if normalized_query == key.lower() or normalized_query == entry_name:
                matches.append((key, entry))

        if not matches:
            words = normalized_query.split()
            for key, entry in all_player_entries:
                entry_name = entry.get("name", "").lower()
                if all(word in entry_name or word in key.lower() for word in words):
                    matches.append((key, entry))

        if not matches:
            embed = discord.Embed(description="❌ Player not found.", color=discord.Color.red())
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return

        # NEW: Group variants of the same player name
        match_names = {entry.get("name", "").strip().lower() for _, entry in matches}
        
        # If the query is exactly a player's name, take ALL their variants (S and N)
        if len(match_names) == 1:
            # Sort N before S for the navigation pages
            matches.sort(key=lambda item: item[1].get("category", "N") == "S")
        else:
            # If multiple different players are found (e.g., "Sharma"), list them without keys or categories
            text = "\n".join(
                f"{entry.get('name', key.replace('_', ' ').title())}"
                for key, entry in matches[:10]
            )
            embed = discord.Embed(description=f"Multiple players found:\n{text}", color=discord.Color.orange())
            if not responded:
                await ctx.send(embed=embed)
                responded = True
            return

        player_key, player = matches[0]
        player_id = all_player_keys.index(player_key) if player_key in all_player_keys else 0

    variant_entries = get_player_variant_entries_with_id(player_key, player)
    variant_items = []
    for variant_id, variant_key, variant_player in variant_entries:
        variant_card_paths = get_player_card_paths(variant_key, variant_player, player_id=variant_id)
        card_path = variant_card_paths[0] if variant_card_paths else None
        variant_items.append((variant_id, variant_key, variant_player, card_path))

    card_paths = [item[3] for item in variant_items]
    first_variant_id, first_variant_key, first_variant_player, first_card_path = variant_items[0]
    embed, file = create_player_embed(
        first_variant_player,
        first_variant_id,
        first_variant_key,
        include_category=False
    )

    files = []
    if first_card_path:
        if first_card_path.startswith('http://') or first_card_path.startswith('https://'):
            embed.set_image(url=first_card_path)
        else:
            embed.set_image(url='attachment://card_0.png')
            files = [discord.File(first_card_path, filename='card_0.png')]
    elif file:
        files = [file]

    content = None

    view = BuyView(ctx, variant_items, card_paths=card_paths, embed=embed)

    if files:
        if not responded:
            message = await ctx.send(content=content, embed=embed, files=files, view=view)
            view.message = message
            responded = True
    else:
        if not responded:
            message = await ctx.send(content=content, embed=embed, view=view)
            view.message = message
            responded = True

@bot.command(aliases=[])
@prevent_double_response
async def ccsell(ctx, *, query: str):
    refresh_squad_ovr(ctx.author.id)
    responded = False

    # Parse query: name [amount]
    parts = query.rsplit(' ', 1)
    if len(parts) == 2 and parts[1].isdigit():
        name = parts[0]
        amount = int(parts[1])
    else:
        name = query
        amount = 1

    # Normalize query to support both key and display-name formats
    name = name.replace('_', ' ').strip().lower()
    canonical_key = get_player_key_from_name(name)

    if not canonical_key:
        embed = discord.Embed(
            description="❌ Player not found in database.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    query = "SELECT rowid, player_key, ovr, category FROM squad WHERE userid=? AND player_key = ?"
    cursor.execute(query, (ctx.author.id, canonical_key))
    rows = cursor.fetchall()

    if not rows:
        embed = discord.Embed(
            description="❌ You don't have that player in your squad.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    player_key = rows[0][1]
    ovr = rows[0][2]
    category = rows[0][3]
    total_owned = len(rows)

    player_variant = get_player_variant_entry(player_key, category=category, ovr=ovr)
    display_name = (player_variant or players.get(player_key, {})).get("name", player_key.replace('_', ' ').title())

    if amount > total_owned:
        embed = discord.Embed(
            description=f"❌ You only have **{total_owned} {display_name}**.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # price logic
    from players import players as players_dict, get_price_by_ovr

    player_obj = player_variant or players_dict.get(player_key)

    if player_obj and player_obj.get('price'):
        buy_price = int(player_obj['price'])
    elif player_obj and player_obj.get('ovr'):
        buy_price = get_price_by_ovr(player_obj['ovr'], player_obj.get('category'))
    else:
        buy_price = 10000

    sell_price = buy_price // 2
    total_price = sell_price * amount

    embed = discord.Embed(
        title=display_name,
        description=f"Sell **{amount} × {display_name}** for **{total_price} CC**?",
        color=discord.Color.blue()
    )

    rowids = [r[0] for r in rows[:amount]]

    # Generate card
    player_id = all_player_keys.index(player_key) if player_key in all_player_keys else 0
    file = None
    try:
        if player_obj and player_obj.get("image"):
            _, file = create_player_embed(player_obj, player_id, player_key)
        else:
            card_path = generate_card(
                player_id,
                player_obj or {
                    'name': display_name,
                    'role': 'Unknown',
                    'ovr': ovr,
                    'bat_ovr': ovr,
                    'bowl_ovr': ovr
                },
                player_key=player_key
            )
            file = discord.File(card_path, filename="card.png")

        if file:
            embed.set_image(url="attachment://card.png")
    except Exception as e:
        print("[ccsell] card generation failed:", e)

    view = SellView(ctx.author.id, player_key, rowids, total_price=total_price)
    if not responded:
        msg = await ctx.send(embed=embed, file=file if file else None, view=view)
        responded = True
        view.message = msg

@bot.command(aliases=['ccmr'])
@prevent_double_response
async def ccms(ctx, start_pos: int, end_pos: int):
    """Sell multiple players by position range. Usage: ccms <starting pos> <ending pos>"""
    refresh_squad_ovr(ctx.author.id)
    responded = False
    
    # Validate positions
    if start_pos < 1 or end_pos < 1 or start_pos > end_pos:
        embed = discord.Embed(
            description="❌ Invalid range. Use: `ccms <starting pos> <ending pos>` (e.g., `ccms 5 8`)",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    # Get squad
    cursor.execute(
        "SELECT rowid, player_key, ovr FROM squad WHERE userid=? ORDER BY rowid",
        (ctx.author.id,)
    )
    squad = cursor.fetchall()
    
    if not squad:
        embed = discord.Embed(
            description="❌ You have no players in your squad.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    squad_size = len(squad)
    
    if start_pos > squad_size or end_pos > squad_size:
        embed = discord.Embed(
            description=f"❌ Invalid positions. Your squad has **{squad_size}** players.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    # Get players to sell (positions are 1-indexed, convert to 0-indexed)
    players_to_sell = squad[start_pos - 1:end_pos]
    rowids = [r[0] for r in players_to_sell]
    
    if not players_to_sell:
        embed = discord.Embed(
            description="❌ No players in that range.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    # Calculate total sell price
    from players import players as players_dict, get_price_by_ovr
    
    total_price = 0
    player_list = []
    
    for rowid, player_key, ovr in players_to_sell:
        player_obj = players_dict.get(player_key)
        
        if player_obj and player_obj.get('price'):
            buy_price = int(player_obj['price'])
        elif player_obj and player_obj.get('ovr'):
            buy_price = get_price_by_ovr(player_obj['ovr'], player_obj.get('category'))
        else:
            buy_price = 10000
        
        sell_price = buy_price // 2
        total_price += sell_price
        
        display_name = player_obj.get("name", player_key.replace('_', ' ').title()) if player_obj else player_key.replace('_', ' ').title()
        player_list.append(f"• **{display_name}** `{ovr}`")
    
    # Create confirmation embed
    embed = discord.Embed(
        title="🛒 BULK SELL",
        description=f"Sell **{len(players_to_sell)} players** (positions {start_pos}-{end_pos}) for **{total_price:,} CC**?",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Players to Sell:",
        value="\n".join(player_list),
        inline=False
    )
    
    # Create a generic confirmation view (reuse SellView)
    # For bulk, pass None as player_key since multiple
    view = SellView(ctx.author.id, None, rowids, total_price)
    if not responded:
        msg = await ctx.send(embed=embed, view=view)
        responded = True
        view.message = msg

@bot.command(aliases=[])
@prevent_double_response
async def ccjoin(ctx, arg=None):
    global auction_players, auction_countdown_active, countdown_start_time
    responded = False

    if arg != "auction":
        return

    # Check if countdown is active
    if not auction_countdown_active or countdown_start_time is None:
        if not responded:
            await ctx.send("Auction is not open. Wait for admin to start the auction with `ccstart auction`.")
            responded = True
        return
    
    # Check if countdown has expired (5 minutes = 300 seconds)
    now = datetime.now()
    elapsed = (now - countdown_start_time).total_seconds()
    if elapsed >= 300:
        if not responded:
            await ctx.send("⏰ Countdown has ended. Auction will start or was cancelled.")
            responded = True
        return

    if ctx.author.id in auction_players:
        if not responded:
            await ctx.send("You already joined the auction.")
            responded = True
        return

    if len(auction_players) < 15:
        auction_players.append(ctx.author.id)
    else:
        if not responded:
            await ctx.send("Auction is full.")
            responded = True
        return
    time_remaining = 300 - elapsed
    minutes_remaining = int(time_remaining // 60)
    seconds_remaining = int(time_remaining % 60)

    if not responded:
        await ctx.send(
            f"✅ {ctx.author.mention} joined the auction! ({len(auction_players)}/15)\n"
            f"⏳ Time remaining: {minutes_remaining}m {seconds_remaining}s"
        )
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def cctime(ctx):
    global auction_active, auction_countdown_active, countdown_start_time
    responded = False

    if ctx.channel.id != AUCTION_CHANNEL_ID:
        if not responded:
            await ctx.send("❌ This command can only be used in the auction channel.")
            responded = True
        return

    if auction_countdown_active and countdown_start_time is not None:
        elapsed = (datetime.now() - countdown_start_time).total_seconds()
        remaining = max(0, 300 - elapsed)
        if remaining <= 0:
            if auction_active:
                if not responded:
                    await ctx.send("✅ Auction has started! Place your bids now.")
                    responded = True
            else:
                if not responded:
                    await ctx.send("⏰ The countdown has ended. Wait for the auction to start or the admin to restart it.")
                    responded = True
        else:
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            if not responded:
                await ctx.send(f"⏳ Auction starts in **{minutes}m {seconds}s**. Use `ccjoin auction` to join now.")
                responded = True
        return

    if auction_active:
        if not responded:
            await ctx.send("✅ Auction has started! Place your bids now.")
            responded = True
        return

    if not responded:
        await ctx.send("❌ No auction is active right now. Wait for admin to start the auction with `CCstart auction`.")
        responded = True
        return

@bot.command(aliases=[])
@prevent_double_response
async def ccend(ctx):
    """End the current live match, only if the user is in that match."""
    responded = False
    
    content = ctx.message.content.strip().lower()
    if content.startswith("ccplay"):
        # A ccplay request should not trigger ccend
        return

    views_module = __import__('views')
    if ctx.channel.id not in views_module.current_matches:
        if not responded:
            await ctx.send("❌ There is no match in progress in this channel.")
            responded = True
        return

    current_match = views_module.current_matches[ctx.channel.id]

    # user must be involved
    user = ctx.author
    if user != current_match.p1 and user != current_match.p2:
        if not responded:
            await ctx.send("❌ You are not part of the ongoing match, you cannot end it.")
            responded = True
        return

    # End the match
    del views_module.current_matches[ctx.channel.id]
    if not responded:
        await ctx.send(f"🛑 Match cancelled by {user.mention}. The current match has been ended.")
        responded = True

@bot.command(aliases=[])
@prevent_double_response
async def cccd(ctx):
    responded = False
    """Show cooldown timings for daily and reward claims."""
    now = int(time.time())
    
    # Check if user is registered
    cursor.execute("SELECT * FROM users WHERE id=?", (ctx.author.id,))
    user = cursor.fetchone()
    if not user:
        embed = discord.Embed(
            description="❌ Use ccdeb first to register your team.",
            color=discord.Color.red()
        )
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return
    
    embed = discord.Embed(
        title="⏱️ COOLDOWN STATUS",
        description=f"Reward timings for **{ctx.author.name}**",
        color=discord.Color.blurple()
    )
    
    # ===== DAILY COOLDOWN =====
    cursor.execute("SELECT last_claim, streak FROM daily_rewards WHERE userid=?", (ctx.author.id,))
    daily_row = cursor.fetchone()
    
    if daily_row:
        last_claim, streak = daily_row
        time_since = now - last_claim
        
        if time_since < 86400:
            remaining = 86400 - time_since
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            
            daily_status = f"⏳ **COOLDOWN ACTIVE**\n⏰ Ready in: **{hours}h {minutes}m {seconds}s**\n🔥 Streak: **{streak}** day(s)"
            daily_color = "🟠"
        else:
            daily_status = f"✅ **READY TO CLAIM**\n💰 Reward: **5,000 CC** + Streak bonus\n🔥 Streak: **{streak}** day(s)"
            daily_color = "🟢"
    else:
        daily_status = "✅ **READY TO CLAIM**\n💰 Reward: **5,000 CC** (First claim)\n🔥 Streak: **0** day(s)"
        daily_color = "🟢"
    
    embed.add_field(
        name=f"{daily_color} DAILY REWARD",
        value=daily_status,
        inline=False
    )
    
    # ===== CCDROP COOLDOWN =====
    cursor.execute("SELECT last_drop FROM drops WHERE userid=?", (ctx.author.id,))
    drop_row = cursor.fetchone()
    
    if drop_row:
        last_drop = drop_row[0]
        time_since_drop = now - last_drop
        
        if time_since_drop < 3600:
            remaining = 3600 - time_since_drop
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            
            ccdrop_status = f"⏳ **COOLDOWN ACTIVE**\n⏰ Ready in: **{hours}h {minutes}m {seconds}s**"
            ccdrop_color = "🟠"
        else:
            ccdrop_status = "✅ **READY TO CLAIM**\n🎁 Reward: **Money or Player Card** (50/50)\n💰 Money Range: 1K-60K CC"
            ccdrop_color = "🟢"
    else:
        ccdrop_status = "✅ **READY TO CLAIM**\n🎁 Reward: **Money or Player Card** (50/50)\n💰 Money Range: 1K-60K CC"
        ccdrop_color = "🟢"
    
    embed.add_field(
        name=f"{ccdrop_color} CCDROP",
        value=ccdrop_status,
        inline=False
    )
    
    # ===== CCMONTHLY PROGRESS =====
    cursor.execute("SELECT points FROM users WHERE id=?", (ctx.author.id,))
    points_row = cursor.fetchone()
    points = points_row[0] if points_row and points_row[0] is not None else 0
    monthly_required = 800
    cursor.execute("SELECT last_claim FROM ccmonthly_claims WHERE userid=?", (ctx.author.id,))
    monthly_row = cursor.fetchone()

    if points < monthly_required:
        if monthly_row:
            remaining = 2592000 - (now - monthly_row[0])
            days_left = remaining // 86400 if remaining > 0 else 0
            if remaining > 0:
                wait_text = format_seconds(remaining)
                monthly_status = (
                    f"⏳ **NOT ELIGIBLE**\n"
                    f"🏅 Points: **{points}/{monthly_required}**\n"
                    f"Days left to claim monthly: {days_left}"
                )
            else:
                monthly_status = (
                    f"⏳ **NOT ELIGIBLE**\n"
                    f"🏅 Points: **{points}/{monthly_required}**\n"
                    f"Days left to claim monthly: {days_left}"
                )
        else:
            days_left = 0
            monthly_status = (
                f"⏳ **NOT ELIGIBLE**\n"
                f"🏅 Points: **{points}/{monthly_required}**\n"
                f"Days left to claim monthly: {days_left}"
            )
        monthly_color = "🟠"
    else:
        if not monthly_row:
            monthly_status = (
                f"✅ **READY TO CLAIM**\n"
                f"🏅 Points: **{points}/{monthly_required}**\n"
                f"🎁 Use `ccmonthly` to claim your monthly reward."
            )
            monthly_color = "🟢"
        else:
            remaining = 2592000 - (now - monthly_row[0])
            if remaining > 0:
                wait_text = format_seconds(remaining)
                monthly_status = (
                    f"⏳ **CLAIMED**\n"
                    f"🏅 Points: **{points}/{monthly_required}**\n"
                    f"⏰ Next monthly claim in: **{wait_text}**"
                )
                monthly_color = "🟠"
            else:
                monthly_status = (
                    f"✅ **READY TO CLAIM**\n"
                    f"🏅 Points: **{points}/{monthly_required}**\n"
                    f"🎁 Use `ccmonthly` to claim your monthly reward."
                )
                monthly_color = "🟢"

    embed.add_field(
        name=f"{monthly_color} MONTHLY PROGRESS",
        value=monthly_status,
        inline=False
    )

    embed.set_footer(text="Use cc daily and cc drop to claim your rewards!")
    
    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(name="cchelp", aliases=[])
@prevent_double_response
async def cchelp(ctx):
    responded = False
    embed = discord.Embed(
        title="CCBot Help",
        description="**Use these commands to manage your team and play matches**",
        color=discord.Color.blue()
    )
    embed.add_field(name="**ccdeb**", value="Register and get your starter squad + 10,000 CC.", inline=False)
    embed.add_field(name="**ccdaily**", value="Claim daily 5,000 CC (24h cooldown). 7-day streak = random player!", inline=False)
    embed.add_field(name="**cclb**", value="Show the top 10 leaderboard and your rank. Earn points from matches, daily claims, and buys.", inline=False)
    embed.add_field(name="**ccpoints**", value="Show your current points, rank, and how to earn more points.", inline=False)
    embed.add_field(name="**ccmonthly**", value="Claim monthly rewards when you reach 800 points. Includes coins and a Monthly Claim pack.", inline=False)
    embed.add_field(name="**ccpacks**", value="Open your available packs, including Monthly Claim and shop packs.", inline=False)
    embed.add_field(name="**ccpack / ccshop**", value="Browse and purchase pack bundles in the shop.", inline=False)
    embed.add_field(name="**ccreward**", value="Claim a one-time random XI (requires empty/small squad).", inline=False)
    embed.add_field(name="**cccd**", value="Show cooldown timings for daily and ccreward claims.", inline=False)
    embed.add_field(name="**ccinfo**", value="Show your team name and current balance.", inline=False)
    embed.add_field(name="**ccteam**", value="List all players in your squad.", inline=False)
    embed.add_field(name="**ccxi**", value="Show your current playing XI (first 11 players).", inline=False)
    embed.add_field(name="**ccname <name>**", value="Rename your team.", inline=False)
    embed.add_field(name="**ccbuy <player>**", value="Buy a player from the market.", inline=False)
    embed.add_field(name="**ccsell <player>**", value="Sell a player from your squad for CC.", inline=False)
    embed.add_field(name="**ccms <start_pos> <end_pos>**", value="Sell multiple players by position range (e.g., `ccms 5 8`). Alias: `ccmr`.", inline=False)
    embed.add_field(name="**ccaddp @user <points>**", value="Admin only: add leaderboard points to a user.", inline=False)
    embed.add_field(name="**ccbid <amount>**", value="Bid a specific amount in an active auction.", inline=False)
    embed.add_field(name="**ccswap <pos1> <pos2>**", value="Swap squad positions (top 11 = XI).", inline=False)
    embed.add_field(name="**ccstats <player>**", value="Show detailed stats for a player.", inline=False)

    if not responded:
        await ctx.send(embed=embed)
        responded = True

@bot.command(aliases=['pstats'])
@prevent_double_response
async def ccstats(ctx, *, name: str):
    responded = False

    canonical_key = get_player_key_from_name(name)
    if not canonical_key:
        embed = discord.Embed(description="❌ Player not found.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Squad Check
    cursor.execute("SELECT player_key FROM squad WHERE userid=? AND player_key = ?", (ctx.author.id, canonical_key))
    if not cursor.fetchone():
        embed = discord.Embed(description="❌ You can only view stats for players in your squad.", color=discord.Color.red())
        if not responded:
            await ctx.send(embed=embed)
            responded = True
        return

    # Data Fetching
    cursor.execute("SELECT * FROM player_stats WHERE player = ?", (canonical_key,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT OR IGNORE INTO player_stats (player) VALUES (?)", (canonical_key,))
        db.commit()
        cursor.execute("SELECT * FROM player_stats WHERE player = ?", (canonical_key,))
        row = cursor.fetchone()

    (
        player_db_name,
        bat_inn, bat_runs, bat_balls, bat_outs, bat_50s, bat_100s, bat_best, bat_notout,
        bowl_inn, bowl_balls, bowl_wkts, bowl_3w, bowl_5w, bowl_runs, bowl_best_wkts, bowl_best_runs
    ) = row

    # Calculations
    avg = bat_runs / bat_outs if bat_outs > 0 else bat_runs
    sr = (bat_runs / bat_balls * 100) if bat_balls > 0 else 0
    eco = (bowl_runs * 6 / bowl_balls) if bowl_balls > 0 else 0
    bowl_avg = (bowl_runs / bowl_wkts) if bowl_wkts > 0 else 0
    best_score = f"{bat_best}*" if bat_notout else str(bat_best)
    best_bowl = f"{bowl_best_wkts}/{bowl_best_runs}" if bowl_best_wkts > 0 else "-"

    batting_data = {
        'inn': bat_inn, 'runs': bat_runs, '50s': bat_50s, '100s': bat_100s,
        '4s': 0, '6s': 0, 'avg': avg, 'sr': sr, 'hs': best_score
    }
    bowling_data = {
        'inn': bowl_inn, 'wkts': bowl_wkts, '3w': bowl_3w, '5w': bowl_5w,
        'hat': 0, 'avg': bowl_avg, 'eco': eco, 'best': best_bowl
    }

    player_data = players.get(canonical_key)
    card_img = None

    if player_data:
        try:
            player_id = all_player_keys.index(canonical_key) if canonical_key in all_player_keys else 0
            if player_data.get("image"):
                image_path = Path(player_data["image"])
                if not image_path.is_absolute():
                    image_path = Path(__file__).resolve().parent / player_data["image"]
                card_img = Image.open(image_path).convert("RGBA")
            else:
                card_path = generate_card(player_id, player_data, player_key=canonical_key)
                card_img = Image.open(card_path).convert("RGBA")
        except Exception as e:
            print(f"Error preparing player card image for stats: {e}")

    display_name = get_player_display_name(canonical_key)
    owner_name = ctx.author.display_name
    
    value = player_data.get("price", 0) if player_data else 0
    try:
        value = int(value)
    except Exception:
        value = 0
    potms = player_data.get("potm", 0) if player_data else 0

    stats_buf = generate_fancy_stats_image(
        display_name, owner_name, value, potms, batting_data, bowling_data, card_img=card_img
    )

    stats_file = discord.File(stats_buf, filename="player_stats.png")
    files = [stats_file]

    embed = discord.Embed(color=discord.Color.from_rgb(47, 49, 54))
    embed.set_image(url="attachment://player_stats.png")

    if not responded:
        await ctx.send(embed=embed, files=files)
        responded = True

@bot.command(name="ccbid", aliases=[])
@prevent_double_response
async def ccbid(ctx, amount: int = None):
    global current_bid, highest_bidder, last_bid_time, last_user_bid
    responded = False

    if not auction_active:
        if not responded:
            await ctx.send("❌ Wait until an auction starts before bidding.")
            responded = True
        return

    if ctx.author.id not in auction_players:
        if not responded:
            await ctx.send("❌ You didn't join the auction.")
            responded = True
        return

    if highest_bidder == ctx.author.id:
        if not responded:
            await ctx.send("❌ You are already the highest bidder. You cannot outbid yourself.")
            responded = True
        return

    if amount is None:
        amount = current_bid + max(1, (current_bid * 5 + 99) // 100)

    auction_minimum = 10000
    if auction_card and auction_card in players:
        auction_minimum = get_auction_minimum(players[auction_card].get("ovr", 0), players[auction_card].get("category", "N"))

    if amount < auction_minimum:
        if not responded:
            await ctx.send(f"❌ Minimum bid is {auction_minimum:,} CC.")
            responded = True
        return

    if amount <= current_bid:
        if not responded:
            await ctx.send(f"❌ Bid must be higher than the current bid of {current_bid:,} CC.")
            responded = True
        return

    now = time.time()

    if ctx.author.id in last_user_bid:
        if now - last_user_bid[ctx.author.id] < 2:
            if not responded:
                await ctx.send("⏳ Slow down! Wait before bidding again.")
                responded = True
            return

    last_user_bid[ctx.author.id] = now

    try:
        cursor.execute(
            "SELECT COUNT(*) FROM squad WHERE userid=?",
            (ctx.author.id,)
        )
        squad_count = cursor.fetchone()[0]
        if squad_count >= 22:
            if not responded:
                await ctx.send(
                    "❌ Your squad already has 22 or more players. You cannot bid in the auction."
                )
                responded = True
            return

        cursor.execute(
            "SELECT balance FROM users WHERE id=?",
            (ctx.author.id,)
        )

        result = cursor.fetchone()
        if result is None:
            if not responded:
                await ctx.send("❌ You are not registered. Use ccdeb first.")
                responded = True
            return

        balance = result[0]

        if balance < amount:
            if not responded:
                await ctx.send("❌ Not enough CC.")
                responded = True
            return

        auction_ovr = None
        if auction_card and auction_card in players:
            auction_ovr = players[auction_card].get("ovr")

        if auction_ovr is not None and user_owns_player_variant(ctx.author.id, auction_card, ovr=auction_ovr):
            if not responded:
                await ctx.send("❌ You already own the exact auctioned variant.")
                responded = True
            return

        current_bid = amount
        highest_bidder = ctx.author.id
        last_bid_time = datetime.now()

        if not responded:
            await ctx.send(
                f"💰 {ctx.author.mention} bid **{current_bid:,} CC**!\n"
                f"👑 Highest bidder: <@{highest_bidder}>"
            )
            responded = True
    except Exception as e:
        if not responded:
            await ctx.send(f"❌ Error placing bid: {str(e)}")
            responded = True

@bot.event
async def on_ready():
    print("Bot is ready!")
    if not auction_scheduler.is_running():
        auction_scheduler.start()

_processed_message_ids = set()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip().lower()
    if not (content.startswith("CC") or content.startswith("cc")) and not content.startswith(bot.user.mention):
        return

    if message.id in _processed_message_ids:
        return

    ctx = await bot.get_context(message)

    if message.channel.category_id in BOT_COMMAND_CATEGORY_IDS:
        bot_channel_mentions = " ".join(f"<#{cid}>" for cid in BOT_COMMAND_CHANNEL_IDS)
        await message.channel.send(f"Please use the bot command channels: {bot_channel_mentions}")
        return

    if message.channel.id in CHANNELS_EXCEPT_CCPLAY and ctx.command:
        if ctx.command.name == "ccplay":
            await message.channel.send("ccplay is disabled in this channel. Please use <#1490662892431999047> <#1490663044274061373> <#1490663082115076097> instead.")
            return

    if message.channel.id in CHANNELS_AUCTION_ONLY and ctx.command:
        if ctx.command.name not in ("ccbid", "ccjoin"):
            await message.channel.send("Only auction commands are allowed here: `ccbid`, and `ccjoin auction`.")
            return

    if message.channel.id in CHANNELS_EXCEPT_CCID_CCPLAY_CCJOIN and ctx.command:
        if ctx.command.name in ("ccbid", "ccplay", "ccjoin"):
            await message.channel.send("`ccbid`, `ccplay`, and `ccjoin auction` are disabled in this channel.")
            return

    if ctx.command:
        _processed_message_ids.add(message.id)
        await bot.invoke(ctx)
        return

bot.run("MTQ4MDUzNTkxNjAwMjE1MjUwMA.Gdsh84.98Y7An3LZkTWLOscGf-W5Z1UxxRKfpy0EEgZLU")