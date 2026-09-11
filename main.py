import discord
from discord.ext import commands
import config
from database import init_db

init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} готов!")
    try:
        await bot.load_extension("cogs.mafia_setup")
        await bot.load_extension("cogs.mafia_stats")
        await bot.tree.sync()
        print("✅ Все коги загружены, команды синхронизированы")
    except Exception as e:
        print(f"❌ Ошибка загрузки когов: {e}")

if __name__ == "__main__":
    bot.run(config.BOT_TOKEN)