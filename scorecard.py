import discord
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from players import players


def get_ovr(player_name):
    if not player_name:
        return 80, 80
    key = player_name.lower().replace(" ", "_")
    p = players.get(key)
    if not p:
        return 80, 80
    bat = p.get("bat_ovr") or p.get("ovr") or 80
    bowl = p.get("bowl_ovr") or p.get("ovr") or 80
    return bat, bowl


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
        return "—"
    key = get_player_key_from_name(player_name)
    if key:
        return players.get(key, {}).get("name", player_name)
    return player_name


def get_timeline_squares(timeline):
    """Converts timeline into color-coded squares with spacing for clarity."""
    res = []
    for ball in (timeline or [])[-12:]:
        if ball == "W":
            res.append("🔴")
        elif ball == "4":
            res.append("4️⃣")
        elif ball == "6":
            res.append("6️⃣")
        elif ball == "2":
            res.append("2️⃣")
        elif ball == "1":
            res.append("1️⃣")
        elif ball == "0" or ball == "dot":
            res.append("⚪")
        # else branch removed: unknown balls are ignored
    return " ".join(res) if res else "🏟️ *Match just started...*"


def get_current_player_ovr(player_name):
    """Get player OVR dynamically from players.py (not from database)"""
    key = get_player_key_from_name(player_name)
    if not key:
        return None
    ov = players.get(key, {}).get("ovr")
    return int(ov) if isinstance(ov, (int, float)) else None


def score_embed(match):
    batting_team = getattr(match, "batting_team_name", None) or getattr(match, "batting", None)
    bowling_team = getattr(match, "bowling_team_name", None) or getattr(match, "bowling", None)
    if hasattr(batting_team, "name"):
        batting_team = batting_team.name
    if hasattr(bowling_team, "name"):
        bowling_team = bowling_team.name
    batting_team = str(batting_team).upper()
    bowling_team = str(bowling_team).upper()

    runs = getattr(match, "runs", 0)
    wickets = getattr(match, "wickets", 0)
    balls = getattr(match, "balls", 0)
    max_balls = getattr(match, "max_balls", 0)
    target = getattr(match, "target", None)
    partnership_runs = getattr(match, "partnership_runs", 0)
    partnership_balls = getattr(match, "partnership_balls", 0)
    innings = getattr(match, "innings", 1)

    # Header Logic with Visual Indicators
    if innings == 1:
        score_title = f"🏏 {batting_team} vs {bowling_team}"
        score_val = f"**{runs}/{wickets}** ┃ {match.over() if hasattr(match, 'over') else f'{balls // 6}.{balls % 6}'} Overs"
        extra_info = f"🎯 Projected: **{int((runs / balls) * max_balls) if balls > 0 and max_balls > 0 else 0}**"
        rr_label = "📈 CRR"
    else:
        score_title = f"⚔️ THE CHASE: {batting_team}"
        score_val = f"**{runs}/{wickets}** ┃ {match.over() if hasattr(match, 'over') else f'{balls // 6}.{balls % 6}'} Overs"
        req_runs = target - runs if target is not None else 0
        balls_left = max_balls - balls if max_balls > 0 else 0
        extra_info = f"🎯 Need **{req_runs}** from **{balls_left}** balls"
        rr_label = "📉 RRR"

    crr = round((runs / balls) * 6, 2) if balls > 0 else 0.0
    ps = f"{partnership_runs} ({partnership_balls}b)"

    embed = discord.Embed(title=score_title, color=0x2f3136)
    embed.add_field(name="SCORE", value=f"### {score_val}", inline=False)
    embed.add_field(name=rr_label, value=f"` {crr} `", inline=True)
    embed.add_field(name="🤝 PARTNERSHIP", value=f"` {ps} `", inline=True)
    embed.add_field(name="📝 STATUS", value=extra_info, inline=True)

    def fmt_batter(name, stats, is_striker):
        mark = "🏏" if is_striker else "  "
        n = get_player_display_name(name)[:12].ljust(12)
        r = str(stats.get('runs', 0)).rjust(3)
        b = str(stats.get('balls', 0)).rjust(3)
        sr_val = (stats.get('runs', 0) / stats.get('balls', 1) * 100) if stats.get('balls', 0) > 0 else 0
        sr_color = "32" if sr_val >= 150 else "37"
        return f"{mark} {n} {r}({b})  \u001b[{sr_color}m{sr_val:>6.1f}\u001b[0m"

    bat_rows = []
    striker = getattr(match, 'striker', None)
    non_striker = getattr(match, 'non_striker', None)

    if striker:
        bat_rows.append(fmt_batter(striker, match.batting_stats.get(striker, {'runs': 0, 'balls': 0}), True))
    if non_striker:
        bat_rows.append(fmt_batter(non_striker, match.batting_stats.get(non_striker, {'runs': 0, 'balls': 0}), False))

    if bat_rows:
        embed.add_field(
            name="BATTERS",
            value=f"```ansi\nPLAYER           RUNS(B)    SR\n{chr(10).join(bat_rows)}```",
            inline=False
        )

    current_bowler = getattr(match, 'current_bowler', None)
    if current_bowler:
        b_stats = match.bowling_stats.get(current_bowler, {'runs': 0, 'balls': 0, 'wickets': 0})
        ov = f"{b_stats.get('balls', 0) // 6}.{b_stats.get('balls', 0) % 6}"
        econ = (b_stats.get('runs', 0) / b_stats.get('balls', 0) * 6) if b_stats.get('balls', 0) > 0 else 0
        wkt = b_stats.get('wickets', 0)
        bowl_info = (
            f"**{get_player_display_name(current_bowler)}**\n"
            f"⭕ {ov} Ov ┃ 📉 {econ:.1f} Eco ┃  wickets: **{wkt}**"
        )
        embed.add_field(name="CURRENT BOWLER", value=bowl_info, inline=True)

    embed.add_field(name="LAST 12 BALLS", value=get_timeline_squares(getattr(match, 'timeline', [])), inline=False)

    return embed


