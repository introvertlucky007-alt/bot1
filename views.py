import discord
import sqlite3
import random
import asyncio
import traceback
from pathlib import Path
import aiohttp

from gifs import get_gif
from engine import play_pace_ball, play_offspin_ball, play_legspin_ball, BALL_TYPES, generate_pitch, get_ovr


async def safe_channel_send(channel, *args, max_retries=2, **kwargs):
    if channel is None:
        return None

    for attempt in range(max_retries + 1):
        try:
            return await channel.send(*args, **kwargs)
        except (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            if attempt >= max_retries:
                print(f"Channel.send failed after {max_retries + 1} attempts: {exc}")
                traceback.print_exc()
                return None
            await asyncio.sleep(0.5 * (attempt + 1))
        except Exception as exc:
            print(f"Unexpected channel.send exception: {exc}")
            traceback.print_exc()
            return None


async def safe_interaction_edit(interaction, *, content=None, embed=None, view=None, attachments=None):
    if attachments is None:
        attachments = []
    elif isinstance(attachments, discord.File):
        attachments = [attachments]
    else:
        try:
            attachments = list(attachments)
        except TypeError:
            attachments = []

    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=content, embed=embed, view=view, attachments=attachments)
        else:
            await interaction.edit_original_response(content=content, embed=embed, view=view, attachments=attachments)
    except discord.errors.NotFound:
        if interaction.message is not None:
            try:
                await interaction.message.edit(content=content, embed=embed, view=view, attachments=attachments)
            except Exception:
                pass
    except Exception as exc:
        print(f"safe_interaction_edit failed: {exc}")
        raise


async def send_gif(channel, gif_url, max_retries=2):
    if not gif_url or channel is None:
        return

    await safe_channel_send(channel, content=gif_url, max_retries=max_retries)


async def send_scorecard_image(channel, match):
    if channel is None or match is None:
        return
    try:
        card_path = generate_final_scorecard_image(match)
        if card_path and Path(card_path).exists():
            await safe_channel_send(channel, file=discord.File(str(card_path), filename="scorecard.png"))
            return
        print(f"WARNING: Scorecard image path missing or does not exist: {card_path}")
        await safe_channel_send(channel, "⚠️ Could not attach the final scorecard image.")
    except Exception as e:
        print(f"ERROR sending final scorecard image: {e}")
        traceback.print_exc()
        try:
            await safe_channel_send(channel, "⚠️ Could not attach the final scorecard image.")
        except Exception:
            pass
from scorecard import score_embed, innings_summary_embed, generate_final_scorecard_image
from match import Match
from players import players
from card_generator import create_player_embed

# 4-Run Commentary Messages (25% probability each - 4 messages total)
FOUR_RUN_COMMENTARY = [
    "**{player}** beautifully played! That races away to the boundary for four",
    "**{player}** shows pure timing—no chance for the fielders, that's four!",
    "**{player}** cracked it! Finds the gap and that's a boundary",
    "**{player}** shows class written all over it—glides to the fence for four"
]

# 6-Run Commentary Messages (16.67% probability each - 6 messages total)
SIX_RUN_COMMENTARY = [
    "**{player}** launches it huge! Into the stands for six!",
    "**{player}** picked up and dismissed! That's gone all the way!",
    "**{player}** delights the crowd—maximum!",
    "**{player}** hits it right off the middle—sails over the boundary for six!",
    "**{player}** plays a statement shot! Six runs",
    "**{player}** goes BANG! Six!"
]

db = None
cursor = None

current_matches = {}

all_player_entries = list(players.items())
all_player_keys = [key for key, _ in all_player_entries]

PACKS_DATA = {
    "wpl_2026": {
        "name": "WPL 2026 Pack",
        "price": 1200000,
        "banner": "C:/VCBOT/templates/pack banners/WPL 2026 Banner.png",
        "pool": [
            ("harmanpreet_kaur_S", 7),
            ("lizelle_lee_S", 12),
            ("shree_charani_S", 9),
            ("nadine_de_klerk_S", 8),
            ("jemimah_rodrigues_S", 11),
            ("lauren_bell_S", 7),
            ("nandini_sharma_S", 7),
            ("nat_sciver_brunt_S", 8),
            ("richa_ghosh_S", 8),
            ("shreyanka_patil_S", 9),
            ("smriti_mandhana_S", 8),
            ("sophie_devine_S", 6)
        ]
    },
    "t20_wc": {
        "name": "T20 World Cup Pack",
        "price": 1800000,
        "banner": "C:/VCBOT/templates/pack banners/T20 WC banner.png",
        "pool": [
            ("finn_allen_S", 7),
            ("tim_seifert_S", 7),
            ("sahibzada_farhan_S", 7),
            ("ishan_kishan_S", 9),
            ("shivam_dube_S", 11),
            ("jasprit_bumrah_S", 5),
            ("varun_chakravarthy_S", 8),
            ("hardik_pandya_S", 7),
            ("will_jacks_S", 7),
            ("adil_rashid_S", 9),
            ("blessing_muzarabani_S", 7),
            ("lungi_ngidi_S", 10),
            ("sanju_samson_S", 6),
        ]
    },
    "sa20": {
        "name": "SA20 Pack",
        "price": 1300000,
        "banner": "C:/VCBOT/templates/pack banners/SA20 Banner.png",
        "pool": [
            ("quinton_de_kock_S", 7),
            ("jonny_bairstow_S", 9),
            ("ryan_rickelton_S", 8),
            ("dewald_brevis_S", 7),
            ("mathew_breetzke_S", 11),
            ("aiden_markram_S", 9),
            ("sherfane_rutherford_S", 8),
            ("sikandar_raza_S", 10),
            ("marco_jansen_S", 8),
            ("anrich_nortje_S", 6),
            ("ottniel_baartman_S", 8),
            ("keshav_maharaj_S", 9)
        ]
    },
    "ipl_legends": {
        "name": "IPL Legends Pack",
        "price": 2500000,
        "banner": "C:/VCBOT/templates/pack banners/IPL Legends.png",
        "pool": [
            ("david_warner_S", 4),
            ("bhuvaneshwar_kumar_S", 6),
            ("ab_de_villiers_S", 4),
            ("dwayne_bravo_S", 6),
            ("lasith_malinga_S", 6),
            ("chris_gayle_S", 5),
            ("suresh_raina_S", 8),
            ("piyush_chawla_S", 10),
            ("shane_watson_S", 6),
            ("shikar_dhawan_S", 10),
            ("shane_warne_S", 8),
            ("ravi_ashwin_S", 8),
            ("sunil_narine_S", 7),
            ("kieron_pollard_S", 8),
            ("ms_dhoni_S", 4)
        ]
    }
}

def init_db(database_connection, database_cursor):
    """Initialize database connection from bot.py"""
    global db, cursor
    db = database_connection
    cursor = database_cursor


def add_user_points(user_id, amount):
    if not isinstance(amount, int) or amount == 0:
        return
    cursor.execute(
        "UPDATE users SET points = COALESCE(points, 0) + ? WHERE id = ?",
        (amount, user_id)
    )
    db.commit()


def normalize_player_name(name):
    """Normalize player name for comparison"""
    if not isinstance(name, str):
        return ""
    return name.strip().lower()


def get_player_key_from_name(name):
    """Get player key from display name or key"""
    normalized = normalize_player_name(name)
    if not normalized:
        return None

    # Exact key match (case-sensitive)
    if normalized in players:
        return normalized

    # Case-insensitive key match
    normalized_key = normalized.replace(" ", "_")
    for key in players.keys():
        if key.lower() == normalized_key:
            return key

    # Find by display name
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == normalized:
            return key

    # Try underscore/space alternates
    normalized_underscore = normalized.replace(" ", "_")
    if normalized_underscore in players:
        return normalized_underscore

    # Partial match
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if normalized == pdata_name or normalized in pdata_name or pdata_name in normalized:
            return key

    return None


def get_player_display_name(player_name):
    """Get the display name for a player (e.g., 'Virat Kohli' instead of 'virat_kohli')"""
    if not player_name:
        return player_name
    key = get_player_key_from_name(player_name)
    if key:
        return players[key].get("name", player_name)
    return player_name


def get_current_player_ovr(player_name):
    """Get player OVR dynamically from players.py (not from database)"""
    key = get_player_key_from_name(player_name)
    if not key:
        return None
    ov = players.get(key, {}).get("ovr")
    return int(ov) if isinstance(ov, (int, float)) else None


def get_canonical_player_name(player_name):
    """Return a normalized canonical player identifier for UI and selection values."""
    if not player_name:
        return player_name
    player_key = get_player_key_from_name(player_name)
    return player_key if player_key else player_name


def canonicalize_player_list(player_list):
    seen = set()
    canonical_list = []
    for player in player_list:
        canonical = get_canonical_player_name(player)
        if canonical not in seen:
            seen.add(canonical)
            canonical_list.append(canonical)
    return canonical_list


def get_ball_name(ball):
    """Format ball dictionary into readable name"""
    if ball.get("style") == "pace":
        parts = []
        if ball.get("swing"):
            parts.append(ball["swing"])
        if ball.get("length"):
            parts.append(ball["length"])
        if ball.get("variation"):
            parts.append(ball["variation"])
        return " ".join(parts) if parts else "Fast Ball"
    elif ball.get("style") == "offspin":
        return ball.get("type", "Off Spin")
    elif ball.get("style") == "legspin":
        return ball.get("type", "Leg Spin")
    return "Unknown Ball"

def get_player_by_name(player_name):
    """
    Find player object by name with intelligent matching.
    Handles:
    - Direct exact match (normalized)
    - Exact key match
    - Last name matching (for abbreviations like V Chakravarthy)
    - Substring/partial matching
    Returns player dict or empty dict if not found
    """
    if not player_name:
        return {}
    
    player_name_normalized = player_name.strip().lower()
    
    # Strategy 0: Exact key match or underscore/space alternate key match
    if player_name_normalized in players:
        return players[player_name_normalized]
    for key in players:
        if key.strip().lower() == player_name_normalized:
            return players[key]
    alt_key = player_name_normalized.replace(" ", "_")
    if alt_key in players:
        return players[alt_key]
    for key in players:
        if key.strip().lower() == alt_key:
            return players[key]
    alt_key = player_name_normalized.replace("_", " ")
    if alt_key in players:
        return players[alt_key]
    for key in players:
        if key.strip().lower() == alt_key:
            return players[key]
    
    # Strategy 1: Exact normalized match
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if pdata_name == player_name_normalized:
            return pdata
    
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
                first_part = player_parts[0]
                pdata_first = pdata_parts[0]
                if first_part in pdata_first or pdata_first in first_part:
                    return pdata
    
    # Strategy 3: Substring match
    for key, pdata in players.items():
        if not pdata:
            continue
        pdata_name = pdata.get("name", "").strip().lower()
        if player_name_normalized in pdata_name or pdata_name in player_name_normalized:
            return pdata
    
    return {}

