import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", 0))
PARENT_CATEGORY_ID = int(os.getenv("PARENT_CATEGORY_ID", 0))
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", 0))
IMAGE_URL = os.getenv("IMAGE_URL", "")
NIGHT_IMAGE_URL = os.getenv("NIGHT_IMAGE_URL", "")
DAY_IMAGE_URL = os.getenv("DAY_IMAGE_URL", "")
VOTE_IMAGE_URL = os.getenv("VOTE_IMAGE_URL", "")

ROLE_EASY_ID = int(os.getenv("ROLE_EASY_ID", 0))
ROLE_CLASSIC_ID = int(os.getenv("ROLE_CLASSIC_ID", 0))
RULES_CHANNEL_ID = int(os.getenv("RULES_CHANNEL_ID", 0))
RESULTS_CHANNEL_ID = int(os.getenv("RESULTS_CHANNEL_ID", 0))

TIME_EMOJI = os.getenv("TIME_EMOJI", "<:time:1544687699389186048>")
MUTE_EMOJI = os.getenv("MUTE_EMOJI", "<:Mute:1544687593323761756>")
MUTED_AUDIO_EMOJI = os.getenv("MUTED_AUDIO_EMOJI", "<:muted_audio:1544687640891105392>")

BAN_ROLE_ID = int(os.getenv("BAN_ROLE_ID", 0))

# Новая переменная – ID голосового канала, куда перемещать после игры
AFTER_GAME_VOICE_CHANNEL_ID = int(os.getenv("AFTER_GAME_VOICE_CHANNEL_ID", 0))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")