def innings_summary_embed(match):
    """Creates an innings summary with top 5 batters and top 5 bowlers."""

    batting_team = match.batting_team_name if hasattr(match, 'batting_team_name') else match.batting.name
    bowling_team = match.bowling_team_name if hasattr(match, 'bowling_team_name') else match.bowling.name

    # Determine the current batting and bowling lineup.
    batting_lineup = match.team1 if match.batting == match.p1 else match.team2
    bowling_lineup = match.team1 if match.bowling == match.p1 else match.team2

    batting_roles = {"Batter", "Allrounder", "Wicketkeeper"}
    bowling_roles = {"Bowler", "Allrounder"}

    batting_candidates = [p for p in batting_lineup if players.get(p, {}).get("role") in batting_roles]
    if len(batting_candidates) < 5:
        batting_candidates = batting_lineup

    bowling_candidates = [p for p in bowling_lineup if players.get(p, {}).get("role") in bowling_roles]
    if len(bowling_candidates) < 5:
        bowling_candidates = bowling_lineup

    # Batters who have come to crease
    batted = [p for p in match.batters if p in batting_candidates]

    # Batters who scored runs, sorted by runs desc.
    scored_batters = [p for p in batted if match.batting_stats.get(p, {}).get("runs", 0) > 0]
    scored_sorted = sorted(scored_batters, key=lambda p: -match.batting_stats.get(p, {}).get("runs", 0))

    # Remaining batters who did not bat, excluding Allrounders, sorted by bat_ovr desc.
    did_not_bat = [p for p in batting_candidates if p not in batted and players.get(p, {}).get("role") != "Allrounder"]
    remaining_sorted = sorted(did_not_bat, key=lambda p: -get_ovr(p)[0])

    # Combine
    all_batters = scored_sorted + remaining_sorted

    batters_display = []
    for player in all_batters:
        if len(batters_display) >= 5:
            break
        stats = match.batting_stats.get(player, {})
        player_display = get_player_display_name(player)
        runs = stats.get("runs", 0)
        balls = stats.get("balls", 0)
        not_out = player not in match.dismissed
        if runs > 0:
            batters_display.append(
                f"**{player_display}** - {runs}{'*' if not_out else ''}({balls})"
            )
        else:
            batters_display.append(f"**{player_display}** - Did not bat")

    if not batters_display:
        batters_text = "No batters yet"
    else:
        batters_text = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(batters_display))

    # Bowlers who have bowled
    bowled = [p for p in bowling_candidates if match.bowling_stats.get(p, {}).get("balls", 0) > 0]

    # Bowlers who took wickets, sorted by wickets desc.
    wicket_takers = [p for p in bowled if match.bowling_stats.get(p, {}).get("wickets", 0) > 0]
    wicket_sorted = sorted(wicket_takers, key=lambda p: -match.bowling_stats.get(p, {}).get("wickets", 0))

    # Remaining bowlers who did not bowl, sorted by bowl_ovr desc.
    did_not_bowl = [p for p in bowling_candidates if p not in bowled]
    remaining_bowlers_sorted = sorted(did_not_bowl, key=lambda p: -get_ovr(p)[1])

    # Combine
    all_bowlers = wicket_sorted + remaining_bowlers_sorted

    bowlers_display = []
    for player in all_bowlers:
        if len(bowlers_display) >= 5:
            break
        stats = match.bowling_stats.get(player, {})
        player_display = get_player_display_name(player)
        wickets = stats.get("wickets", 0)
        runs = stats.get("runs", 0)
        balls = stats.get("balls", 0)
        overs = f"{balls // 6}.{balls % 6}"
        if balls > 0:
            bowlers_display.append(
                f"**{player_display}** - {wickets}/{runs} ({overs})"
            )
        else:
            bowlers_display.append(f"**{player_display}** - Did not bowl")

    if not bowlers_display:
        bowlers_text = "No bowlers yet"
    else:
        bowlers_text = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(bowlers_display))

    embed = discord.Embed(
        title=f"📊 Innings Summary - {batting_team} scored {match.runs}/{match.wickets}",
        description=f"Innings {match.innings} - {match.over()} overs",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="🏏 Top 5 Batters",
        value=batters_text,
        inline=True
    )
    embed.add_field(
        name="🎯 Top 5 Bowlers",
        value=bowlers_text,
        inline=True
    )

    return embed


