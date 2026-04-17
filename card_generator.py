from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import discord


def generate_card(player_id, player, player_key=None):

    base_dir = Path(__file__).resolve().parent

    if player_key is None:
        player_key = player.get("name", "").lower().replace(" ", "_")

    template_path = base_dir / "templates" / "card.png"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with Image.open(template_path) as template_file:
        template = template_file.convert("RGBA")
    draw = ImageDraw.Draw(template)

    # ---------- FONT LOADER ----------
    def try_font(names, size):
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_ovr = try_font(["Oswald-Bold.ttf", "arialbd.ttf", "arial.ttf"], 140)
    font_name = try_font(["Montserrat-Bold.ttf", "Montserrat-Bold.ttf", "Montserrat-Bold.ttf"], 64)
    font_role = try_font(["Montserrat-BoldItalic.ttf", "Montserrat-BoldItalic.ttf"], 36)
    font_stats = try_font(["Poppins-ExtraBold.ttf", "Poppins-ExtraBold.ttf"], 85)

    # ---------- CENTER TEXT ----------
    def draw_centered(text, font, box_left, box_top, box_width,
                      fill="orange", stroke_width=0, stroke_fill=None):

        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        w = bbox[2] - bbox[0]

        x = box_left + max(0, (box_width - w) // 2)

        draw.text(
            (x, box_top),
            text,
            fill=fill,
            font=font,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill
        )

    name = player.get("name", "").upper().strip()

    # ---------- PLAYER IMAGE ----------
    player_image_dir = base_dir / "player_images"

    if player_key and player_image_dir.exists():

        for ext in ("png", "jpg", "jpeg"):

            image_path = player_image_dir / f"{player_key}.{ext}"

            if image_path.exists():
                try:
                    with Image.open(image_path) as img_file:
                        img = img_file.convert("RGBA")

                        box_left, box_top = 104, 85
                        box_width, box_height = 774 - 104, 820 - 79

                        img.thumbnail((box_width, box_height), Image.LANCZOS)

                        new_w = int(img.width * 1.085)
                        new_h = int(img.height * 1.085)

                        img = img.resize((new_w, new_h), Image.LANCZOS)

                        offset_x = box_left + (box_width - img.width) // 2
                        offset_y = box_top + (box_height - img.height) // 2

                        template.paste(img, (offset_x, offset_y), img)

                except Exception:
                    pass

                break

    # ---------- TEXT ELEMENTS ----------

    draw_centered(
        str(player.get("ovr", "")),
        font_ovr,
        box_left=77,
        box_top=78,
        box_width=180,
        fill="#9b30ff",
        stroke_width=3,
        stroke_fill="black"
    )

    draw_centered(
        name,
        font_name,
        box_left=117,
        box_top=825,
        box_width=670,
        fill="black"
    )

    role_text = player.get("role", "").upper()

    draw_centered(
        role_text,
        font_role,
        box_left=350,
        box_top=911.5,
        box_width=338,
        fill="white",
        stroke_width=2,
        stroke_fill="black"
    )

    bat_ovr = player.get("bat_ovr") or player.get("batovr")
    bowl_ovr = player.get("bowl_ovr") or player.get("bowlovr")

    draw_centered(
        str(bat_ovr),
        font_stats,
        box_left=314,
        box_top=979,
        box_width=98,
        fill="white",
        stroke_width=2,
        stroke_fill="black"
    )

    draw_centered(
        str(bowl_ovr),
        font_stats,
        box_left=670,
        box_top=978,
        box_width=98,
        fill="white",
        stroke_width=2,
        stroke_fill="black"
    )

    # ---------- SAVE CARD ----------
    output_dir = base_dir / "generated_cards"
    output_dir.mkdir(parents=True, exist_ok=True)

    save_path = output_dir / f"{player_id}.png"

    template.save(save_path)

    return str(save_path)


def create_player_embed(player, player_id, player_key, include_category=True):
    role = player["role"][:-1] if player["role"].endswith("s") else player["role"]
    
    country = player.get('country', 'Unknown')
    country_abbrev = {
        'SL': 'Sri Lanka',
        'ZIM': 'Zimbabwe', 
        'AUS': 'Australia',
        'ENG': 'England',
        'AFG': 'Afghanistan',
        'IND': 'India',
        'BAN': 'Bangladesh',
        "SA": "South Africa",
        "US": "United States",
        'WI': 'West Indies'
    }.get(country, country)
    category = player.get('category')
    category_suffix = f" :: **Category {category}**" if include_category and category else ""
    
    embed = discord.Embed(
        title=player_key.replace('_', ' ').title(),
        description=f"**{role.upper()}** :: **{country_abbrev}**{category_suffix}",
        color=discord.Color.blue()
    )

    price_value = None
    price_field = player.get("price")
    if isinstance(price_field, (int, float)):
        price_value = int(price_field)
    elif isinstance(price_field, str) and price_field.strip().isdigit():
        price_value = int(price_field.strip())
    if price_value is not None:
        embed.add_field(name="Price", value=f"{price_value:,} CC")

    custom_image = player.get("image")
    if custom_image:
        custom_path = Path(custom_image)
        if not custom_path.is_absolute():
            custom_path = Path(__file__).resolve().parent / custom_image

        if custom_path.exists():
            file = discord.File(str(custom_path), filename="card.png")
            embed.set_image(url="attachment://card.png")
            return embed, file
        else:
            print(f"[create_player_embed] custom image not found: {custom_path}")

    try:
        card_path = generate_card(player_id, player, player_key=player_key)
        file = discord.File(card_path, filename="card.png")
        embed.set_image(url="attachment://card.png")
        return embed, file
    except Exception as e:
        print("[create_player_embed] card generation failed:", e)
        import traceback
        traceback.print_exc()
        return embed, None