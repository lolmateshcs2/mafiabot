import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import aiohttp
import os
from database import get_player_data
import config

# ------------------------------------------------------------
# НАСТРОЙКИ
# ------------------------------------------------------------
DEBUG = False
CANVAS_SIZE = (800, 422)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, "template.png")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "Inter-ExtraLight.ttf")

FONT_SIZE_NICK = 32
FONT_SIZE_ROLE = 20
FONT_SIZE_ROLES = 20
FONT_SIZE_INFO  = 16

COLOR_NICK = (255, 255, 255)
COLOR_ROLE = (200, 200, 200)
COLOR_STATS = (255, 255, 255)

# ID ролей для определения должности
ROLE_ADMIN_ID = 1538695654430212206
ROLE_HOST_ID = 1538685933178593290
ROLE_PLAYER_ID = 1538687965876719697

# ------------------------------------------------------------
# КООРДИНАТЫ
# ------------------------------------------------------------
POSITIONS = {
    "avatar": {"x": 50, "y": 55, "size": (201, 199)},
    "nick": {"x": 150, "y": 274},
    "role": {"x": 150, "y": 316},
    "roles": {
        "Мирный":  {"wins": (338, 194), "games": (338, 234)},
        "Шериф":   {"wins": (440, 194), "games": (440, 234)},
        "Доктор":  {"wins": (542, 194), "games": (542, 234)},
        "Мафия":   {"wins": (644, 194), "games": (644, 234)},
        "Дон":     {"wins": (746, 194), "games": (746, 234)},
    },
    "info": {
        "first_game": (421, 332),
        "total_wins":  (426, 350),
        "coins":       (380, 369),
        "total_games": (736, 330),
        "top":         (726, 350),
        "rating":      (688, 369),
    }
}

# ------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ------------------------------------------------------------
async def get_avatar_circle(user, size):
    async with aiohttp.ClientSession() as session:
        async with session.get(user.display_avatar.url) as resp:
            avatar_data = await resp.read()
    avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")
    avatar = avatar.resize(size, Image.LANCZOS)
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    avatar = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
    avatar.putalpha(mask)
    return avatar

def get_display_role(member, db_role):
    """Определяет, какую должность показывать: серверную роль или игровую."""
    roles = [r.id for r in member.roles]
    if ROLE_ADMIN_ID in roles:
        return "Админ"
    elif ROLE_HOST_ID in roles:
        return "Ведущий"
    elif ROLE_PLAYER_ID in roles:
        return "Игрок"
    else:
        return db_role  # Новичок, Игрок, Опытный, Мафиози

async def generate_profile_image(user, player_data, member):
    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    try:
        bg = Image.open(TEMPLATE_PATH).convert("RGBA")
        bg = bg.resize(CANVAS_SIZE, Image.LANCZOS)
    except:
        bg = Image.new("RGBA", CANVAS_SIZE, (30, 30, 40, 255))
    canvas.paste(bg, (0, 0))
    draw = ImageDraw.Draw(canvas)

    try:
        font_nick = ImageFont.truetype(FONT_PATH, FONT_SIZE_NICK)
        font_role = ImageFont.truetype(FONT_PATH, FONT_SIZE_ROLE)
        font_roles = ImageFont.truetype(FONT_PATH, FONT_SIZE_ROLES)
        font_info  = ImageFont.truetype(FONT_PATH, FONT_SIZE_INFO)
    except:
        font_nick = font_role = font_roles = font_info = ImageFont.load_default()

    def draw_text(x, y, text, font, color=(255,255,255), center=False):
        if center:
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            except:
                tw, th = draw.textsize(text, font=font)
            x = x - tw // 2
            # центрирование по вертикали не делаем, оставляем y как есть
        draw.text((x, y), text, font=font, fill=color)
        if DEBUG:
            try:
                bbox = draw.textbbox((x, y), text, font=font)
            except:
                w, h = draw.textsize(text, font=font)
                bbox = (x, y, x + w, y + h)
            draw.rectangle(bbox, outline=(255, 0, 0), width=1)

    avatar = await get_avatar_circle(user, POSITIONS["avatar"]["size"])
    canvas.paste(avatar, (POSITIONS["avatar"]["x"], POSITIONS["avatar"]["y"]), avatar)

    display_role = get_display_role(member, player_data["role"])
    draw_text(POSITIONS["nick"]["x"], POSITIONS["nick"]["y"], user.name, font_nick, COLOR_NICK, center=True)
    draw_text(POSITIONS["role"]["x"], POSITIONS["role"]["y"], display_role, font_role, COLOR_ROLE, center=True)

    # Роли (здесь центрирование оставлено, так как это числовые поля внутри областей)
    for role, coords in POSITIONS["roles"].items():
        stats = player_data["roles"].get(role, {"wins": 0, "games": 0})
        draw_text(coords["wins"][0], coords["wins"][1], str(stats["wins"]), font_roles, COLOR_STATS, center=True)
        draw_text(coords["games"][0], coords["games"][1], str(stats["games"]), font_roles, COLOR_STATS, center=True)

    # Информационный блок – убрано центрирование
    for key, (x, y) in POSITIONS["info"].items():
        value = player_data.get(key, "")
        if key == "rating":
            value = f"{value:.1f}"
        elif key == "first_game" and value is None:
            value = "—"
        else:
            value = str(value)
        draw_text(x, y, value, font_info, COLOR_STATS, center=False)

    buf = io.BytesIO()
    canvas.save(buf, format='PNG')
    buf.seek(0)
    return buf

# ------------------------------------------------------------
# КОГ
# ------------------------------------------------------------
class MafiaStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="mafia_stats", description="Показать статистику игрока")
    async def mafia_stats(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = interaction.user
        data = get_player_data(user.id)
        try:
            img = await generate_profile_image(user, data, user)
            await interaction.followup.send(file=discord.File(fp=img, filename="profile.png"))
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

# ------------------------------------------------------------
# ОБЯЗАТЕЛЬНАЯ ФУНКЦИЯ SETUP
# ------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(MafiaStatsCog(bot))