def generate_final_scorecard_image(match, template_path=None, output_filename=None):
    if template_path is None:
        template_path = Path(__file__).resolve().parent / "templates" / "scorecard.png"
    else:
        template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Scorecard template not found: {template_path}")

    if output_filename is None:
        output_filename = Path(__file__).resolve().parent / "generated_cards" / "final_scorecard.png"
    else:
        output_filename = Path(output_filename)

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Use a Bold Sans-Serif font for the clean look
    font_dir = Path("C:/Windows/Fonts")
    try:
        font_main = ImageFont.truetype(str(font_dir / "arial.ttf"), size=60)
        font_sub = ImageFont.truetype(str(font_dir / "arial.ttf"), size=32)
        font_stats = ImageFont.truetype(str(font_dir / "cour.ttf"), size=26)
        # Try to load a bold font for names
        try:
            font_bold = ImageFont.truetype(str(font_dir / "arialbd.ttf"), size=26)
        except IOError:
            font_bold = font_stats
    except IOError:
        try:
            font_main = ImageFont.truetype("Arial.ttf", size=60)
            font_sub = ImageFont.truetype("Arial.ttf", size=32)
            font_stats = ImageFont.truetype("cour.ttf", size=26)
            try:
                font_bold = ImageFont.truetype("Arialbd.ttf", size=26)
            except IOError:
                font_bold = font_stats
        except IOError:
            font_main = font_sub = font_stats = font_bold = ImageFont.load_default()

    team_name = getattr(match, "batting_team_name", None) or getattr(match, "batting", None)
    if hasattr(team_name, "name"):
        team_name = team_name.name
    team_name = str(team_name).upper()

    # Determine first and second innings teams
    def team_list_for_user(user):
        if user == match.p1:
            return match.team1
        return match.team2

    first_batting_user = match.bowling if match.innings == 2 else match.batting
    second_batting_user = match.batting if match.innings == 2 else None
    first_batting_team = team_list_for_user(first_batting_user)
    second_batting_team = team_list_for_user(second_batting_user) if second_batting_user else []
    second_bowling_team = match.team1 if second_batting_team == match.team2 else match.team2 if second_batting_team else []

    def format_team_label(name, score=None, overs=None):
        if score is None or overs is None:
            return name
        return f"{name}  {score} ({overs} Ov)"

    first_batting_name = getattr(first_batting_user, "name", str(first_batting_user)).upper()
    if match.first_innings_score and match.first_innings_overs:
        first_batting_label = format_team_label(first_batting_name, match.first_innings_score, match.first_innings_overs)
    elif match.innings == 1:
        first_batting_label = format_team_label(first_batting_name, f"{match.runs}/{match.wickets}", match.over())
    else:
        first_batting_label = first_batting_name

    second_batting_name = getattr(second_batting_user, "name", str(second_batting_user)).upper() if second_batting_user else "SECOND INNINGS"
    if match.innings == 2:
        second_batting_label = format_team_label(second_batting_name, f"{match.runs}/{match.wickets}", match.over())
    else:
        second_batting_label = second_batting_name

    draw.text((1268, 150), first_batting_label, fill="#FFFFFF", font=font_sub, anchor="mm")
    draw.text((413, 150), second_batting_label, fill="#FFFFFF", font=font_sub, anchor="mm")
    draw.text((500, 180), f"{match.runs}/{match.wickets} ({match.over()})", fill="#58b9ff", font=font_sub, anchor="mm")

    # First innings batting and bowling stats
    first_batting_stats = match.first_innings_batting if match.first_innings_batting else {}
    first_bowling_stats = match.first_innings_bowling if match.first_innings_bowling else {}
    second_batting_stats = match.batting_stats
    second_bowling_stats = match.bowling_stats

    def draw_stats_box(x, y, title, lines):
        draw.text((x, y), title, fill="#58b9ff", font=font_sub)
        y += 40
        for line in lines:
            # Bold the player name (first 18 chars)
            name_part = line[:18]
            rest_part = line[18:]
            draw.text((x, y), name_part, fill="white", font=font_bold)
            # Use textbbox to get width of name_part
            try:
                bbox = draw.textbbox((x, y), name_part, font=font_bold)
                name_width = bbox[2] - bbox[0] if bbox else 0
            except AttributeError:
                name_width, _ = draw.textsize(name_part, font=font_bold)
            draw.text((x + name_width, y), rest_part, fill="white", font=font_stats)
            y += 34

    def build_batting_lines(team, stats, batting_order=None):
        batting_order = [p for p in (batting_order or []) if p in team]
        remaining = [p for p in team if p not in batting_order]
        remaining_sorted = sorted(remaining, key=lambda p: -get_ovr(p)[0])
        ordered = batting_order + remaining_sorted

        lines = []
        for player in ordered:
            display_name = get_player_display_name(player)[:18].ljust(18)
            player_stats = stats.get(player, {"runs": 0, "balls": 0})
            if player in batting_order:
                runs = player_stats.get("runs", 0)
                balls = player_stats.get("balls", 0)
                not_out = player not in match.dismissed
                lines.append(f"{display_name} {runs}{'*' if not_out else ''}({balls})")
            else:
                if player_stats.get("balls", 0) == 0 and player_stats.get("runs", 0) == 0:
                    lines.append(f"{display_name} DID NOT BAT")
                else:
                    lines.append(f"{display_name} {player_stats['runs']}({player_stats['balls']})")
        return lines

    def build_bowling_lines(team, stats):
        bowling_candidates = [p for p in team if players.get(p, {}).get("role") in {"Bowler", "Allrounder"}]
        bowled = [p for p in bowling_candidates if stats.get(p, {}).get("balls", 0) > 0]
        bowled_sorted = sorted(
            bowled,
            key=lambda p: (
                -stats.get(p, {}).get("wickets", 0),
                stats.get(p, {}).get("runs", 0),
                stats.get(p, {}).get("balls", 0),
            ),
        )
        did_not_bowl = [p for p in bowling_candidates if p not in bowled]
        remaining_sorted = sorted(did_not_bowl, key=lambda p: -get_ovr(p)[1])
        ordered = bowled_sorted + remaining_sorted

        lines = []
        for player in ordered:
            display_name = get_player_display_name(player)[:18].ljust(18)
            player_stats = stats.get(player, {"runs": 0, "balls": 0, "wickets": 0})
            if player_stats.get("balls", 0) == 0:
                lines.append(f"{display_name} YET TO BOWL")
            else:
                ov = f"{player_stats['balls']//6}.{player_stats['balls']%6}"
                lines.append(f"{display_name} {player_stats['wickets']}-{player_stats['runs']} ({ov})")
        return lines

    first_batting_order = match.batters if match.innings == 1 else []
    second_batting_order = match.batters if match.innings == 2 else []

    first_bat_lines = build_batting_lines(first_batting_team, first_batting_stats, first_batting_order)
    first_bowl_team = match.team1 if first_batting_team == match.team2 else match.team2
    first_bowl_lines = build_bowling_lines(first_bowl_team, first_bowling_stats)

    second_bat_lines = build_batting_lines(second_batting_team, second_batting_stats, second_batting_order)
    second_bowl_lines = build_bowling_lines(second_bowling_team, second_bowling_stats)

    draw_stats_box(915, 190, "BATTERS", first_bat_lines)
    draw_stats_box(915, 620, "BOWLERS", first_bowl_lines)
    draw_stats_box(90, 190, "BATTERS", second_bat_lines)
    draw_stats_box(90, 620, "BOWLERS", second_bowl_lines)

    if output_filename.parent:
        output_filename.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_filename)
    return str(output_filename)