def get_player_role(player_name):
    """
    Get player role with intelligent name matching.
    Handles:
    - Case-insensitive key matches including spaces/underscores
    - Display name match (normalized)
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
    
    # Strategy 1: Exact normalized match
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
    
    return "Unknown"

def get_current_match(channel):
    channel_id = getattr(channel, "id", None)
    if channel_id is None:
        return None
    return current_matches.get(channel_id)

def is_match_player(user, channel):
    current_match = get_current_match(channel)
    if not current_match:
        return False
    return user.id == current_match.p1.id or user.id == current_match.p2.id

def get_match_reward(max_overs):
    """Calculate winner and loser rewards based on match overs."""
    if max_overs <= 5:
        winner_reward = 5000
    elif max_overs <= 10:
        winner_reward = 10000
    elif max_overs == 20:
        winner_reward = 30000
    else:  # 11-19 overs
        winner_reward = 20000
    
    loser_reward = winner_reward // 2
    return winner_reward, loser_reward

def update_innings_stats(batting_stats, bowling_stats, striker, non_striker, team1, team2):
    # Only update stats for players that are actually in the match squads
    all_match_players = set(team1 + team2)

    # Update batting stats - only for players in the match
    for player, stats in batting_stats.items():
        if player not in all_match_players:
            continue  # Skip players not in match squads

        runs = stats["runs"]
        balls = stats["balls"]
        not_out = player in [striker, non_striker]
        
        # Only update innings if the player actually batted
        if balls > 0:
            cursor.execute("INSERT OR IGNORE INTO player_stats (player) VALUES (?)", (player,))
            cursor.execute("UPDATE player_stats SET bat_innings = bat_innings + 1, bat_runs = bat_runs + ?, bat_balls = bat_balls + ? WHERE player = ?", (runs, balls, player))
            if runs >= 50:
                cursor.execute("UPDATE player_stats SET bat_50s = bat_50s + 1 WHERE player = ?", (player,))
            if runs >= 100:
                cursor.execute("UPDATE player_stats SET bat_100s = bat_100s + 1 WHERE player = ?", (player,))
            # Check best score
            cursor.execute("SELECT bat_best, bat_best_notout FROM player_stats WHERE player = ?", (player,))
            row = cursor.fetchone()
            if row:
                current_best, current_notout = row
                if runs > current_best or (runs == current_best and not_out and not current_notout):
                    cursor.execute("UPDATE player_stats SET bat_best = ?, bat_best_notout = ? WHERE player = ?", (runs, 1 if not_out else 0, player))

    # Update bowling stats - only for players in the match
    for player, stats in bowling_stats.items():
        if player not in all_match_players:
            continue  # Skip players not in match squads

        wkts = stats["wickets"]
        balls = stats["balls"]
        runs = stats["runs"]
        
        # Only update innings if the player actually bowled
        if balls > 0:
            cursor.execute("INSERT OR IGNORE INTO player_stats (player) VALUES (?)", (player,))
            cursor.execute("UPDATE player_stats SET bowl_innings = bowl_innings + 1, bowl_balls = bowl_balls + ?, bowl_wickets = bowl_wickets + ?, bowl_runs = bowl_runs + ? WHERE player = ?", (balls, wkts, runs, player))
            if wkts >= 3:
                cursor.execute("UPDATE player_stats SET bowl_3w = bowl_3w + 1 WHERE player = ?", (player,))
            if wkts >= 5:
                cursor.execute("UPDATE player_stats SET bowl_5w = bowl_5w + 1 WHERE player = ?", (player,))
            # Check best spell
            cursor.execute("SELECT bowl_best_wkts, bowl_best_runs FROM player_stats WHERE player = ?", (player,))
            row = cursor.fetchone()
            if row:
                current_best_wkts, current_best_runs = row
                if wkts > current_best_wkts or (wkts == current_best_wkts and runs < current_best_runs):
                    cursor.execute("UPDATE player_stats SET bowl_best_wkts = ?, bowl_best_runs = ? WHERE player = ?", (wkts, runs, player))

    db.commit()

class SafeResponseView(discord.ui.View):
    async def _safe_response_send(self, interaction, *args, **kwargs):
        try:
            await interaction.response.send_message(*args, **kwargs)
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"SafeResponseView response send error: {e}")

    async def _safe_response_edit(self, interaction, *args, **kwargs):
        try:
            await interaction.response.edit_message(*args, **kwargs)
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"SafeResponseView response edit error: {e}")


class LegSpinView(SafeResponseView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Leg Break", row=0, style=discord.ButtonStyle.green)
    async def legbreak(self, interaction, button):
        await self.handle_selection(interaction, "Leg Break")

    @discord.ui.button(label="Top Spinner", row=0, style=discord.ButtonStyle.green)
    async def topspinner(self, interaction, button):
        await self.handle_selection(interaction, "Top Spinner")

    @discord.ui.button(label="Googly", row=0, style=discord.ButtonStyle.green)
    async def googly(self, interaction, button):
        await self.handle_selection(interaction, "Googly")

    @discord.ui.button(label="Flipper", row=0, style=discord.ButtonStyle.green)
    async def flipper(self, interaction, button):
        await self.handle_selection(interaction, "Flipper")

    @discord.ui.button(label="Slider", row=0, style=discord.ButtonStyle.green)
    async def slider(self, interaction, button):
        await self.handle_selection(interaction, "Slider")

    async def handle_selection(self, interaction, ball_type):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.bowling.id:
            await interaction.response.send_message(
                "❌ Only bowling team can select bowling options.",
                ephemeral=True
            )
            return
        try:
            current_match.ball = {
                "style": "legspin",
                "type": ball_type
            }
            bowler_display_name = get_player_display_name(current_match.current_bowler)
            await self._safe_response_edit(
                interaction,
                content=f"**{bowler_display_name}** bowled {ball_type}.",
                view=None
            )
            await safe_channel_send(interaction.channel, f"{current_match.batting.mention} get ready to play!", view=ShotView())
        except Exception as exc:
            print(f"LegSpinView handle_selection error: {exc}")
            traceback.print_exc()
            await self._safe_response_send(interaction, "❌ A connection error occurred. Please try again.", ephemeral=True)
class OffSpinView(SafeResponseView):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Off Break", row=0, style=discord.ButtonStyle.red)
    async def offbreak(self, interaction, button):
        await self.handle_selection(interaction, "Off Break")

    @discord.ui.button(label="Doosra", row=0, style=discord.ButtonStyle.red)
    async def doosra(self, interaction, button):
        await self.handle_selection(interaction, "Doosra")

    @discord.ui.button(label="Arm Ball", row=0, style=discord.ButtonStyle.red)
    async def armball(self, interaction, button):
        await self.handle_selection(interaction, "Arm Ball")

    @discord.ui.button(label="Flighted", row=0, style=discord.ButtonStyle.red)
    async def flighted(self, interaction, button):
        await self.handle_selection(interaction, "Flighted")

    @discord.ui.button(label="Quicker One", row=0, style=discord.ButtonStyle.red)
    async def quicker(self, interaction, button):
        await self.handle_selection(interaction, "Quicker One")

    async def handle_selection(self, interaction, ball_type):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.bowling.id:
            await interaction.response.send_message(
                "❌ Only bowling team can select bowling options.",
                ephemeral=True
            )
            return
        try:
            current_match.ball = {
                "style": "offspin",
                "type": ball_type
            }
            bowler_display_name = get_player_display_name(current_match.current_bowler)
            await self._safe_response_edit(
                interaction,
                content=f"**{bowler_display_name}** bowled {ball_type}.",
                view=None
            )
            await safe_channel_send(interaction.channel, f"{current_match.batting.mention} get ready to play!", view=ShotView())
        except Exception as exc:
            print(f"OffSpinView handle_selection error: {exc}")
            traceback.print_exc()
            await self._safe_response_send(interaction, "❌ A connection error occurred. Please try again.", ephemeral=True)


class PaceBowlingView(SafeResponseView):
    # Mapping for display names
    DISPLAY_NAMES = {
        "Good Length": "Good",
        "Full Length": "Full",
        "Back of Length": "Knuckle",
        "Inswinger": "In-swing",
        "Outswinger": "Out-swing",
        "Yorker": "Yorker",
        "Bouncer": "Bouncer",
        "Slow": "Slow",
        "Fast": "Fast",
        "Wide Yorker": "Wide Yorker"
    }
    
    def __init__(self, step=1):
        super().__init__(timeout=None)
        self.step = step  # 1 = first row, 2 = second row, 3 = done
        self.selected_length = None
        self.selected_swing = None
        self.selected_variation = None
        self.display_length = None
        self.display_swing = None
        self.display_variation = None
        # Set initial enabled/disabled state
        for item in self.children:
            if hasattr(item, 'row'):
                if self.step == 1:
                    item.disabled = item.row != 0
                elif self.step == 2:
                    item.disabled = item.row != 1
                else:
                    item.disabled = True

    # ROW 1
    @discord.ui.button(label="Inswinger", row=0, style=discord.ButtonStyle.green)
    async def inswing_btn(self, interaction, button):
        await self.handle_row1(interaction, "Inswinger", "In-swing")

    @discord.ui.button(label="Outswinger", row=0, style=discord.ButtonStyle.green)
    async def outswing_btn(self, interaction, button):
        await self.handle_row1(interaction, "Outswinger", "Out-swing")

    @discord.ui.button(label="Slow", row=0, style=discord.ButtonStyle.green)
    async def slow_btn(self, interaction, button):
        await self.handle_row1(interaction, "Slow", "Slow")

    @discord.ui.button(label="Fast", row=0, style=discord.ButtonStyle.green)
    async def fast_btn(self, interaction, button):
        await self.handle_row1(interaction, "Fast", "Fast")

    @discord.ui.button(label="Knuckle", row=0, style=discord.ButtonStyle.green)
    async def knuckle_btn(self, interaction, button):
        await self.handle_row1(interaction, "Back of Length", "Knuckle")

    # ROW 2
    @discord.ui.button(label="Good", row=1, style=discord.ButtonStyle.red)
    async def good_length_btn(self, interaction, button):
        await self.handle_row2(interaction, "Good Length", "Good")

    @discord.ui.button(label="Full", row=1, style=discord.ButtonStyle.red)
    async def full_length_btn(self, interaction, button):
        await self.handle_row2(interaction, "Full Length", "Full")

    @discord.ui.button(label="Yorker", row=1, style=discord.ButtonStyle.red)
    async def yorker(self, interaction, button):
        await self.handle_row2(interaction, "Yorker", "Yorker")

    @discord.ui.button(label="Bouncer", row=1, style=discord.ButtonStyle.red)
    async def bouncer(self, interaction, button):
        await self.handle_row2(interaction, "Bouncer", "Bouncer")

    @discord.ui.button(label="Wide Yorker", row=1, style=discord.ButtonStyle.red)
    async def widey(self, interaction, button):
        await self.handle_row2(interaction, "Wide Yorker", "Wide Yorker")

    async def handle_row1(self, interaction, ball_type, display_name):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.bowling.id:
            await interaction.response.send_message(
                "❌ Only bowling team can select bowling options.",
                ephemeral=True
            )
            return
        # Set the selected swing, variation, or length
        if ball_type in ["Inswinger", "Outswinger"]:
            self.selected_swing = ball_type
            self.display_swing = display_name
        elif ball_type in ["Slow", "Fast"]:
            self.selected_length = ball_type
            self.display_length = display_name
        elif ball_type == "Back of Length":
            self.selected_variation = ball_type
            self.display_variation = display_name

        # Move to the second row of the picker
        self.step = 2

        # Disable all row 0 buttons, enable row 1
        for item in self.children:
            if hasattr(item, 'row'):
                if item.row == 0:
                    item.disabled = True
                elif item.row == 1:
                    item.disabled = False
        await interaction.response.edit_message(content=f"You selected: {display_name}. Now select from next row.", view=self)

    async def handle_row2(self, interaction, ball_type, display_name):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.bowling.id:
            await interaction.response.send_message(
                "❌ Only bowling team can select bowling options.",
                ephemeral=True
            )
            return
        # Set the selected length or swing
        if ball_type in ["Good Length", "Full Length", "Yorker", "Bouncer", "Wide Yorker"]:
            self.selected_variation = ball_type
            self.display_variation = display_name

        self.step = 3
        current_match.ball = {
            "style": "pace",
            "length": self.selected_length,      # Good Length / Full Length / Back of Length
            "variation": self.selected_variation, # Yorker / Bouncer etc
            "swing": self.selected_swing         # Inswinger / Outswinger (optional)
        }
        # Build display name from short versions
        parts = []
        if self.display_swing:
            parts.append(self.display_swing)
        if self.display_length:
            parts.append(self.display_length)
        if self.display_variation:
            parts.append(self.display_variation)
        display_ball_name = " ".join(parts) if parts else "Fast Ball"
        
        # Hide bowling buttons completely
        bowler_display_name = get_player_display_name(current_match.current_bowler)
        await interaction.response.edit_message(
            content=f"**{bowler_display_name}** bowled {display_ball_name}.",
            view=None
        )
        # Trigger batting options for batting team
        await safe_channel_send(interaction.channel, f"{current_match.batting.mention} get ready to play!", view=ShotView())


# ---------------- ACCEPT MATCH ---------------- #

class AcceptView(discord.ui.View):

    def __init__(self, challenger, overs):
        super().__init__(timeout=60)  # Increased from 15 to 60 seconds
        self.challenger = challenger
        self.overs = min(overs, 20)

    @discord.ui.button(label="Accept Match", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button):
        try:
            await interaction.response.defer()
            
            # Disable button immediately to prevent multiple clicks
            button.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass  # If edit fails, continue anyway

            if interaction.user == self.challenger:
                await interaction.followup.send(
                    "❌ You cannot accept your own challenge.",
                    ephemeral=True
                )
                return

            # Check accepter's squad requirements
            try:
                roles, squad_players = get_squad_counts(interaction.user.id)
            except Exception as db_error:
                print(f"Error in get_squad_counts: {db_error}")
                await interaction.followup.send(
                    f"❌ Database error checking squad: {str(db_error)}",
                    ephemeral=True
                )
                return

            errors = []
            if not (3 <= roles["bat"] <= 5):
                errors.append(f"You have {roles['bat']} batters. You need 3-5 batters.")
            if not (3 <= roles["bowl"] <= 5):
                errors.append(f"You have {roles['bowl']} bowlers. You need 3-5 bowlers.")
            if not (1 <= roles["alr"] <= 3):
                errors.append(f"You have {roles['alr']} all-rounders. You need 1-3 all-rounders.")
            if not (1 <= roles["wk"] <= 2):
                errors.append(f"You have {roles['wk']} wicketkeepers. You need 1-2 wicketkeepers.")
            if errors:
                embed = discord.Embed(
                    title="Squad Requirements Not Met",
                    description=(
                        "To play a match, your playing XI must meet all of the following requirements:\n"
                        "- 3 to 5 batters\n"
                        "- 3 to 5 bowlers\n"
                        "- 1 to 3 all-rounders\n"
                        "- 1 to 2 wicketkeepers\n\n"
                        "Issues:\n" + "\n".join(errors)
                    ),
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            global current_match
            
            try:
                # Load team1 (challenger's XI)
                cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (self.challenger.id,))
                team1 = [row[0] for row in cursor.fetchall()]
                
                # Load team2 (accepter's XI)
                cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (interaction.user.id,))
                team2 = [row[0] for row in cursor.fetchall()]
            except Exception as query_error:
                print(f"Error loading teams: {query_error}")
                await interaction.followup.send(
                    f"❌ Error loading squads from database: {str(query_error)}",
                    ephemeral=True
                )
                return
            
            if not team1 or not team2:
                await interaction.followup.send(
                    "❌ One or both teams have empty squads. Cannot start match.",
                    ephemeral=True
                )
                return
            
            try:
                current_match = Match(self.challenger, interaction.user, self.overs, team1, team2)
                current_match.toss_allowed_user = interaction.user
                # Generate and assign pitch
                current_match.pitch = generate_pitch()
                print(f"[Pitch] generated {current_match.pitch} for match {self.challenger.id} vs {interaction.user.id}")
            except Exception as match_error:
                print(f"Error creating Match object: {match_error}")
                await interaction.followup.send(
                    f"❌ Error creating match: {str(match_error)}",
                    ephemeral=True
                )
                return

            # Check if match already in progress in this channel
            if interaction.channel.id in current_matches:
                await interaction.followup.send(
                    "❌ A match is already in progress in this channel.",
                    ephemeral=True
                )
                return

            current_matches[interaction.channel.id] = current_match
            add_user_points(self.challenger.id, 10)
            add_user_points(interaction.user.id, 10)

            # Show pitch information first
            embed = discord.Embed(
                title="🏟️ Pitch Report",
                description=f"**Pitch:** {current_match.pitch['name']}",
                color=discord.Color.green()
            )

            if current_match.pitch["type"] == "green":
                embed.add_field(name="Conditions", value="Seamers will dominate early. Expect swing and wickets.")
            elif current_match.pitch["type"] == "dry":
                embed.add_field(name="Conditions", value="Spinners will be dangerous. Batting gets harder later.")
            elif current_match.pitch["type"] == "flat":
                embed.add_field(name="Conditions", value="Batting paradise. High scoring match expected.")

            await interaction.channel.send(embed=embed)
            
            await asyncio.sleep(2)

            await interaction.channel.send(
                f"{self.challenger.mention} vs {interaction.user.mention}\n🏏 Time for the toss!",
                view=TossView(current_match.toss_allowed_user)
            )
        except Exception as e:
            print(f"Error in AcceptView.accept: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    f"❌ Unexpected error: {str(e)[:100]}",
                    ephemeral=True
                )
            except Exception:
                print("Failed to send error message to user")


# ---------------- TOSS ---------------- #

class TossView(discord.ui.View):

    def __init__(self, allowed_user):
        super().__init__(timeout=120)
        self.allowed_user = allowed_user


    @discord.ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads(self, interaction, button):
        await self.handle_toss_choice(interaction, "Heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.primary)
    async def tails(self, interaction, button):
        await self.handle_toss_choice(interaction, "Tails")

    async def handle_toss_choice(self, interaction, choice):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return

        user = interaction.user
        if user.id not in (current_match.p1.id, current_match.p2.id):
            await interaction.response.send_message(
                "❌ Only match players can choose the toss.",
                ephemeral=True
            )
            return
        
        # Check if this user is allowed to call the toss - silently return if not
        if user != self.allowed_user:
            await interaction.response.defer()
            return

        # Disable all buttons after first click
        for item in self.children:
            item.disabled = True
        
        # Immediately defer and edit to show who chose
        await interaction.response.defer()
        await interaction.message.edit(
            content=f"🪙 {user.mention} chose {choice.lower()}",
            view=self
        )
        
        # Real toss logic
        await asyncio.sleep(1)
        toss_result = random.choice(["Heads", "Tails"])
        
        if toss_result == choice:
            winner = user
            loser = current_match.p2 if winner == current_match.p1 else current_match.p1
        else:
            winner = current_match.p2 if user == current_match.p1 else current_match.p1
            loser = user
        
        await interaction.channel.send(
            f"🪙 Toss result: **{toss_result}**\n🏆 {winner.mention} won the toss!",
            view=BatBowlView(winner)
        )


# ---------------- BAT / BOWL CHOICE ---------------- #

class BatBowlView(discord.ui.View):

    def __init__(self, winner):
        super().__init__(timeout=120)
        self.winner = winner


    @discord.ui.button(label="Bat", style=discord.ButtonStyle.green)
    async def bat(self, interaction, button):
        current_match = current_matches[interaction.channel.id]
        if interaction.user != self.winner:
            await interaction.response.send_message(
                "❌ Only toss winner can choose.",
                ephemeral=True
            )
            return
        current_match.batting = self.winner
        current_match.bowling = (
            current_match.p2 if self.winner == current_match.p1 else current_match.p1
        )
        # Disable all buttons after first click
        for item in self.children:
            item.disabled = True
        # Edit the original message to show the choice and disable buttons
        try:
            await interaction.response.edit_message(content=f"{interaction.user.mention} chose to bat.", view=self)
        except Exception:
            await interaction.message.edit(content=f"{interaction.user.mention} chose to bat.", view=self)
        # Use the new async method to handle opener selection
        await OpenerSelect.send_for_batting(interaction.channel)


    @discord.ui.button(label="Bowl", style=discord.ButtonStyle.blurple)
    async def bowl(self, interaction, button):
        current_match = current_matches[interaction.channel.id]
        if interaction.user != self.winner:
            await interaction.response.send_message(
                "❌ Only toss winner can choose.",
                ephemeral=True
            )
            return
        current_match.bowling = self.winner
        current_match.batting = (
            current_match.p2 if self.winner == current_match.p1 else current_match.p1
        )
        # Disable all buttons after first click
        for item in self.children:
            item.disabled = True
        # Edit the original message to show the choice and disable buttons
        try:
            await interaction.response.edit_message(content=f"{interaction.user.mention} chose to field.", view=self)
        except Exception:
            await interaction.message.edit(content=f"{interaction.user.mention} chose to field.", view=self)
        # Use the new async method to handle opener selection
        await OpenerSelect.send_for_batting(interaction.channel)


# ---------------- SELECT XI ---------------- #

class XISelect(discord.ui.View):
    def __init__(self, user_id, squad_players):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.user_id = user_id
        options = []
        for p in canonicalize_player_list(squad_players):
            display_name = get_player_display_name(p)
            ovr = get_current_player_ovr(p)
            label = f"{display_name} ({ovr})" if ovr else display_name
            options.append(discord.SelectOption(label=label, value=p))
        select = discord.ui.Select(
            placeholder="Select 11 players for your XI",
            options=options,
            min_values=11,
            max_values=11
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the team owner can set XI.", ephemeral=True)
            return

        selected_players = interaction.data["values"]
        if len(selected_players) != 11:
            await interaction.response.send_message("❌ You must select exactly 11 players.", ephemeral=True)
            return

        # Clear existing XI
        cursor.execute("DELETE FROM xi WHERE userid=?", (self.user_id,))
        # Insert new XI
        for player in selected_players:
            cursor.execute("INSERT INTO xi (userid, player) VALUES (?, ?)", (self.user_id, player))
        db.commit()

        await interaction.response.send_message("✅ Playing XI set successfully!")


# ---------------- SELECT OPENERS ---------------- #


class OpenerSelect(discord.ui.View):
    def __init__(self, available_players):
        super().__init__(timeout=None)
        options = []
        for p in canonicalize_player_list(available_players):
            display_name = get_player_display_name(p)
            ovr = get_current_player_ovr(p)
            label = f"{display_name} ({ovr})" if ovr else display_name
            options.append(discord.SelectOption(label=label, value=p))
        select = discord.ui.Select(
            placeholder="Select 2 openers",
            options=options,
            min_values=2,
            max_values=2
        )
        select.callback = self.select_callback
        self.add_item(select)

    @staticmethod
    async def send_for_batting(ctx):
        channel = getattr(ctx, "channel", ctx)
        current_match = current_matches.get(channel.id)
        if not current_match:
            await ctx.send("❌ No match in progress.")
            return
        try:
            user_id = current_match.batting.id
            cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
            xi_players = [row[0] for row in cursor.fetchall()]
            if not xi_players:
                await ctx.send("Your XI is empty. Add players to your squad with `ccbuy`.")
                return
            # Normalize and remove duplicate players while preserving order
            xi_players = canonicalize_player_list(xi_players)
            # Filter out already dismissed players
            available = [p for p in xi_players if p not in current_match.dismissed]
            if len(available) < 2:
                await ctx.send("❌ Not enough available players for openers.")
                return
            view = OpenerSelect(available)
            await ctx.send(f"{current_match.batting.mention} select your 2 openers.", view=view)
        except Exception as e:
            print(f"ERROR: Failed to send opener select: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Error selecting openers: {str(e)[:100]}")

    async def select_callback(self, interaction):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if interaction.user.id != current_match.batting.id:
            await interaction.response.send_message(
                "❌ Only batting team selects openers.",
                ephemeral=True
            )
            return

        values = interaction.data["values"]

        if values[0] == values[1]:
            await interaction.response.send_message(
                "❌ Openers must be different players.",
                ephemeral=True
            )
            return

        current_match.striker = values[0]
        current_match.non_striker = values[1]
        current_match.batters = [values[0], values[1]]

        # Initialize batting stats for openers
        current_match.batting_stats[current_match.striker] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0}
        current_match.batting_stats[current_match.non_striker] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0}

        # Edit original message to show openers with display names
        await interaction.response.defer()
        opener1_display = get_player_display_name(values[0])
        opener2_display = get_player_display_name(values[1])
        await interaction.message.edit(
            content=f"🏏 Here we go! **{opener1_display}** and **{opener2_display}** stride out to the middle—two explosive openers ready to set the tone!",
            view=None
        )

        await interaction.channel.send(
            f"{current_match.bowling.mention} select your bowler.",
            view=BowlerSelect(interaction.channel)
        )


# ---------------- SELECT NEXT BATTER (after dismissal) ---------------- #

class NextBatterSelect(discord.ui.View):
    def __init__(self, available_players):
        super().__init__(timeout=None)
        options = []
        for p in canonicalize_player_list(available_players):
            display_name = get_player_display_name(p)
            ovr = get_current_player_ovr(p)
            label = f"{display_name} ({ovr})" if ovr else display_name
            options.append(discord.SelectOption(label=label, value=p))
        select = discord.ui.Select(
            placeholder="Select next batter",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if interaction.user.id != current_match.batting.id:
            await interaction.response.send_message(
                "❌ Only batting team selects next batter.",
                ephemeral=True
            )
            return

        next_batter = interaction.data["values"][0]

        if next_batter in current_match.dismissed:
            await interaction.response.send_message(
                "❌ That batter is already dismissed. Choose another.",
                ephemeral=True
            )
            return

        current_match.striker = next_batter
        current_match.batters.append(next_batter)
        current_match.batting_stats[next_batter] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0}

        # Edit original message to show batter comes to crease
        await interaction.response.defer()
        batter_display_name = get_player_display_name(next_batter)
        await interaction.message.edit(
            content=f"🚶 And here comes the new man, **{batter_display_name}**, walking out to the middle after that breakthrough!",
            view=None
        )

        # CHECK IF INNINGS IS OVER (G1 glitch fix: wicket on last ball of innings)
        status = current_match.innings_over()
        if status == "FIRST_DONE":
            try:
                target = current_match.runs + 1
                # Send innings summary before resetting stats
                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(1)
                current_match.start_second_innings()

                await interaction.channel.send(
                    content=f"🏁 First innings finished!\nTarget: **{target}**",
                    embed=score_embed(current_match)
                )

                await OpenerSelect.send_for_batting(interaction.channel)
            except Exception as e:
                print(f"ERROR: Failed to transition to second innings: {e}")
                import traceback
                traceback.print_exc()
                await interaction.channel.send(f"❌ Error during second innings setup: {str(e)[:100]}")
            return

        if status == "MATCH_DONE":
            # Send live scorecard for the last ball before match finished
            await interaction.channel.send(embed=score_embed(current_match))
            
            # Determine winner or tie  
            if current_match.innings == 2:
                # Tie: both teams get same reward
                if current_match.runs == current_match.target - 1:
                    team1 = current_match.p1
                    team2 = current_match.p2
                    tie_reward, _ = get_match_reward(current_match.max_overs)
                    for user in [team1, team2]:
                        cursor.execute("SELECT balance FROM users WHERE id=?", (user.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + tie_reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, user.id)
                            )
                    db.commit()
                    for user in [team1, team2]:
                        add_user_points(user.id, current_match.max_overs * 2)
                    result_text = f"It's a tie! Both teams receive **{tie_reward:,} CC**."

                    # Send second innings summary
                    await interaction.channel.send(embed=innings_summary_embed(current_match))
                    await asyncio.sleep(2)

                    embed = discord.Embed(
                        title="🏆 MATCH FINISHED - TIE!",
                        description=result_text,
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="🏆 Tie Reward", value=f"💰 Both teams earned **{tie_reward:,} CC**!", inline=False)
                    await interaction.channel.send(embed=embed)
                    del current_matches[interaction.channel.id]
                    return

                if current_match.runs >= current_match.target:
                    winner = current_match.batting
                    loser = current_match.bowling
                    wickets_left = 10 - current_match.wickets
                    result_text = f"{winner.mention} won by **{wickets_left} wickets**!"
                else:
                    winner = current_match.bowling
                    loser = current_match.batting
                    runs_diff = current_match.target - current_match.runs - 1
                    result_text = f"{winner.mention} won by **{runs_diff} runs**!"

                winner_reward, loser_reward = get_match_reward(current_match.max_overs)
                
                # Update winner balance
                cursor.execute("SELECT balance FROM users WHERE id=?", (winner.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + winner_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, winner.id)
                    )
                
                # Update loser balance
                cursor.execute("SELECT balance FROM users WHERE id=?", (loser.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + loser_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, loser.id)
                    )
                    db.commit()

                add_user_points(winner.id, 50 + current_match.max_overs * 2)
                add_user_points(loser.id, 5 + current_match.max_overs * 2)

                # Calculate Player of the Match
                all_players = set(current_match.batting_stats.keys()) | set(current_match.bowling_stats.keys())
                potm = None
                max_score = -1
                for player in all_players:
                    runs = current_match.batting_stats.get(player, {}).get('runs', 0)
                    wickets = current_match.bowling_stats.get(player, {}).get('wickets', 0)
                    score = runs + (wickets * 20)
                    if score > max_score:
                        max_score = score
                        potm = player

                potm_runs = current_match.batting_stats.get(potm, {}).get('runs', 0) if potm else 0
                potm_wickets = current_match.bowling_stats.get(potm, {}).get('wickets', 0) if potm else 0
                potm_display = get_player_display_name(potm)
                potm_text = f"⭐ Player of the Match: {potm_display} ({potm_runs} & {potm_wickets} wickets)" if potm else ""

                # Update player stats for second innings
                update_innings_stats(current_match.batting_stats, current_match.bowling_stats, current_match.striker, current_match.non_striker, current_match.team1, current_match.team2)
                db.commit()

                # Send second innings summary
                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(2)

                # Create match over embed
                embed = discord.Embed(
                    title="🏆 MATCH FINISHED",
                    description=result_text,
                    color=discord.Color.gold()
                )
                embed.add_field(name="Player of the Match", value=potm_text, inline=False)
                embed.add_field(name="🏆 Winner Reward", value=f"💰 {winner.mention} earned **{winner_reward:,} CC**!", inline=False)
                embed.add_field(name="🥈 Loser Reward", value=f"💰 {loser.mention} earned **{loser_reward:,} CC**!", inline=False)
                embed.add_field(name="Points Gifted", value=f"🏅 {winner.mention} +{50 + current_match.max_overs * 2} pts\n🥉 {loser.mention} +{5 + current_match.max_overs * 2} pts", inline=False)

                await interaction.channel.send(embed=embed)
                del current_matches[interaction.channel.id]
                return

        # CHECK IF OVER IS ENDED (G1 glitch fix: wicket on last ball of over)
        if current_match.over_end():
            # Increment bowler overs
            current_match.bowler_overs[current_match.current_bowler] = current_match.bowler_overs.get(current_match.current_bowler, 0) + 1
            current_match.previous_bowler = current_match.current_bowler
            
            # Send scorecard at end of over
            await interaction.channel.send(embed=score_embed(current_match))
            
            # Tag batting team for first ball of new over
            await interaction.channel.send(
                f"{current_match.batting.mention} get ready! First ball of the over.",
            )
            
            await interaction.channel.send(
                f"🔄 Over finished. {current_match.bowling.mention} select new bowler.",
                view=BowlerSelect(interaction.channel)
            )
            return

        # Show bowling options for next ball
        bowler_name = current_match.current_bowler
        bowler_obj = get_player_by_name(bowler_name)
        bowler_type = bowler_obj.get("type", "")
        
        # Determine which bowling view to show
        if bowler_type in ("fast", "fast_med"):
            view = PaceBowlingView()
        elif bowler_type == "off":
            view = OffSpinView()
        elif bowler_type == "leg":
            view = LegSpinView()
        else:
            view = PaceBowlingView()  # fallback
        
        await interaction.channel.send(
            f"{current_match.bowling.mention} select your bowling for next ball.",
            view=view
        )


# ---------------- SELECT BOWLER ---------------- #

class BowlerSelect(discord.ui.View):

    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

        current_match = current_matches.get(self.channel.id)
        if not current_match:
            return  # or raise error

        # Determine bowler quota based on match overs
        overs = current_match.max_overs
        if overs <= 5:
            max_quota = 1
        elif overs <= 10:
            max_quota = 2
        elif overs <= 15:
            max_quota = 3
        else:
            max_quota = 4

        user_id = current_match.bowling.id
        cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
        xi_players = canonicalize_player_list([row[0] for row in cursor.fetchall()])

        # Get bowler overs from match state
        bowler_overs = getattr(current_match, 'bowler_overs', {})
        previous_bowler = getattr(current_match, 'previous_bowler', None)

        available = []
        options = []
        seen = set()
        for p in xi_players:
            if p in current_match.dismissed:
                continue  # skip dismissed (shouldn't happen for bowlers, but safe)
            # Skip players with role "Batter" or "Wicketkeeper"
            role = get_player_role(p).lower()
            if role in ("batter", "wicketkeeper"):
                continue
            # Skip the bowler who just bowled
            if p == previous_bowler:
                continue
            bowled = bowler_overs.get(p, 0)
            quota_left = max_quota - bowled
            if quota_left > 0 and p not in seen:
                seen.add(p)
                display_name = get_player_display_name(p)
                ovr = get_current_player_ovr(p)
                if ovr:
                    label = f"{display_name} ({ovr}) ({quota_left} over{'s' if quota_left > 1 else ''} left)"
                else:
                    label = f"{display_name} ({quota_left} over{'s' if quota_left > 1 else ''} left)"
                available.append(p)
                options.append(discord.SelectOption(label=label, value=p))

        select = discord.ui.Select(
            placeholder="Select Bowler",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return

        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.bowling.id:
            await interaction.response.send_message(
                "❌ Only bowling team selects bowler.",
                ephemeral=True
            )
            return

        current_match.current_bowler = interaction.data["values"][0]

        # Initialize bowling stats for bowler if not already present
        if current_match.current_bowler not in current_match.bowling_stats:
            current_match.bowling_stats[current_match.current_bowler] = {"balls": 0, "runs": 0, "wickets": 0, "maidens": 0, "dots": 0}

        # Edit original message to show bowler came to bowl with display name
        await interaction.response.defer()
        bowler_display_name = get_player_display_name(current_match.current_bowler)
        
        # Random bowler introduction messages (25% probability each)
        bowler_messages = [
            f"Here we go—**{bowler_display_name}** starts his run-up.",
            f"All set now, **{bowler_display_name}** prepares to deliver.",
            f"In comes **{bowler_display_name}**, over the wicket…",
            f"Here he comes—**{bowler_display_name}** charging in!"
        ]
        
        await interaction.message.edit(
            content=random.choice(bowler_messages),
            view=None
        )

        # After new bowler is selected, show bowling team the bowling options
        bowler_name = current_match.current_bowler
        bowler_obj = get_player_by_name(bowler_name)
        bowler_type = bowler_obj.get("type", "")
        
        # Determine which bowling view to show
        if bowler_type in ("fast", "fast_med"):
            view = PaceBowlingView()
        elif bowler_type == "off":
            view = OffSpinView()
        elif bowler_type == "leg":
            view = LegSpinView()
        else:
            view = PaceBowlingView()  # fallback
        
        await interaction.channel.send(
            f"{current_match.bowling.mention} select your bowling for the first ball.",
            view=view
        )


# ---------------- SHOT BUTTONS ---------------- #

class ShotView(SafeResponseView):

    def __init__(self):
        super().__init__(timeout=None)

    async def _safe_response_send(self, interaction, *args, **kwargs):
        try:
            await interaction.response.send_message(*args, **kwargs)
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"ShotView response send error: {e}")

    async def _safe_response_edit(self, interaction, *args, **kwargs):
        try:
            await interaction.response.edit_message(*args, **kwargs)
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"ShotView response edit error: {e}")

    @discord.ui.button(label="Drive", style=discord.ButtonStyle.primary)
    async def drive(self, interaction, button):
        await self.play(interaction, "Drive")

    @discord.ui.button(label="Pull", style=discord.ButtonStyle.primary)
    async def pull(self, interaction, button):
        await self.play(interaction, "Pull")

    @discord.ui.button(label="Cut", style=discord.ButtonStyle.primary)
    async def cut(self, interaction, button):
        await self.play(interaction, "Cut")

    @discord.ui.button(label="Loft", style=discord.ButtonStyle.primary)
    async def loft(self, interaction, button):
        await self.play(interaction, "Loft")

    @discord.ui.button(label="Defend", style=discord.ButtonStyle.secondary)
    async def defend(self, interaction, button):
        await self.play(interaction, "Defend")

    async def play(self, interaction, shot):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await self._safe_response_send(interaction, "❌ No match in progress.", ephemeral=True)
            return

        if not is_match_player(interaction.user, interaction.channel):
            await self._safe_response_send(
                interaction,
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return

        # Prevent button spam from stale shot messages
        # (removed disabling to avoid confusion)
        # for item in self.children:
        #     item.disabled = True
        # try:
        #     await interaction.message.edit(view=self)
        # except Exception:
        #     pass

        if interaction.user.id != current_match.batting.id:
            await self._safe_response_send(
                interaction,
                "❌ Only batting player plays shot.",
                ephemeral=True
            )
            return

        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception as e:
                print(f"ShotView defer error: {e}")
                try:
                    await interaction.response.send_message(
                        "⏳ Processing shot...",
                        ephemeral=True
                    )
                except Exception as send_err:
                    print(f"ShotView fallback response error: {send_err}")

        status = current_match.innings_over()

        if status == "FIRST_DONE":
            try:
                target = current_match.runs + 1
                current_match.start_second_innings()

                await interaction.message.edit(
                    content=f"🏁 First innings finished!\nTarget: **{target}**",
                    embed=None,
                    view=None
                )

                await send_gif(interaction.channel, get_gif("innings_end"))

                # Update player stats for first innings
                update_innings_stats(current_match.first_innings_batting, current_match.first_innings_bowling, current_match.first_innings_striker, current_match.first_innings_non_striker, current_match.team1, current_match.team2)
                db.commit()

                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(3)
                await OpenerSelect.send_for_batting(interaction.channel)
            except Exception as e:
                print(f"ERROR: Failed to transition to second innings: {e}")
                import traceback
                traceback.print_exc()
                await interaction.channel.send(f"❌ Error during second innings setup: {str(e)[:100]}")

            return

        if status == "MATCH_DONE":
            # Send live scorecard for the final ball before match finished
            await interaction.channel.send(embed=score_embed(current_match))
            
            # Determine winner or tie
            if current_match.innings == 2:
                # Tie: both teams get same reward
                if current_match.runs == current_match.target - 1:
                    team1 = current_match.p1
                    team2 = current_match.p2
                    reward = 10000
                    for user in [team1, team2]:
                        cursor.execute("SELECT balance FROM users WHERE id=?", (user.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, user.id)
                            )
                    db.commit()
                    for user in [team1, team2]:
                        add_user_points(user.id, current_match.max_overs * 2)
                    result_text = f"It's a tie! Both teams receive **{reward} CC**."

                    # Accumulate second innings totals
                    for p, stats in current_match.batting_stats.items():
                        current_match.total_batting_stats[p] = current_match.total_batting_stats.get(p, 0) + stats.get('runs', 0)

                    for p, stats in current_match.bowling_stats.items():
                        current_match.total_bowling_stats[p] = current_match.total_bowling_stats.get(p, 0) + stats.get('wickets', 0)

                    # Calculate Player of the Match
                    all_players = set(current_match.total_batting_stats.keys()) | set(current_match.total_bowling_stats.keys())
                    potm = None
                    max_score = -1
                    for player in all_players:
                        runs = current_match.total_batting_stats.get(player, 0)
                        wickets = current_match.total_bowling_stats.get(player, 0)
                        score = runs + (wickets * 20)
                        if score > max_score:
                            max_score = score
                            potm = player

                    potm_runs = current_match.total_batting_stats.get(potm, 0) if potm else 0
                    potm_wickets = current_match.total_bowling_stats.get(potm, 0) if potm else 0
                    potm_display = get_player_display_name(potm)
                    potm_text = f"⭐ Player of the Match: {potm_display} ({potm_runs} & {potm_wickets} wickets)" if potm else ""

                    # Update player stats for second innings
                    update_innings_stats(current_match.batting_stats, current_match.bowling_stats, current_match.striker, current_match.non_striker, current_match.team1, current_match.team2)
                    db.commit()

                    embed = discord.Embed(
                        title="🏆 MATCH FINISHED - TIE!",
                        description=result_text,
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Player of the Match", value=potm_text, inline=False)
                    embed.add_field(name="🏆 Tie Reward", value=f"💰 Both teams earned **{reward} CC**!", inline=False)

                    await interaction.channel.send(embed=embed)
                    await self._safe_response_edit(interaction, view=None)
                    del current_matches[interaction.channel.id]
                    return

                # Win/Loss
                if current_match.runs >= current_match.target:
                    winner = current_match.batting
                    loser = current_match.bowling
                    wickets_left = 10 - current_match.wickets
                    result_text = f"{winner.mention} won by **{wickets_left} wickets**!"
                else:
                    winner = current_match.bowling
                    loser = current_match.batting
                    runs_diff = current_match.target - current_match.runs - 1
                    result_text = f"{winner.mention} won by **{runs_diff} runs**!"

                winner_reward, loser_reward = get_match_reward(current_match.max_overs)

                # Winner
                cursor.execute("SELECT balance FROM users WHERE id=?", (winner.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + winner_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, winner.id)
                    )

                # Loser
                cursor.execute("SELECT balance FROM users WHERE id=?", (loser.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + loser_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, loser.id)
                    )

                db.commit()

                add_user_points(winner.id, 50 + current_match.max_overs * 2)
                add_user_points(loser.id, 5 + current_match.max_overs * 2)

                # Accumulate second innings totals
                for p, stats in current_match.batting_stats.items():
                    current_match.total_batting_stats[p] = current_match.total_batting_stats.get(p, 0) + stats.get('runs', 0)

                for p, stats in current_match.bowling_stats.items():
                    current_match.total_bowling_stats[p] = current_match.total_bowling_stats.get(p, 0) + stats.get('wickets', 0)

                # Calculate Player of the Match
                all_players = set(current_match.total_batting_stats.keys()) | set(current_match.total_bowling_stats.keys())
                potm = None
                max_score = -1
                for player in all_players:
                    runs = current_match.total_batting_stats.get(player, 0)
                    wickets = current_match.total_bowling_stats.get(player, 0)
                    score = runs + (wickets * 20)
                    if score > max_score:
                        max_score = score
                        potm = player

                potm_runs = current_match.total_batting_stats.get(potm, 0) if potm else 0
                potm_wickets = current_match.total_bowling_stats.get(potm, 0) if potm else 0
                potm_display = get_player_display_name(potm)
                potm_text = f"⭐ Player of the Match: {potm_display} ({potm_runs} & {potm_wickets} wickets)" if potm else ""

                # Update player stats for second innings
                update_innings_stats(current_match.batting_stats, current_match.bowling_stats, current_match.striker, current_match.non_striker, current_match.team1, current_match.team2)
                db.commit()

                # Create match over embed
                embed = discord.Embed(
                    title="🏆 MATCH FINISHED",
                    description=result_text,
                    color=discord.Color.gold()
                )
                embed.add_field(name="Player of the Match", value=potm_text, inline=False)
                embed.add_field(name="🏆 Winner Reward", value=f"💰 {winner.mention} earned **{winner_reward:,} CC**!", inline=False)
                embed.add_field(name="🥈 Loser Reward", value=f"💰 {loser.mention} earned **{loser_reward:,} CC**!", inline=False)
                embed.add_field(name="Points Gifted", value=f"🏅 {winner.mention} +{50 + current_match.max_overs * 2} pts\n🥉 {loser.mention} +{5 + current_match.max_overs * 2} pts", inline=False)

                await interaction.channel.send(
                    embed=discord.Embed(
                        title="🏆 MATCH OVER!",
                        description=f"🎉 {winner.mention} wins!\n🔥 What a game!",
                        color=discord.Color.green()
                    )
                )

                await interaction.channel.send(embed=embed)
                await self._safe_response_edit(interaction, view=None)
                del current_matches[interaction.channel.id]
                return

        ball = current_match.ball

        # 1. BOWLING EVENT TEXT - only at start of each over
        if current_match.balls % 6 == 0:
            await interaction.channel.send("🏃 Bowler runs in...")
            await asyncio.sleep(1)

            # 2. BALL GIF (after event)
            if ball["style"] == "pace":
                await send_gif(interaction.channel, get_gif("pace"))
            else:
                await send_gif(interaction.channel, get_gif("spin"))

            await asyncio.sleep(1)

        # 3. GET RESULT FROM ENGINE
        batter_ovr, _ = get_ovr(current_match.striker)
        _, bowler_ovr = get_ovr(current_match.current_bowler)

        ball_display = None
        if ball["style"] == "pace":
            result = play_pace_ball(ball, shot, batter_ovr, bowler_ovr, current_match.pitch, current_match.balls // 6)
            ball_display = ball.get("variation") or ball.get("length") or ball.get("swing") or "pace"
        elif ball["style"] == "offspin":
            result = play_offspin_ball(ball, shot, batter_ovr, bowler_ovr, current_match.pitch, current_match.balls // 6)
            ball_display = ball.get("type") or "offspin"
        elif ball["style"] == "legspin":
            result = play_legspin_ball(ball, shot, batter_ovr, bowler_ovr, current_match.pitch, current_match.balls // 6)
            ball_display = ball.get("type") or "legspin"
        else:
            result = "dot"
            ball_display = ball.get("type") or ball.get("variation") or ball.get("length") or "ball"

        comment = f"{shot} vs {ball_display}"

        # 4. COMMENTARY (FIRST) - Override comment for wickets
        if result == "4":
            commentary = "Cracked through the field! FOUR!"
        elif result == "6":
            commentary = "That’s HUGE! Into the stands for SIX!"
        elif result == "W":
            # Random wicket commentary messages (25% probability each)
            bowler_display_name = get_player_display_name(current_match.current_bowler)
            batter_display_name = get_player_display_name(current_match.striker)
            wicket_messages = [
                f"Gone! **{bowler_display_name}** strikes!",
                f"That's out! **{bowler_display_name}** gets the breakthrough",
                f"WICKET! **{bowler_display_name}** delivers",
                f"Huge wicket! **{batter_display_name}** gone!! **{bowler_display_name}** removes him"
            ]
            comment = random.choice(wicket_messages)  # Override the shot vs ball comment
            commentary = "OUT! What a delivery!"  # Keep original commentary for other logic
        elif result == "dot":
            commentary = "Dot ball. Tight bowling."
        else:
            commentary = f"{result} run(s) taken."

        # Will send proper embed after runs conversion
        gif_type = None
        if result == "4":
            gif_type = "four"
        elif result == "6":
            gif_type = "six"
        elif result == "W":
            gif_type = random.choice(["bowled", "caught", "stumped"])

        scorecard_sent_by_gif = False

        # Build the shot message with commentary
        single_commentary = [
            "a quick single taken comfortably",
            "nudges it for an easy single",
            "rotates the strike with a single"
        ]
        double_commentary = [
            "comes back for a well-judged double",
            "good running between the wickets for two",
            "turns it into a comfortable double"
        ]

        base_message = f"**{get_player_display_name(current_match.striker)}** plays {shot}"
        if result == "4":
            shot_commentary = random.choice(FOUR_RUN_COMMENTARY).format(player=get_player_display_name(current_match.striker))
            shot_msg = f"{base_message}\n{shot_commentary}"
        elif result == "6":
            shot_commentary = random.choice(SIX_RUN_COMMENTARY).format(player=get_player_display_name(current_match.striker))
            shot_msg = f"{base_message}\n{shot_commentary}"
        elif result == "W":
            shot_msg = f"{base_message}\n{comment}"
        elif result == "1":
            shot_msg = f"{base_message}, {random.choice(single_commentary)}"
        elif result == "2":
            shot_msg = f"{base_message}, {random.choice(double_commentary)}"
        else:
            shot_msg = f"{base_message}\n{commentary}"

        await interaction.message.edit(
            content=shot_msg,
            view=None
        )

        if not hasattr(current_match, "timeline"):
            current_match.timeline = []

        # Convert result to runs and check for wicket
        if result == "dot":
            runs = 0
            is_wicket = False
        elif result == "W":
            runs = 0
            is_wicket = True
        elif result.isdigit():
            runs = int(result)
            is_wicket = False
        else:
            runs = 0
            is_wicket = False

        # Dramatic messages
        if runs == 6:
            dramatic_text = "💥 BOOM! SIX!"
        elif runs == 4:
            dramatic_text = "🔥 CRACK! FOUR!"
        elif runs == 0 and not is_wicket:
            dramatic_text = "🧱 Solid defense"
        elif is_wicket:
            dramatic_text = "💀 GONE!"
        else:
            dramatic_text = f"🏃 {runs} runs"

        # Update aggregate totals only; base delivery stats are handled by record_delivery()
        if not is_wicket:
            current_match.total_batting_stats[current_match.striker] = current_match.total_batting_stats.get(current_match.striker, 0) + runs
        if is_wicket:
            current_match.total_bowling_stats[current_match.current_bowler] = current_match.total_bowling_stats.get(current_match.current_bowler, 0) + 1

        # Record every delivery once, including wickets.
        current_match.record_delivery(runs, is_wicket=is_wicket)

        # Send GIFs only after the ball is recorded.
        if gif_type:
            gif_url = get_gif(gif_type)
            if gif_url:
                await send_gif(interaction.channel, gif_url)
            if gif_type not in ["four", "six"]:  # For wickets, send out_signal too
                await asyncio.sleep(1)
                out_signal_gif = get_gif("out_signal")
                if out_signal_gif:
                    await send_gif(interaction.channel, out_signal_gif)

        if result == "W":

            current_match.dismissed.add(current_match.striker)

            # Update player stats for out
            cursor.execute("INSERT OR IGNORE INTO player_stats (player) VALUES (?)", (current_match.striker,))
            cursor.execute("UPDATE player_stats SET bat_outs = bat_outs + 1 WHERE player = ?", (current_match.striker,))
            db.commit()

            status = current_match.innings_over()
            if status == "FIRST_DONE":
                try:
                    target = current_match.runs + 1
                    current_match.start_second_innings()

                    await interaction.channel.send(
                        content=f"🏁 First innings finished!\nTarget: **{target}**",
                        embed=score_embed(current_match)
                    )
                    await send_gif(interaction.channel, get_gif("innings_end"))

                    # Update player stats for first innings
                    update_innings_stats(
                        current_match.first_innings_batting,
                        current_match.first_innings_bowling,
                        current_match.first_innings_striker,
                        current_match.first_innings_non_striker,
                        current_match.team1,
                        current_match.team2
                    )
                    db.commit()

                    await interaction.channel.send(embed=innings_summary_embed(current_match))
                    await asyncio.sleep(3)
                    await OpenerSelect.send_for_batting(interaction.channel)
                except Exception as e:
                    print(f"ERROR: Failed to transition to second innings: {e}")
                    import traceback
                    traceback.print_exc()
                    await interaction.channel.send(f"❌ Error during second innings setup: {str(e)[:100]}")
                return

            if status == "MATCH_DONE":
                # Send live scorecard for the final wicket ball before match finished
                await interaction.channel.send(embed=score_embed(current_match))
                
                # Determine winner or tie
                if current_match.innings == 2 and current_match.runs == current_match.target - 1:
                    tie_reward, _ = get_match_reward(current_match.max_overs)
                    for user in [current_match.p1, current_match.p2]:
                        cursor.execute("SELECT balance FROM users WHERE id=?", (user.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + tie_reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, user.id)
                            )
                    db.commit()
                    for user in [current_match.p1, current_match.p2]:
                        add_user_points(user.id, current_match.max_overs * 2)

                    await interaction.channel.send(embed=innings_summary_embed(current_match))
                    await asyncio.sleep(2)
                    await send_scorecard_image(interaction.channel, current_match)

                    embed = discord.Embed(
                        title="🏆 MATCH FINISHED - TIE!",
                        description=f"It's a tie! Both teams receive **{tie_reward:,} CC**.",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="🏆 Tie Reward", value=f"💰 Both teams earned **{tie_reward:,} CC**!", inline=False)

                    await interaction.channel.send(embed=embed)
                    await self._safe_response_edit(interaction, view=None)
                    del current_matches[interaction.channel.id]
                    return

                if current_match.innings == 2:
                    if current_match.runs >= current_match.target:
                        winner = current_match.batting
                        loser = current_match.bowling
                        wickets_left = 10 - current_match.wickets
                        result_text = f"{winner.mention} won by **{wickets_left} wickets**!"
                    else:
                        winner = current_match.bowling
                        loser = current_match.batting
                        runs_diff = current_match.target - current_match.runs - 1
                        result_text = f"{winner.mention} won by **{runs_diff} runs**!"
                else:
                    # Should not happen, but fallback
                    winner = current_match.bowling
                    loser = current_match.batting
                    result_text = f"{winner.mention} won by default!"

                winner_reward, loser_reward = get_match_reward(current_match.max_overs)
                
                # Update winner balance
                cursor.execute("SELECT balance FROM users WHERE id=?", (winner.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + winner_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, winner.id)
                    )
                
                # Update loser balance
                cursor.execute("SELECT balance FROM users WHERE id=?", (loser.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + loser_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, loser.id)
                    )
                    db.commit()

                add_user_points(winner.id, 50 + current_match.max_overs * 2)
                add_user_points(loser.id, 5 + current_match.max_overs * 2)

                # Send second innings summary
                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(2)
                await send_scorecard_image(interaction.channel, current_match)

                # Create match over embed
                embed = discord.Embed(
                    title="🏆 MATCH FINISHED",
                    description=result_text,
                    color=discord.Color.gold()
                )
                embed.add_field(name="🏆 Winner Reward", value=f"💰 {winner.mention} earned **{winner_reward:,} CC**!", inline=False)
                embed.add_field(name="🥈 Loser Reward", value=f"💰 {loser.mention} earned **{loser_reward:,} CC**!", inline=False)
                embed.add_field(name="Points Gifted", value=f"🏅 {winner.mention} +{50 + current_match.max_overs * 2} pts\n🥉 {loser.mention} +{5 + current_match.max_overs * 2} pts", inline=False)

                await interaction.channel.send(embed=embed)
                await self._safe_response_edit(interaction, view=None)
                return

            # Prompt for next batter selection
            user_id = current_match.batting.id
            cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
            xi_players = canonicalize_player_list([row[0] for row in cursor.fetchall()])
            unavailable = set(current_match.dismissed)
            if current_match.non_striker:
                unavailable.add(current_match.non_striker)
            available = [p for p in xi_players if p not in unavailable]
            
            if not available:
                # All out - innings finished
                if current_match.innings == 1:
                    try:
                        # First innings over, start second
                        target = current_match.runs + 1
                        # Send innings summary before resetting stats
                        await interaction.channel.send(embed=innings_summary_embed(current_match))
                        await asyncio.sleep(3)
                        current_match.start_second_innings()
                        await interaction.channel.send(
                            content=f"🏁 **FIRST INNINGS FINISHED!**\nTarget: **{target}**",
                            embed=score_embed(current_match)
                        )
                        await OpenerSelect.send_for_batting(interaction.channel)
                    except Exception as e:
                        print(f"ERROR: Failed to transition to second innings (all out): {e}")
                        import traceback
                        traceback.print_exc()
                        await interaction.channel.send(f"❌ Error during second innings setup: {str(e)[:100]}")
                else:
                    # Second innings all out - match over
                    # Send live scorecard for the last ball before innings summary
                    await interaction.channel.send(embed=score_embed(current_match))
                    
                    await interaction.channel.send(embed=innings_summary_embed(current_match))
                    await asyncio.sleep(2)
                    await send_scorecard_image(interaction.channel, current_match)

                    if current_match.runs == current_match.target - 1:
                        tie_reward, _ = get_match_reward(current_match.max_overs)
                        for user in [current_match.p1, current_match.p2]:
                            cursor.execute("SELECT balance FROM users WHERE id=?", (user.id,))
                            row = cursor.fetchone()
                            if row:
                                new_balance = row[0] + tie_reward
                                cursor.execute(
                                    "UPDATE users SET balance=? WHERE id=?",
                                    (new_balance, user.id)
                                )
                        db.commit()
                        for user in [current_match.p1, current_match.p2]:
                            add_user_points(user.id, current_match.max_overs * 2)

                        embed = discord.Embed(
                            title="🏆 MATCH FINISHED - TIE!",
                            description=f"It's a tie! Both teams receive **{tie_reward:,} CC**.",
                            color=discord.Color.gold()
                        )
                        embed.add_field(name="🏆 Tie Reward", value=f"💰 Both teams earned **{tie_reward:,} CC**!", inline=False)
                        await interaction.channel.send(embed=embed)
                    else:
                        winner = current_match.bowling
                        loser = current_match.batting
                        runs_diff = current_match.target - current_match.runs - 1

                        winner_reward, loser_reward = get_match_reward(current_match.max_overs)

                        cursor.execute("SELECT balance FROM users WHERE id=?", (winner.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + winner_reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, winner.id)
                            )

                        cursor.execute("SELECT balance FROM users WHERE id=?", (loser.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + loser_reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, loser.id)
                            )

                        db.commit()

                        embed = discord.Embed(
                            title="🏆 MATCH FINISHED",
                            description=f"{winner.mention} won by **{runs_diff} runs**!",
                            color=discord.Color.gold()
                        )
                        embed.add_field(name="🏆 Winner Reward", value=f"💰 {winner.mention} earned **{winner_reward:,} CC**!", inline=False)
                        embed.add_field(name="🥈 Loser Reward", value=f"💰 {loser.mention} earned **{loser_reward:,} CC**!", inline=False)
                        await interaction.channel.send(embed=embed)

                    del current_matches[interaction.channel.id]
                return
            
            await interaction.channel.send(embed=score_embed(current_match))

            await interaction.channel.send(
                f"{current_match.batting.mention} select your next batter.",
                view=NextBatterSelect(available)
            )

            return

        if not scorecard_sent_by_gif:
            try:
                await interaction.channel.send(embed=score_embed(current_match))
            except Exception as e:
                print(f"ERROR sending scorecard: {e}")

        # Check if innings or match is done after adding runs
        status = current_match.innings_over()
        if status == "FIRST_DONE":
            try:
                target = current_match.runs + 1
                # Send innings summary before resetting stats
                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(1)
                current_match.start_second_innings()

                await interaction.channel.send(
                    content=f"🏁 First innings finished!\nTarget: **{target}**",
                    embed=score_embed(current_match)
                )

                await OpenerSelect.send_for_batting(interaction.channel)
            except Exception as e:
                print(f"ERROR: Failed to transition to second innings (runs added): {e}")
                import traceback
                traceback.print_exc()
                await interaction.channel.send(f"❌ Error during second innings setup: {str(e)[:100]}")
            return

        if status == "MATCH_DONE":
            # Determine winner or tie  
            if current_match.innings == 2:
                # Tie: both teams get same reward
                if current_match.runs == current_match.target - 1:
                    team1 = current_match.p1
                    team2 = current_match.p2
                    tie_reward, _ = get_match_reward(current_match.max_overs)
                    for user in [team1, team2]:
                        cursor.execute("SELECT balance FROM users WHERE id=?", (user.id,))
                        row = cursor.fetchone()
                        if row:
                            new_balance = row[0] + tie_reward
                            cursor.execute(
                                "UPDATE users SET balance=? WHERE id=?",
                                (new_balance, user.id)
                            )
                    db.commit()
                    for user in [team1, team2]:
                        add_user_points(user.id, current_match.max_overs * 2)
                    result_text = f"It's a tie! Both teams receive **{tie_reward:,} CC**."

                    # Send second innings summary
                    await interaction.channel.send(embed=innings_summary_embed(current_match))
                    await asyncio.sleep(2)
                    await send_scorecard_image(interaction.channel, current_match)

                    # Calculate Player of the Match
                    all_players = set(current_match.total_batting_stats.keys()) | set(current_match.total_bowling_stats.keys())
                    potm = None
                    max_score = -1
                    for player in all_players:
                        runs_player = current_match.total_batting_stats.get(player, 0)
                        wickets = current_match.total_bowling_stats.get(player, 0)
                        score = runs_player + (wickets * 20)
                        if score > max_score:
                            max_score = score
                            potm = player

                    potm_runs = current_match.total_batting_stats.get(potm, 0) if potm else 0
                    potm_wickets = current_match.total_bowling_stats.get(potm, 0) if potm else 0
                    potm_text = f"⭐ Player of the Match: {potm} ({potm_runs} & {potm_wickets} wickets)" if potm else ""

                    # Update player stats for second innings
                    update_innings_stats(current_match.batting_stats, current_match.bowling_stats, current_match.striker, current_match.non_striker, current_match.team1, current_match.team2)
                    db.commit()

                    # Create tie embed
                    embed = discord.Embed(
                        title="🏆 MATCH FINISHED - TIE!",
                        description=result_text,
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Player of the Match", value=potm_text, inline=False)
                    embed.add_field(name="🏆 Tie Reward", value=f"💰 Both teams earned **{tie_reward:,} CC**!", inline=False)

                    await interaction.channel.send(embed=embed)
                    del current_matches[interaction.channel.id]
                    return

                # Win/Loss
                if current_match.runs >= current_match.target:
                    winner = current_match.batting
                    loser = current_match.bowling
                    wickets_left = 10 - current_match.wickets
                    result_text = f"{winner.mention} won by **{wickets_left} wickets**!"
                else:
                    winner = current_match.bowling
                    loser = current_match.batting
                    runs_diff = current_match.target - current_match.runs - 1
                    result_text = f"{winner.mention} won by **{runs_diff} runs**!"

                winner_reward, loser_reward = get_match_reward(current_match.max_overs)

                # Winner
                cursor.execute("SELECT balance FROM users WHERE id=?", (winner.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + winner_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, winner.id)
                    )

                # Loser
                cursor.execute("SELECT balance FROM users WHERE id=?", (loser.id,))
                row = cursor.fetchone()
                if row:
                    new_balance = row[0] + loser_reward
                    cursor.execute(
                        "UPDATE users SET balance=? WHERE id=?",
                        (new_balance, loser.id)
                    )

                db.commit()

                # Send second innings summary
                await interaction.channel.send(embed=innings_summary_embed(current_match))
                await asyncio.sleep(2)
                await send_scorecard_image(interaction.channel, current_match)

                # Calculate Player of the Match
                all_players = set(current_match.total_batting_stats.keys()) | set(current_match.total_bowling_stats.keys())
                potm = None
                max_score = -1
                for player in all_players:
                    runs_player = current_match.total_batting_stats.get(player, 0)
                    wickets = current_match.total_bowling_stats.get(player, 0)
                    score = runs_player + (wickets * 20)
                    if score > max_score:
                        max_score = score
                        potm = player

                potm_runs = current_match.total_batting_stats.get(potm, 0) if potm else 0
                potm_wickets = current_match.total_bowling_stats.get(potm, 0) if potm else 0
                potm_text = f"⭐ Player of the Match: {potm} ({potm_runs} & {potm_wickets} wickets)" if potm else ""

                # Update player stats for second innings
                update_innings_stats(current_match.batting_stats, current_match.bowling_stats, current_match.striker, current_match.non_striker, current_match.team1, current_match.team2)
                db.commit()

                # Create match over embed
                embed = discord.Embed(
                    title="🏆 MATCH FINISHED",
                    description=result_text,
                    color=discord.Color.gold()
                )
                embed.add_field(name="Player of the Match", value=potm_text, inline=False)
                embed.add_field(name="🏆 Winner Reward", value=f"💰 {winner.mention} earned **{winner_reward:,} CC**!", inline=False)
                embed.add_field(name="🥈 Loser Reward", value=f"💰 {loser.mention} earned **{loser_reward:,} CC**!", inline=False)
                embed.add_field(name="Points Gifted", value=f"🏅 {winner.mention} +{50 + current_match.max_overs * 2} pts\n🥉 {loser.mention} +{5 + current_match.max_overs * 2} pts", inline=False)

                await interaction.channel.send(embed=embed)
                await interaction.channel.send(
                    embed=discord.Embed(
                        title="🏆 MATCH OVER!",
                        description=f"{result_text}\n🎉 {winner.mention} wins!",
                        color=discord.Color.green()
                    )
                )
                del current_matches[interaction.channel.id]
                return

        if current_match.over_end():
            # Increment bowler overs
            current_match.bowler_overs[current_match.current_bowler] = current_match.bowler_overs.get(current_match.current_bowler, 0) + 1
            current_match.previous_bowler = current_match.current_bowler
            
            # Tag batting team for first ball of new over
            await interaction.channel.send(
                f"{current_match.batting.mention} get ready! First ball of the over.",
            )
            
            await interaction.channel.send(
                f"🔄 Over finished. {current_match.bowling.mention} select new bowler.",
                view=BowlerSelect(interaction.channel)
            )
            return

        # Show bowling options for next ball
        bowler_name = current_match.current_bowler
        bowler_obj = get_player_by_name(bowler_name)
        bowler_type = bowler_obj.get("type", "")
        if bowler_type in ("fast", "fast_med"):
            view = PaceBowlingView()
        elif bowler_type == "off":
            view = OffSpinView()
        elif bowler_type == "leg":
            view = LegSpinView()
        else:
            view = PaceBowlingView()  # fallback
        await interaction.channel.send(f"{current_match.bowling.mention} select bowling options for next ball.", view=view)


# ---------------- NEW BATTER ---------------- #

class NewBatterSelect(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        # Only show players from the batting user's XI who are not dismissed or already batting
        user_id = current_match.batting.id
        cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
        xi_players = canonicalize_player_list([row[0] for row in cursor.fetchall()])
        unavailable = set(current_match.dismissed)
        if current_match.striker:
            unavailable.add(current_match.striker)
        if current_match.non_striker:
            unavailable.add(current_match.non_striker)
        available = [p for p in xi_players if p not in unavailable]
        
        options = []
        for p in canonicalize_player_list(available):
            display_name = get_player_display_name(p)
            ovr = get_current_player_ovr(p)
            label = f"{display_name} ({ovr})" if ovr else display_name
            options.append(discord.SelectOption(label=label, value=p))

        select = discord.ui.Select(
            placeholder="Select new batter",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction):
        current_match = current_matches.get(interaction.channel.id)
        if not current_match:
            await interaction.response.send_message("❌ No match in progress.", ephemeral=True)
            return
        if not is_match_player(interaction.user, interaction.channel):
            await interaction.response.send_message(
                "❌ You are not part of this match.",
                ephemeral=True
            )
            return
        if interaction.user.id != current_match.batting.id:
            await interaction.response.send_message(
                "❌ Only batting team selects batter.",
                ephemeral=True
            )
            return

        new_batter = interaction.data["values"][0]
        current_match.striker = new_batter
        current_match.batters.append(new_batter)
        
        new_batter_display = get_player_display_name(new_batter)

        await interaction.response.send_message(
            f"✅ New batter: **{new_batter_display}**\n\n{current_match.bowling.mention} select your bowling!",
            view=BowlerSelect(interaction.channel)
        )


def _select_player_by_ovr_range(min_ovr, max_ovr, exclude_names=None):
    exclude_names = {name.lower() for name in (exclude_names or [])}
    pool = [p for p in players.values()
            if isinstance(p.get("ovr"), (int, float))
            and min_ovr <= int(p.get("ovr")) <= max_ovr
            and p.get("name", "").lower() not in exclude_names]
    if pool:
        return random.choice(pool)
    # fallback to allow duplicates if no unique player exists
    pool = [p for p in players.values()
            if isinstance(p.get("ovr"), (int, float))
            and min_ovr <= int(p.get("ovr")) <= max_ovr]
    return random.choice(pool) if pool else None


def generate_monthly_pack_contents(pack_type, user_id):
    cursor.execute("SELECT player_key FROM squad WHERE userid=?", (user_id,))
    owned = {row[0].lower() for row in cursor.fetchall()}
    selected = []
    exclude = set(owned)

    def pick(min_ovr, max_ovr):
        player = _select_player_by_ovr_range(min_ovr, max_ovr, exclude)
        if player:
            exclude.add(player.get("name", "").lower())
            selected.append(player)

    if pack_type == "top1":
        pick(85, 88)
        pick(80, 83)
        pick(78, 80)
        pick(80, 80)
        pick(75, 75)
    elif pack_type == "top2":
        pick(85, 88)
        pick(80, 80)
        pick(80, 82)
    elif pack_type == "top3":
        pick(85, 87)
        pick(82, 82)
    elif pack_type == "top4_10":
        pick(85, 87)
    else:
        pick(85, 85)

    for player in selected:
        if player:
            cursor.execute(
                "INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)",
                (user_id, get_player_key_from_name(player.get("name", "Unknown")) or player.get("name", "Unknown"), int(player.get("ovr", 0)))
            )
    db.commit()
    return selected


class PackSelectView(discord.ui.View):
    def __init__(self, user_id, monthly_packs, inventory_packs=None):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.monthly_packs = monthly_packs or []
        self.inventory_packs = inventory_packs or []

        options = []
        for pack_id, name, tier in self.monthly_packs:
            options.append(discord.SelectOption(label=f"{name} — {tier}", value=f"monthly:{pack_id}"))
        for inv_id, pack_type, pack_name in self.inventory_packs:
            display_label = f"{pack_name} — {pack_type.replace('_', ' ').title()}"
            options.append(discord.SelectOption(label=display_label, value=f"shop:{inv_id}"))

        select = discord.ui.Select(
            placeholder="Select a pack to open",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pack is not for you.", ephemeral=True)
            return

        selected_value = interaction.data["values"][0]
        if selected_value.startswith("monthly:"):
            pack_id = int(selected_value.split(":", 1)[1])
            cursor.execute(
                "SELECT name, tier FROM monthly_packs WHERE pack_id=? AND userid=? AND status='unopened'",
                (pack_id, self.user_id)
            )
            row = cursor.fetchone()
            if not row:
                await interaction.response.send_message("❌ Pack not found or already opened.", ephemeral=True)
                return

            name, tier = row
            embed = discord.Embed(
                title="Monthly Claim",
                description=(
                    f"You selected **{name}** — **{tier}**.\n"
                    "Click Open to reveal the pack contents, or Cancel to keep the pack unopened."
                ),
                color=discord.Color.gold()
            )
            await safe_interaction_edit(interaction, embed=embed, view=PackActionView(self.user_id, pack_id, name, tier))
            return

        if selected_value.startswith("shop:"):
            inv_id = int(selected_value.split(":", 1)[1])
            cursor.execute(
                "SELECT pack_type, pack_name FROM user_inventory WHERE inv_id=? AND userid=?",
                (inv_id, self.user_id)
            )
            row = cursor.fetchone()
            if not row:
                await interaction.response.send_message("❌ Pack not found or already opened.", ephemeral=True)
                return

            pack_type, pack_name = row
            pack_data = PACKS_DATA.get(pack_type, {
                "name": pack_name,
                "price": 0,
                "banner": None
            })
            embed = discord.Embed(
                title="Shop Pack",
                description=(
                    f"You selected **{pack_name}**.\n"
                    "Click Open Pack 🎁 to reveal the card, or Cancel to keep this pack unopened."
                ),
                color=discord.Color.gold()
            )
            files = None
            banner = pack_data.get("banner")
            if banner:
                if isinstance(banner, str) and banner.startswith(("http://", "https://")):
                    embed.set_image(url=banner)
                else:
                    banner_path = Path(banner)
                    if banner_path.is_dir():
                        image_files = [p for p in banner_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}]
                        if image_files:
                            banner_path = image_files[0]
                    if banner_path.is_file():
                        filename = banner_path.name
                        embed.set_image(url=f"attachment://{filename}")
                        files = [discord.File(banner_path, filename=filename)]

            if files:
                await safe_interaction_edit(interaction, embed=embed, view=OpenPackAnimationView(self.user_id, inv_id, pack_type, pack_name), attachments=files)
            else:
                await safe_interaction_edit(interaction, embed=embed, view=OpenPackAnimationView(self.user_id, inv_id, pack_type, pack_name))
            return

        await interaction.response.send_message("❌ Invalid selection.", ephemeral=True)


class PackActionView(discord.ui.View):
    def __init__(self, user_id, pack_id, name, tier):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.pack_id = pack_id
        self.name = name
        self.tier = tier

    @discord.ui.button(label="Open", style=discord.ButtonStyle.success)
    async def open_pack(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pack is not for you.", ephemeral=True)
            return

        cursor.execute("SELECT status FROM monthly_packs WHERE pack_id=? AND userid=?", (self.pack_id, self.user_id))
        row = cursor.fetchone()
        if not row or row[0] != "unopened":
            await interaction.response.send_message("❌ This pack cannot be opened.", ephemeral=True)
            return

        pack_player_requirements = {
            "Top 1": 5,
            "Top 2": 3,
            "Top 3": 2,
            "Top 4-10": 1,
            "Rest": 1
        }
        required_slots = pack_player_requirements.get(self.tier, 1)
        cursor.execute("SELECT COUNT(*) FROM squad WHERE userid=?", (self.user_id,))
        current_count = cursor.fetchone()[0]
        available_slots = 22 - current_count

        if available_slots < required_slots:
            reason = (
                f"❌ Cannot open this pack because your squad has only {available_slots} free slot{'s' if available_slots != 1 else ''} "
                f"but this pack requires {required_slots}."
            )
            embed = discord.Embed(
                title="Monthly Claim",
                description=reason,
                color=discord.Color.red()
            )
            await safe_interaction_edit(interaction, content=None, embed=embed, view=None)
            return

        cursor.execute("UPDATE monthly_packs SET status='opened' WHERE pack_id=?", (self.pack_id,))
        db.commit()

        await interaction.response.defer()
        await asyncio.sleep(3)

        pack_type = {
            "Top 1": "top1",
            "Top 2": "top2",
            "Top 3": "top3",
            "Top 4-10": "top4_10",
            "Rest": "rest"
        }.get(self.tier, "rest")
        players_received = generate_monthly_pack_contents(pack_type, self.user_id)
        if players_received:
            lines = [f"• {p.get('name', 'Unknown')} ({int(p.get('ovr', 0))})" for p in players_received]
            description = "\n".join(lines)
        else:
            description = "No players could be generated for this pack."

        embed = discord.Embed(
            title="Monthly Claim",
            description=(
                f"📦 Pack opened! You received the following players:\n{description}"
            ),
            color=discord.Color.green()
        )
        embed.add_field(name="Note", value="Coins were already added when you claimed monthly rewards.", inline=False)
        await interaction.message.edit(content=None, embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_pack(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This pack is not for you.", ephemeral=True)
            return

        cursor.execute("UPDATE monthly_packs SET status='cancelled' WHERE pack_id=?", (self.pack_id,))
        db.commit()
        await safe_interaction_edit(interaction, content="❌ Pack cancelled. You can open another pack later with ccpacks.", embed=None, view=None)


class PackShopView(discord.ui.View):
    async def _safe_edit(self, interaction, *, embed, view, attachments=None):
        # Ensure attachments is always a list (never None)
        if attachments is None:
            attachments = []
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=view, attachments=attachments)
            else:
                await interaction.edit_original_response(embed=embed, view=view, attachments=attachments)
        except Exception as e:
            import discord
            if isinstance(e, discord.errors.NotFound):
                # Interaction expired or unknown, ignore gracefully
                pass
            else:
                raise

    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

        options = [
            discord.SelectOption(label=f"{v['name']} ({v['price']:,} CC)", value=k)
            for k, v in PACKS_DATA.items()
        ]

        self.select = discord.ui.Select(placeholder="Choose a pack to buy...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

        # Add Cancel button to dropdown view
        self.cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)
        self.cancel_btn.callback = self.cancel_callback
        self.add_item(self.cancel_btn)

    async def cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your shop!", ephemeral=True)
        await interaction.response.edit_message(content="❌ Pack selection cancelled.", embed=None, view=None)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your shop!", ephemeral=True)

        selected_key = self.select.values[0]
        pack = PACKS_DATA[selected_key]

        embed = discord.Embed(
            title=f"Confirm Purchase: {pack['name']}",
            description=(
                f"Price: **{pack['price']:,} CC**\n"
                "Click Buy to add this to your inventory."
            ),
            color=discord.Color.gold()
        )

        files = None
        banner = pack.get("banner")
        if banner:
            if isinstance(banner, str) and banner.startswith(("http://", "https://")):
                embed.set_image(url=banner)
            else:
                banner_path = Path(banner)
                if banner_path.is_dir():
                    image_files = [p for p in banner_path.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}]
                    if image_files:
                        banner_path = image_files[0]
                if banner_path.is_file():
                    filename = banner_path.name
                    embed.set_image(url=f"attachment://{filename}")
                    files = [discord.File(banner_path, filename=filename)]

        view = PackPurchaseConfirm(self.user_id, selected_key, pack)
        await self._safe_edit(interaction, embed=embed, view=view, attachments=files)


class PackPurchaseConfirm(discord.ui.View):
    def __init__(self, user_id, pack_key, pack_data):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.pack_key = pack_key
        self.data = pack_data

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your shop!", ephemeral=True)

        cursor.execute("SELECT balance FROM users WHERE id=?", (self.user_id,))
        row = cursor.fetchone()
        balance = row[0] if row else 0

        if balance < self.data['price']:
            return await interaction.response.send_message("❌ Insufficient CC!", ephemeral=True)

        cursor.execute("UPDATE users SET balance = balance - ? WHERE id=?", (self.data['price'], self.user_id))
        cursor.execute(
            "INSERT INTO user_inventory (userid, pack_type, pack_name) VALUES (?,?,?)",
            (self.user_id, self.pack_key, self.data['name'])
        )
        db.commit()

        await interaction.response.edit_message(content=f"✅ {interaction.user.mention} purchased a **{self.data['name']}**!", embed=None, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your shop!", ephemeral=True)

        await interaction.response.edit_message(content="❌ Purchase cancelled.", embed=None, view=None)


class OpenPackAnimationView(discord.ui.View):
    def __init__(self, user_id, inv_id, pack_type, pack_name):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.inv_id = inv_id
        self.pack_type = pack_type
        self.pack_name = pack_name
        self.opened = False

    @discord.ui.button(label="Open Pack 🎁", style=discord.ButtonStyle.primary)
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This pack is not for you.", ephemeral=True)

        if self.opened:
            return await interaction.response.send_message("❌ This pack is already opening.", ephemeral=True)

        self.opened = True

        cursor.execute("SELECT COUNT(*) FROM squad WHERE userid=?", (self.user_id,))
        current_count = cursor.fetchone()[0]
        if current_count >= 22:
            await interaction.response.send_message("❌ Your squad is full. Release a player before opening a pack.", ephemeral=True)
            return

        anim_embed = discord.Embed(title="Opening Pack...", color=discord.Color.blue())
        anim_embed.set_image(url="https://your-animation-link.gif")
        await safe_interaction_edit(interaction, embed=anim_embed, view=None)

        await asyncio.sleep(4)

        pack_data = PACKS_DATA.get(self.pack_type, {})
        pack_pool = pack_data.get("pool")

        if pack_pool:
            keys, weights = zip(*pack_pool)
            player_key = random.choices(keys, weights=weights, k=1)[0]
            player_data = players.get(player_key)
            if not player_data:
                player_data = players.get(random.choice(all_player_keys))
                player_key = player_data and get_player_key_from_name(player_data.get("name", "")) or player_key
        else:
            if self.pack_type == "ipl_legends":
                pool = [(k, v) for k, v in all_player_entries if "IPL Legends" in v.get("image", "")]
            elif self.pack_type == "wpl_2026":
                pool = [(k, v) for k, v in all_player_entries if "WPL cards" in v.get("image", "")]
            elif self.pack_type == "t20_wc":
                pool = [(k, v) for k, v in all_player_entries if "World Cup" in v.get("image", "") or "WC" in v.get("image", "")]
            else:
                pool = all_player_entries

            if not pool:
                pool = all_player_entries

            player_key, player_data = random.choice(pool)

        cursor.execute("DELETE FROM user_inventory WHERE inv_id=?", (self.inv_id,))
        cursor.execute(
            "INSERT INTO squad(userid, player_key, ovr, category) VALUES(?,?,?,?)",
            (self.user_id, player_key, player_data.get('ovr', 0), player_data.get('category', 'N'))
        )
        db.commit()

        player_id = all_player_keys.index(player_key) if player_key in all_player_keys else 0
        card_embed, card_file = create_player_embed(player_data, player_id, player_key)
        card_embed.title = f"🎊 You won {player_data.get('name', 'a player')}!"

        try:
            await interaction.message.delete()
        except Exception:
            pass

        try:
            if card_file:
                await interaction.followup.send(embed=card_embed, files=[card_file])
            else:
                await interaction.followup.send(embed=card_embed)
        except Exception:
            try:
                await interaction.followup.send(embed=card_embed)
            except Exception:
                pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ This pack is not for you.", ephemeral=True)

        await safe_interaction_edit(interaction, content="❌ Pack opening cancelled.", embed=None, view=None)


# ---------------- SELL ------------ #
class SellView(discord.ui.View):

    def __init__(self, user_id, player_key, rowids, total_price=None, timeout=30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.player_key = player_key
        self.rowids = rowids

        # If total_price is provided (bulk sale), use it directly
        if total_price is not None:
            self.total_price = total_price
            self.sell_price_each = total_price // len(rowids) if rowids else 0
        else:
            # Single player sale - calculate based on player price
            from players import players, get_price_by_ovr

            player = players.get(player_key)

            if player and player.get("price"):
                buy_price = int(player["price"])
            elif player and player.get("ovr"):
                buy_price = get_price_by_ovr(player["ovr"], player.get("category"))
            else:
                buy_price = 10000

            self.sell_price_each = buy_price // 2
            self.total_price = self.sell_price_each * len(rowids)

        self.cursor = cursor
        self.db = db
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="Sale timed out.", view=self)
            except:
                pass


    @discord.ui.button(label="Sell", style=discord.ButtonStyle.green)
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ You can't sell this player.",
                ephemeral=True
            )
            return

        # delete multiple players
        for rid in self.rowids:
            self.cursor.execute("DELETE FROM squad WHERE rowid=?", (rid,))

        # update balance
        self.cursor.execute(
            "SELECT balance FROM users WHERE id=?", (self.user_id,)
        )
        balance = self.cursor.fetchone()[0]

        new_balance = balance + self.total_price

        self.cursor.execute(
            "UPDATE users SET balance=? WHERE id=?",
            (new_balance, self.user_id)
        )

        self.db.commit()

        await interaction.response.edit_message(content=f"✅ Sold **{len(self.rowids)} {'players' if self.player_key is None else players.get(self.player_key, {}).get('name', self.player_key.replace('_', ' ').title())}** for **{self.total_price} CC**", view=None)

        self.stop()


    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ You can't cancel this.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(content="Sale cancelled.", view=None)

        self.stop()


    async def interaction_check(self, interaction: discord.Interaction) -> bool:

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Not your sell request.",
                ephemeral=True
            )
            return False

        if self.message is None:
            self.message = interaction.message

        return True

def get_squad_counts(user_id):
    cursor.execute("SELECT player_key FROM squad WHERE userid=? ORDER BY rowid LIMIT 11", (user_id,))
    xi_players = [row[0] for row in cursor.fetchall()]
    # Count roles by matching player names in players dict (intelligent matching)
    roles = {"bat": 0, "bowl": 0, "alr": 0, "wk": 0}
    for p in xi_players:
        role = get_player_role(p)
        
        if role == "Batter":
            roles["bat"] += 1
        elif role == "Bowler":
            roles["bowl"] += 1
        elif role == "Allrounder":
            roles["alr"] += 1
        elif role == "Wicketkeeper":
            roles["wk"] += 1
    return roles, xi_players

async def check_squad_requirements(ctx, user_id):
    roles, squad_players = get_squad_counts(user_id)
    errors = []
    if not (3 <= roles["bat"] <= 5):
        errors.append("You need **3-5 batters**.")
    if not (3 <= roles["bowl"] <= 5):
        errors.append("You need **3-5 bowlers**.")
    if not (1 <= roles["alr"] <= 3):
        errors.append("You need **1-3 all-rounders**.")
    if not (1 <= roles["wk"] <= 2):
        errors.append("You need **1-2 wicketkeepers**.")
    if errors:
        embed = discord.Embed(
            title="Squad Requirements Not Met",
            description="\n".join(errors),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return False
    return True


# Helper function to check squad requirements in an async context
async def ensure_squad_requirements(ctx, user_id):
    if not await check_squad_requirements(ctx, user_id):
        return False  # Do not proceed if requirements not met
    return True
# Usage: await ensure_squad_requirements(ctx, user_id) inside your async command or handler


class DropView(discord.ui.View):
    def __init__(self, user_id, player, ovr, player_key, card_path, embed, timeout=30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.player = player
        self.ovr = ovr
        self.player_key = player_key
        self.card_path = card_path
        self.embed = embed
        self.message = None
        self.handled = False

    async def on_timeout(self):
        if self.handled:
            return

        self.handled = True

        # Auto-retain the dropped player if no response within timeout
        cursor.execute("SELECT rowid FROM squad WHERE userid=? AND LOWER(player_key)=?", 
                      (self.user_id, self.player_key.lower()))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE squad SET ovr=? WHERE rowid=?", (self.ovr, existing[0]))
        else:
            cursor.execute("INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)",
                          (self.user_id, self.player_key, self.ovr))
        db.commit()

        content = f"⏱️ Time's up! <@{self.user_id}> retained the card {self.player['name']}."
        if self.message is not None:
            try:
                await self.message.edit(content=content, embed=self.embed, view=None)
            except Exception:
                pass
        self.stop()

    @discord.ui.button(label="Retain", style=discord.ButtonStyle.primary)
    async def retain(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This drop is not for you.", ephemeral=True)
            return

        # Check if player already in squad, update if exists, insert if not
        cursor.execute("SELECT rowid FROM squad WHERE userid=? AND LOWER(player_key)=?", 
                      (self.user_id, self.player_key.lower()))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing player's OVR
            cursor.execute("UPDATE squad SET ovr=? WHERE rowid=?", (self.ovr, existing[0]))
        else:
            # Insert new player
            cursor.execute("INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)",
                          (self.user_id, self.player_key, self.ovr))
        
        db.commit()

        # Edit message
        content = f"{interaction.user.mention} Retained {self.player['name']}"
        self.handled = True
        try:
            await interaction.response.edit_message(content=content, embed=self.embed, view=None)
        except Exception:
            try:
                await interaction.message.edit(content=content, embed=self.embed, view=None)
            except Exception:
                pass
        self.stop()

    @discord.ui.button(label="Release", style=discord.ButtonStyle.danger)
    async def release(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This drop is not for you.", ephemeral=True)
            return

        # Calculate sell value
        from players import players, get_price_by_ovr
        buy_price = self.player.get("price") or get_price_by_ovr(self.ovr, self.player.get("category"))
        sell_value = buy_price // 2

        # Add to balance
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                      (sell_value, self.user_id))
        db.commit()

        # Edit message
        content = f"{interaction.user.mention} Released {self.player['name']}"
        self.handled = True
        try:
            await interaction.response.edit_message(content=content, embed=self.embed, view=None)
        except Exception:
            try:
                await interaction.message.edit(content=content, embed=self.embed, view=None)
            except Exception:
                pass
        self.stop()


class DropFullView(discord.ui.View):
    def __init__(self, user_id, player, ovr, player_key, card_path, embed, squad_players, timeout=30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.player = player
        self.ovr = ovr
        self.player_key = player_key
        self.card_path = card_path
        self.embed = embed
        self.squad_players = squad_players  # List of player names in squad
        self.message = None
        self.handled = False

        # Create dropdown options with display names, but keep canonical values for selection
        options = []
        for p in self.squad_players:
            display_name = players.get(p, {}).get("name", p.replace('_', ' ').title())
            option_value = p  # use key as value
            options.append(discord.SelectOption(label=display_name, value=option_value))
        options.append(discord.SelectOption(label="Release", value="release"))
        
        self.select = discord.ui.Select(
            placeholder="Choose player to replace or release",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def on_timeout(self):
        if self.handled:
            return

        self.handled = True

        from players import players, get_price_by_ovr
        buy_price = self.player.get("price") or get_price_by_ovr(self.ovr, self.player.get("category"))
        sell_value = buy_price // 2

        cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                      (sell_value, self.user_id))
        db.commit()

        content = f"⏱️ Time's up! <@{self.user_id}> released {self.player['name']} for {sell_value} CC."
        if self.message is not None:
            try:
                await self.message.edit(content=content, embed=self.embed, view=None)
            except Exception:
                pass
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This drop is not for you.", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        
        if choice == "release":
            # Calculate sell value
            from players import get_price_by_ovr
            buy_price = self.player.get("price") or get_price_by_ovr(self.ovr, self.player.get("category"))
            sell_value = buy_price // 2

            # Add to balance
            cursor.execute("UPDATE users SET balance = balance + ? WHERE id=?",
                          (sell_value, self.user_id))
            db.commit()

            # Edit message
            content = f"{interaction.user.mention} Released {self.player['name']}"
            self.handled = True
            try:
                await interaction.response.edit_message(content=content, embed=self.embed, view=None)
            except Exception:
                try:
                    await interaction.message.edit(content=content, embed=self.embed, view=None)
                except Exception:
                    pass
            
        else:
            # Replace the selected player
            display_choice = players.get(choice, {}).get("name", choice.replace('_', ' ').title())

            # Remove the selected player from squad
            cursor.execute(
                "DELETE FROM squad WHERE userid=? AND player_key=?",
                (self.user_id, choice)
            )
            
            # Add the new player
            cursor.execute("INSERT INTO squad(userid, player_key, ovr) VALUES(?,?,?)",
                          (self.user_id, self.player_key, self.ovr))
            
            db.commit()

            # Edit message
            content = f"{interaction.user.mention} Replaced {display_choice} with {self.player['name']}"
            self.handled = True
            try:
                await interaction.response.edit_message(content=content, embed=self.embed, view=None)
            except Exception:
                try:
                    await interaction.message.edit(content=content, embed=self.embed, view=None)
                except Exception:
                    pass
        
        self.stop()



