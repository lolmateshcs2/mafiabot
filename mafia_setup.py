import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time
from config import (
    PARENT_CATEGORY_ID,
    ANNOUNCE_CHANNEL_ID,
    IMAGE_URL,
    ROLE_EASY_ID,
    ROLE_CLASSIC_ID,
    RULES_CHANNEL_ID,
    TIME_EMOJI,
    MUTE_EMOJI,
    MUTED_AUDIO_EMOJI,
    VOTE_IMAGE_URL,
    BAN_ROLE_ID,
    ALLOWED_ROLE_ID,
    AFTER_GAME_VOICE_CHANNEL_ID
)
from utils.checks import check_allowed_role
from .mafia_game import MafiaGame
from database import get_top_players
from .mafia_messages import MafiaMessages

# ---------- Модальное окно для упоминания ролей ----------
class MentionCountModal(discord.ui.Modal, title="Упомянуть роли"):
    count = discord.ui.TextInput(
        label="Сколько не хватает?",
        placeholder="Введите число от 1 до 10",
        required=True,
        min_length=1,
        max_length=2
    )

    def __init__(self, channel_id: int, cog, role_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.cog = cog
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.count.value)
            if count < 1 or count > 10:
                await interaction.response.send_message("❌ Введите число от 1 до 10.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Введите число.", ephemeral=True)
            return

        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра не найдена.", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Роль не найдена на сервере.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Канал записи не найден.", ephemeral=True)
            return

        await channel.send(f"{role.mention}, требуется {count} игроков для заполнения слота!")
        await interaction.response.send_message("✅ Упоминание отправлено!", ephemeral=True)

class MentionRoleSelect(discord.ui.Select):
    def __init__(self, channel_id: int, cog):
        self.channel_id = channel_id
        self.cog = cog
        options = [
            discord.SelectOption(label="Городская", value="easy", description="Роль для городской мафии"),
            discord.SelectOption(label="Классическая", value="classic", description="Роль для классической мафии")
        ]
        super().__init__(placeholder="Выберите роль", options=options, custom_id="mention_role_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "easy":
            role_id = ROLE_EASY_ID
        else:
            role_id = ROLE_CLASSIC_ID
        modal = MentionCountModal(channel_id=self.channel_id, cog=self.cog, role_id=role_id)
        await interaction.response.send_modal(modal)

class MentionRoleView(discord.ui.View):
    def __init__(self, channel_id: int, cog):
        super().__init__(timeout=None)
        self.add_item(MentionRoleSelect(channel_id, cog))

# ---------- Кнопки регистрации ----------
class RegistrationView(discord.ui.View):
    def __init__(self, channel_id: int, cog):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.cog = cog

    @discord.ui.button(label="Записаться", style=discord.ButtonStyle.primary, custom_id="register")
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.followup.send("Игра уже завершена.", ephemeral=True)
            return
        if game.get('started', False):
            await interaction.followup.send("Игра уже началась, запись закрыта.", ephemeral=True)
            return

        # Ведущий не может записаться
        if interaction.user.id == game['creator_id']:
            await interaction.followup.send("❌ Ведущий не может записаться в игру.", ephemeral=True)
            return

        ban_role = interaction.guild.get_role(BAN_ROLE_ID)
        if ban_role and ban_role in interaction.user.roles:
            await interaction.followup.send("❌ Вы не можете записаться, у вас роль 'мафия бан'!", ephemeral=True)
            return

        if interaction.user.id in game['players']:
            await interaction.followup.send("Вы уже записаны!", ephemeral=True)
            return
        if len(game['players']) >= 10:
            await interaction.followup.send("Мест больше нет! Максимум 10 игроков.", ephemeral=True)
            return

        game['players'].add(interaction.user.id)
        await self._update_all(interaction)
        await self.cog.update_ready_check(interaction.guild, self.channel_id)
        await interaction.followup.send("✅ Вы записались!", ephemeral=True)

    @discord.ui.button(label="Отписаться", style=discord.ButtonStyle.secondary, custom_id="unregister")
    async def unregister(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.followup.send("Игра уже завершена.", ephemeral=True)
            return
        if game.get('started', False):
            await interaction.followup.send("Игра уже началась, отписаться нельзя.", ephemeral=True)
            return
        if interaction.user.id not in game['players']:
            await interaction.followup.send("Вы не записаны.", ephemeral=True)
            return

        game['players'].remove(interaction.user.id)
        await self._update_all(interaction)
        await self.cog.update_ready_check(interaction.guild, self.channel_id)
        await interaction.followup.send("✅ Вы отписались!", ephemeral=True)

    async def _update_all(self, interaction: discord.Interaction):
        game = self.cog.games.get(self.channel_id)
        if game is None:
            return
        guild = interaction.guild
        channel = guild.get_channel(self.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(game['message_id'])
                embed = self.cog.build_registration_embed(game, guild)
                await msg.edit(embed=embed)
            except:
                pass
        announce_channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if announce_channel and game.get('announce_message_id'):
            try:
                msg = await announce_channel.fetch_message(game['announce_message_id'])
                embed = self.cog.build_announcement_embed(game, guild)
                await msg.edit(embed=embed)
            except:
                pass

# ---------- Кнопка афиши ----------
class AnnouncementView(discord.ui.View):
    def __init__(self, channel_url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="Присоединится к ивенту",
            style=discord.ButtonStyle.primary,
            url=channel_url
        ))

# ---------- Кнопка проверки готовности (только при 10 игроках) ----------
class ReadyCheckView(discord.ui.View):
    def __init__(self, channel_id: int, cog):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.cog = cog

    @discord.ui.button(label="✅ Проверить готовность", style=discord.ButtonStyle.success, custom_id="ready_check")
    async def ready_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        if button.disabled:
            await interaction.response.send_message("❌ Недостаточно игроков для проверки готовности (нужно 10).", ephemeral=True)
            return
        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра не найдена.", ephemeral=True)
            return
        if game.get('started', False):
            await interaction.response.send_message("❌ Игра уже запущена.", ephemeral=True)
            return
        if len(game['players']) != 10:
            await interaction.response.send_message("❌ Для проверки готовности нужно ровно 10 игроков.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.cog.start_ready_check(interaction, game)

# ---------- SelectMenu удаления игрока ----------
class RemovePlayerSelect(discord.ui.Select):
    def __init__(self, channel_id: int, cog, creator_id: int, guild: discord.Guild):
        self.channel_id = channel_id
        self.cog = cog
        self.creator_id = creator_id
        self.guild = guild
        self.bot = cog.bot

        game = cog.games.get(channel_id)
        options = []
        for uid in game['players']:
            user = self.bot.get_user(uid)
            name = user.name if user else f"ID {uid}"
            options.append(discord.SelectOption(label=name, value=str(uid), description=f"ID: {uid}"))
        super().__init__(placeholder="Выберите игрока для удаления", options=options, custom_id="remove_select")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Только ведущий может убирать игроков.", ephemeral=True)
            return
        uid = int(self.values[0])
        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра уже завершена.", ephemeral=True)
            return
        if uid not in game['players']:
            await interaction.response.send_message("❌ Этот игрок уже не в списке.", ephemeral=True)
            return
        game['players'].remove(uid)

        channel = self.guild.get_channel(self.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(game['message_id'])
                embed = self.cog.build_registration_embed(game, self.guild)
                await msg.edit(embed=embed)
            except Exception as e:
                await interaction.response.send_message(f"❌ Ошибка обновления: {e}", ephemeral=True)
                return

        announce_channel = self.guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if announce_channel and game.get('announce_message_id'):
            try:
                msg = await announce_channel.fetch_message(game['announce_message_id'])
                embed = self.cog.build_announcement_embed(game, self.guild)
                await msg.edit(embed=embed)
            except:
                pass

        await self.cog.update_ready_check(self.guild, self.channel_id)

        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        await interaction.response.send_message(f"✅ Игрок <@{uid}> удалён из списка.", ephemeral=True)

# ---------- ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ (до старта) ----------
class ControlMenu(discord.ui.Select):
    def __init__(self, creator_id: int, category_id: int, channel_id: int, cog):
        self.creator_id = creator_id
        self.category_id = category_id
        self.channel_id = channel_id
        self.cog = cog

        options = [
            discord.SelectOption(label="🚀 Запустить игру", description="Раздать роли и начать игру (требуется 10 игроков)", value="start"),
            discord.SelectOption(label="❌ Закончить событие", description="Удалить всё", value="end"),
            discord.SelectOption(label="📢 Оповестить о начале", description="Отправить афишу в канал", value="announce"),
            discord.SelectOption(label="📢 Созыв игроков", description="Напомнить игрокам зайти в войс", value="call"),
            discord.SelectOption(label="🔔 Упомянуть роли", description="Упомянуть роль с количеством", value="mention"),
            discord.SelectOption(label="👤 Убрать игрока", description="Исключить игрока из списка", value="remove")
        ]
        super().__init__(placeholder="Выберите действие", options=options, custom_id="control_menu")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Только ведущий может управлять ивентом!", ephemeral=True)
            return

        value = self.values[0]
        if value == "start":
            await self._start_event(interaction)
        elif value == "end":
            await self._end_event(interaction)
        elif value == "announce":
            await self._announce(interaction)
        elif value == "call":
            await self._call_players(interaction)
        elif value == "mention":
            await self._mention_roles(interaction)
        elif value == "remove":
            await self._remove_player(interaction)

    async def _start_event(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.followup.send("❌ Игра не найдена.", ephemeral=True)
            return
        if game.get('started', False):
            await interaction.followup.send("❌ Игра уже запущена.", ephemeral=True)
            return

        if len(game['players']) != 10:
            await interaction.followup.send("❌ Для запуска игры нужно ровно 10 игроков!", ephemeral=True)
            return

        await self.cog.game_logic.start_game(interaction, game)

    async def _end_event(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        category = interaction.guild.get_channel(self.category_id)
        if category is None:
            await interaction.followup.send("❌ Категория уже удалена или не найдена.", ephemeral=True)
            return
        await interaction.followup.send("✅ Ивент завершён! Все каналы и категория удалены.", ephemeral=True)
        try:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
            if self.channel_id in self.cog.games:
                del self.cog.games[self.channel_id]
        except Exception as e:
            print(f"Ошибка при удалении каналов: {e}")

    async def _announce(self, interaction: discord.Interaction):
        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра не найдена.", ephemeral=True)
            return
        announce_channel = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if announce_channel is None:
            await interaction.response.send_message("❌ Канал для оповещений не найден.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Канал записи не найден.", ephemeral=True)
            return
        channel_url = f"https://discord.com/channels/{interaction.guild.id}/{channel.id}"
        if game['mode'] == "Городская":
            role_id = ROLE_EASY_ID
        else:
            role_id = ROLE_CLASSIC_ID
        role = interaction.guild.get_role(role_id)
        if role:
            await announce_channel.send(role.mention)
        embed = self.cog.build_announcement_embed(game, interaction.guild)
        view = AnnouncementView(channel_url=channel_url)
        msg = await announce_channel.send(embed=embed, view=view)
        game['announce_message_id'] = msg.id
        await interaction.response.send_message("✅ Афиша отправлена в канал оповещений!", ephemeral=True)

    async def _call_players(self, interaction: discord.Interaction):
        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра не найдена.", ephemeral=True)
            return
        if game.get('started', False):
            await interaction.response.send_message("❌ Игра уже запущена.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.cog.call_missing_players(interaction, game)

    async def _mention_roles(self, interaction: discord.Interaction):
        # Кулдаун 5 минут
        now = time.time()
        last = self.cog.last_mention_time.get(self.channel_id, 0)
        if now - last < 300:
            remaining = int(300 - (now - last))
            await interaction.response.send_message(
                f"❌ Подождите {remaining} секунд перед следующим упоминанием.",
                ephemeral=True
            )
            return
        self.cog.last_mention_time[self.channel_id] = now

        view = MentionRoleView(channel_id=self.channel_id, cog=self.cog)
        await interaction.response.send_message("Выберите роль для упоминания:", view=view, ephemeral=True)

    async def _remove_player(self, interaction: discord.Interaction):
        game = self.cog.games.get(self.channel_id)
        if game is None:
            await interaction.response.send_message("❌ Игра не найдена.", ephemeral=True)
            return
        if not game['players']:
            await interaction.response.send_message("❌ Нет записанных игроков.", ephemeral=True)
            return
        select = RemovePlayerSelect(self.channel_id, self.cog, self.creator_id, interaction.guild)
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для удаления:", view=view, ephemeral=True)

class ControlView(discord.ui.View):
    def __init__(self, creator_id: int, category_id: int, channel_id: int, cog):
        super().__init__(timeout=None)
        self.add_item(ControlMenu(creator_id, category_id, channel_id, cog))

# ---------- Классы для проверки готовности ----------
class ReadyTimerView(discord.ui.View):
    def __init__(self, game, cog, control_channel_id):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.control_channel_id = control_channel_id

    @discord.ui.button(label="❌ Отменить проверку", style=discord.ButtonStyle.danger, custom_id="cancel_ready")
    async def cancel_ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game['creator_id']:
            await interaction.response.send_message("❌ Только ведущий может отменить проверку.", ephemeral=True)
            return
        control_channel = interaction.guild.get_channel(self.control_channel_id)
        if control_channel:
            async for msg in control_channel.history(limit=10):
                if msg.author == interaction.guild.me and msg.embeds and msg.embeds[0].title == "⏳ Проверка готовности":
                    await msg.delete()
                    break
        await interaction.response.send_message("✅ Проверка готовности отменена.", ephemeral=True)

class AcceptReadyView(discord.ui.View):
    def __init__(self, game, cog, pid, voice_channel_url: str = None):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.pid = pid
        if voice_channel_url:
            self.add_item(discord.ui.Button(
                label="🔊 Зайти в войс и принять готовность",
                style=discord.ButtonStyle.link,
                url=voice_channel_url
            ))
        else:
            self.add_item(discord.ui.Button(
                label="❌ Канал не найден, зайди вручную",
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))

class JoinVoiceView(discord.ui.View):
    def __init__(self, game, cog, pid, voice_channel_url: str = None):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.pid = pid
        if voice_channel_url:
            self.add_item(discord.ui.Button(
                label="🔊 Зайти в войс",
                style=discord.ButtonStyle.link,
                url=voice_channel_url
            ))
        else:
            self.add_item(discord.ui.Button(
                label="❌ Канал не найден",
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))

# ---------- Класс для отмены фола/преда (кнопки) ----------
class UndoView(discord.ui.View):
    def __init__(self, game, cog, member, punish_type):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.member = member
        self.punish_type = punish_type  # 'foul' or 'warning'

    @discord.ui.button(label="⏪ Отменить", style=discord.ButtonStyle.secondary, custom_id="undo_punish")
    async def undo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game['creator_id']:
            await interaction.response.send_message("❌ Только ведущий может отменить наказание.", ephemeral=True)
            return
        if self.punish_type == 'foul':
            await self.cog.undo_foul(interaction, self.game, self.member)
        else:
            await self.cog.undo_warning(interaction, self.game, self.member)

# ---------- МЕНЮ ВЕДУЩЕГО ПОСЛЕ ЗАПУСКА ----------
class HostMenuSelect(discord.ui.Select):
    def __init__(self, game, cog):
        self.game = game
        self.cog = cog
        options = [
            discord.SelectOption(label="⚠️ Выдать фол", description="Выдать фол игроку", value="foul"),
            discord.SelectOption(label="⚠️ Выдать предупреждение", description="Выдать предупреждение игроку", value="warning"),
            discord.SelectOption(label="🗳️ Голосование", description="Начать голосование за выгон", value="vote"),
            discord.SelectOption(label="⬆️ Поднять со стола", description="Убрать игрока из игры", value="revive"),
            discord.SelectOption(label="⏹️ Закончить игру досрочно", description="Завершить игру немедленно", value="end_early"),
            discord.SelectOption(label="↩️ Отменить фол", description="Отменить последний фол игроку", value="undo_foul"),
            discord.SelectOption(label="↩️ Отменить предупреждение", description="Отменить последнее предупреждение игроку", value="undo_warning")
        ]
        super().__init__(placeholder="Действия ведущего", options=options, custom_id="host_menu")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game['creator_id']:
            await interaction.response.send_message("❌ Только ведущий может управлять игрой!", ephemeral=True)
            return

        value = self.values[0]
        if value == "foul":
            await self.cog.handle_foul(interaction, self.game)
        elif value == "warning":
            await self.cog.handle_warning(interaction, self.game)
        elif value == "vote":
            await self.cog.handle_vote(interaction, self.game)
        elif value == "revive":
            await self.cog.handle_revive(interaction, self.game)
        elif value == "end_early":
            await self.cog.handle_end_early(interaction, self.game)
        elif value == "undo_foul":
            await self.cog.handle_undo_foul(interaction, self.game)
        elif value == "undo_warning":
            await self.cog.handle_undo_warning(interaction, self.game)

class HostMenuView(discord.ui.View):
    def __init__(self, game, cog):
        super().__init__(timeout=None)
        self.add_item(HostMenuSelect(game, cog))

# ---------- Класс для голосования ----------
class VoteView(discord.ui.View):
    def __init__(self, game, cog, candidate_id):
        super().__init__(timeout=10)
        self.game = game
        self.cog = cog
        self.candidate_id = candidate_id

    @discord.ui.button(label="🗳️ Проголосовать", style=discord.ButtonStyle.primary, custom_id="vote_button")
    async def vote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game['alive']:
            await interaction.response.send_message("❌ Вы уже мертвы или не в игре.", ephemeral=True)
            return
        if 'vote_counts' not in self.game:
            self.game['vote_counts'] = {}
        self.game['vote_counts'][interaction.user.id] = self.game['vote_counts'].get(interaction.user.id, 0) + 1
        await interaction.response.send_message(f"✅ Вы проголосовали за <@{self.candidate_id}>", ephemeral=True)

# ---------- Модальное окно для поднятия со стола ----------
class ReviveModal(discord.ui.Modal, title="Поднять игрока со стола"):
    reason = discord.ui.TextInput(label="Причина", placeholder="Введите причину", required=True)

    def __init__(self, game, cog, member):
        super().__init__()
        self.game = game
        self.cog = cog
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.game['creator_id']:
            await interaction.response.send_message("❌ Только ведущий может поднимать игроков.", ephemeral=True)
            return
        if self.member.id in self.game['alive']:
            self.game['alive'].remove(self.member.id)
        if self.member.id in self.game['players']:
            self.game['players'].remove(self.member.id)
        channel = interaction.guild.get_channel(self.game['channel_id'])
        if channel:
            embed = MafiaMessages.get_revive_embed(self.member.mention, self.reason.value)
            try:
                await channel.send(embed=embed)
            except discord.NotFound:
                pass
        await interaction.response.send_message(f"✅ Игрок {self.member.mention} удалён из игры.", ephemeral=True)
        try:
            await self.cog.game_logic.check_game_end(interaction.guild, self.game)
        except Exception as e:
            print(f"Ошибка при проверке завершения игры: {e}")

# ---------- ОСНОВНОЙ КОГ ----------
class MafiaSetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.games = {}
        self.game_logic = MafiaGame(bot, self)
        self.last_mention_time = {}  # channel_id -> timestamp

    # ---------- ВСЕ МЕТОДЫ УПРАВЛЕНИЯ ----------
    def build_registration_embed(self, game: dict, guild: discord.Guild) -> discord.Embed:
        mode_display = game['mode']
        embed = discord.Embed(
            title=f"**Мафия: {mode_display}**",
            description=f"Игроков: {len(game['players'])} из {game['max_players']}\nПроводит: <@{game['creator_id']}>",
            color=discord.Color.blue()
        )
        if game['players']:
            sorted_players = sorted(game['players'])
            players_list = "\n".join([f"{i+1}) <@{uid}>" for i, uid in enumerate(sorted_players)])
            embed.add_field(name="‎", value=players_list, inline=False)
        else:
            embed.add_field(name="‎", value="*Пока никого*", inline=False)
        embed.add_field(name="‎", value="—————————————————————", inline=False)
        creator = guild.get_member(game['creator_id'])
        if creator:
            embed.set_thumbnail(url=creator.display_avatar.url)
        return embed

    def build_announcement_embed(self, game: dict, guild: discord.Guild) -> discord.Embed:
        description = (
            "```Мафия — салонная командная психологическая пошаговая ролевая игра с детективным сюжетом.\n"
            "Моделирует борьбу информированных друг о друге членов организованного меньшинства с неорганизованным большинством.```\n"
            f"> Правила игры — <#{RULES_CHANNEL_ID}>\n"
            f"## Ведущий: <@{game['creator_id']}>\n"
            "### Награда за участие: __100__ <a:servercoin:1535225417957507112>\n"
            "### Награда за победу: __200__ <a:servercoin:1535225417957507112>"
        )
        embed = discord.Embed(
            title="🏛️ Мафия",
            description=description,
            color=discord.Color.blue()
        )
        creator = guild.get_member(game['creator_id'])
        if creator:
            embed.set_thumbnail(url=creator.display_avatar.url)
        if IMAGE_URL:
            embed.set_image(url=IMAGE_URL)
        return embed

    async def update_ready_check(self, guild: discord.Guild, channel_id: int):
        """Обновляет embed в канале управления, показывает кнопку только при 10 игроках."""
        game = self.games.get(channel_id)
        if not game:
            return
        if game.get('started', False):
            await self.remove_ready_check(guild, channel_id)
            return
        control_channel_id = game.get('control_channel_id')
        if not control_channel_id:
            return
        control_channel = guild.get_channel(control_channel_id)
        if not control_channel:
            return

        embed = MafiaMessages.get_control_embed(f"<@{game['creator_id']}>", game['players'])
        view = ReadyCheckView(channel_id=channel_id, cog=self)
        if len(game['players']) != 10:
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

        message_id = game.get('ready_check_message_id')
        if message_id:
            try:
                msg = await control_channel.fetch_message(message_id)
                await msg.edit(content=None, embed=embed, view=view)
                return
            except:
                pass
        msg = await control_channel.send(embed=embed, view=view)
        game['ready_check_message_id'] = msg.id

    async def remove_ready_check(self, guild: discord.Guild, channel_id: int):
        game = self.games.get(channel_id)
        if not game:
            return
        control_channel_id = game.get('control_channel_id')
        if not control_channel_id:
            return
        control_channel = guild.get_channel(control_channel_id)
        if not control_channel:
            return
        message_id = game.get('ready_check_message_id')
        if message_id:
            try:
                msg = await control_channel.fetch_message(message_id)
                await msg.delete()
            except:
                pass
            game['ready_check_message_id'] = None

    async def start_ready_check(self, interaction, game):
        if 'guild_id' not in game:
            game['guild_id'] = interaction.guild.id

        game['ready_status'] = {pid: False for pid in game['players']}

        control_channel = interaction.guild.get_channel(game['control_channel_id'])
        if not control_channel:
            await interaction.followup.send("❌ Канал управления не найден.", ephemeral=True)
            return

        voice_channel = await self.game_logic.get_voice_channel(interaction.guild, game)
        voice_channel_url = None
        if voice_channel:
            voice_channel_url = f"https://discord.com/channels/{interaction.guild.id}/{voice_channel.id}"
            members_in_voice = [member.id for member in voice_channel.members]
        else:
            members_in_voice = []

        for pid in game['players']:
            if pid in members_in_voice:
                continue
            user = interaction.guild.get_member(pid) or await self.bot.fetch_user(pid)
            if user:
                embed = discord.Embed(
                    title="🎮 Готовность к игре",
                    description="Зайди в голосовой канал и нажми кнопку ниже, чтобы подтвердить готовность.",
                    color=discord.Color.green()
                )
                view = AcceptReadyView(game, self, pid, voice_channel_url)
                await user.send(embed=embed, view=view)

        embed = MafiaMessages.get_ready_check_embed(0, len(game['players']))
        view = ReadyTimerView(game, self, control_channel.id)
        msg = await control_channel.send(embed=embed, view=view)
        game['ready_message_id'] = msg.id

        channel = interaction.guild.get_channel(game['channel_id'])
        if channel:
            violations = [f"{TIME_EMOJI} ㆍ<@{pid}> — {MUTE_EMOJI}" for pid in game['players']]
            embed = MafiaMessages.get_violations_embed(violations, "1:15")
            await channel.send(embed=embed)

        asyncio.create_task(self.ready_timer(interaction.guild, game, control_channel, msg, channel))

    async def ready_timer(self, guild, game, control_channel, msg, channel):
        total_seconds = 75
        interval = 15

        while total_seconds > 0:
            await asyncio.sleep(interval)
            total_seconds -= interval
            if total_seconds < 0:
                total_seconds = 0

            voice_channel = await self.game_logic.get_voice_channel(guild, game)
            if voice_channel:
                members_in_voice = [member.id for member in voice_channel.members]
                for pid in game['players']:
                    if pid in members_in_voice:
                        if 'ready_status' not in game:
                            game['ready_status'] = {}
                        game['ready_status'][pid] = True

            players = game['players']
            ready_count = sum(1 for pid in players if game.get('ready_status', {}).get(pid, False))

            minutes = total_seconds // 60
            seconds = total_seconds % 60
            time_str = f"{minutes}:{seconds:02d}"

            embed = MafiaMessages.get_ready_check_embed(ready_count, len(players))
            try:
                await msg.edit(embed=embed)
            except:
                pass

            if channel:
                not_ready = [pid for pid in players if not game.get('ready_status', {}).get(pid, False)]
                violations = [f"{TIME_EMOJI} ㆍ<@{pid}> — {MUTE_EMOJI}" for pid in not_ready]
                embed = MafiaMessages.get_violations_embed(violations, time_str)
                try:
                    async for old_msg in channel.history(limit=10):
                        if old_msg.author == guild.me and old_msg.embeds and old_msg.embeds[0].title == "Проверка готовности":
                            await old_msg.delete()
                            break
                    await channel.send(embed=embed)
                except:
                    pass

            if ready_count == len(players):
                break

        await self.finish_ready_check(guild, game, control_channel, msg, channel)

    async def finish_ready_check(self, guild, game, control_channel, msg, channel):
        players = game['players']
        ready_status = game.get('ready_status', {})
        not_ready = [pid for pid in players if not ready_status.get(pid, False)]

        ban_role = guild.get_role(BAN_ROLE_ID)
        for uid in not_ready:
            if uid in game['players']:
                game['players'].remove(uid)
            member = guild.get_member(uid)
            if member and ban_role:
                try:
                    await member.add_roles(ban_role, reason="Не принял готовность к игре")
                    embed = MafiaMessages.get_ban_embed("Не принял готовность к игре", 2)
                    await member.send(embed=embed)
                    asyncio.create_task(self.remove_role_after_delay(member, ban_role, 120))
                except Exception as e:
                    print(f"Не удалось выдать бан-роль {uid}: {e}")

        try:
            await msg.delete()
        except:
            pass

        if channel:
            async for old_msg in channel.history(limit=10):
                if old_msg.author == guild.me and old_msg.embeds and old_msg.embeds[0].title == "Проверка готовности":
                    await old_msg.delete()
                    break

        if not_ready:
            mentions = " ".join([f"<@{uid}>" for uid in not_ready])
            await control_channel.send(f"❌ Игроки {mentions} не приняли готовность и были исключены.")
        else:
            await control_channel.send("✅ Все игроки подтвердили готовность!")

        await self.update_ready_check(guild, game['channel_id'])

        if len(game['players']) != 10:
            await control_channel.send("⚠️ После проверки готовности осталось не 10 игроков. Запуск невозможен. Добавьте игроков или завершите игру вручную.")
        else:
            await control_channel.send(f"✅ В игре ровно {len(game['players'])} игроков. Ведущий может запустить игру через меню.")

    async def call_missing_players(self, interaction, game):
        voice_channel = await self.game_logic.get_voice_channel(interaction.guild, game)
        if not voice_channel:
            await interaction.followup.send("❌ Голосовой канал не найден.", ephemeral=True)
            return

        voice_channel_url = f"https://discord.com/channels/{interaction.guild.id}/{voice_channel.id}"

        members_in_voice = [member.id for member in voice_channel.members]
        missing = [pid for pid in game['players'] if pid not in members_in_voice]

        if not missing:
            await interaction.followup.send("✅ Все игроки уже в войсе!", ephemeral=True)
            return

        for pid in missing:
            user = interaction.guild.get_member(pid) or await self.bot.fetch_user(pid)
            if user:
                embed = discord.Embed(
                    title="🔊 Созыв в войс",
                    description=f"Ведущий созывает игроков. Зайди в голосовой канал {voice_channel.mention} в течение 30 секунд.",
                    color=discord.Color.orange()
                )
                view = JoinVoiceView(game, self, pid, voice_channel_url)
                await user.send(embed=embed, view=view)

        await interaction.followup.send("📩 Уведомления отправлены отсутствующим.", ephemeral=True)
        asyncio.create_task(self.voice_timer(interaction.guild, game, voice_channel, missing))

    async def voice_timer(self, guild, game, voice_channel, missing):
        await asyncio.sleep(30)
        members_in_voice = [member.id for member in voice_channel.members]
        still_missing = [pid for pid in missing if pid not in members_in_voice]

        if still_missing:
            for uid in still_missing:
                if uid in game['players']:
                    game['players'].remove(uid)
            control_channel = guild.get_channel(game['control_channel_id'])
            if control_channel:
                mentions = " ".join([f"<@{uid}>" for uid in still_missing])
                await control_channel.send(f"❌ Игроки {mentions} не зашли в войс и были исключены.")
                if len(game['players']) != 10:
                    await control_channel.send("⚠️ После созыва осталось не 10 игроков. Запуск невозможен. Добавьте игроков или завершите игру вручную.")
            await self.update_ready_check(guild, game['channel_id'])

    async def remove_role_after_delay(self, member, role, delay):
        await asyncio.sleep(delay)
        try:
            await member.remove_roles(role)
        except:
            pass

    # ---------- МЕТОДЫ МЕНЮ ВЕДУЩЕГО ----------
    async def show_host_menu(self, guild, game):
        control_channel = guild.get_channel(game['control_channel_id'])
        if not control_channel:
            return
        embed = discord.Embed(
            title="👑 Управление игрой",
            description="Выберите действие для управления игровым процессом.",
            color=discord.Color.blue()
        )
        view = HostMenuView(game, self)
        await control_channel.send(embed=embed, view=view)

    async def handle_foul(self, interaction, game):
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if not alive_members:
            await interaction.response.send_message("❌ Нет живых игроков.", ephemeral=True)
            return
        options = []
        for member in alive_members:
            options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        select = discord.ui.Select(placeholder="Выберите игрока", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может выдавать фол.", ephemeral=True)
                return
            member = select_interaction.guild.get_member(int(select.values[0]))
            if member:
                await self.give_foul(select_interaction, game, member)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для фола:", view=view, ephemeral=True)

    async def give_foul(self, interaction, game, member):
        if 'fouls' not in game:
            game['fouls'] = {}
        game['fouls'][member.id] = game['fouls'].get(member.id, 0) + 1
        await self.update_player_nick(interaction.guild, member, game)
        channel = interaction.guild.get_channel(game['channel_id'])
        if channel:
            embed = MafiaMessages.get_foul_embed(
                member.display_name,
                game['fouls'].get(member.id, 0),
                game.get('warnings', {}).get(member.id, 0),
                member.display_avatar.url
            )
            view = UndoView(game, self, member, 'foul')
            await channel.send(embed=embed, view=view)
        if game['fouls'].get(member.id, 0) >= 4:
            await self.remove_player_from_game(interaction.guild, game, member, "4 фола")
        await interaction.response.send_message(f"✅ Фол выдан {member.mention}", ephemeral=True)

    async def undo_foul(self, interaction, game, member):
        if 'fouls' not in game or game['fouls'].get(member.id, 0) == 0:
            await interaction.response.send_message("❌ У этого игрока нет фолов.", ephemeral=True)
            return
        game['fouls'][member.id] -= 1
        if game['fouls'][member.id] == 0:
            del game['fouls'][member.id]
        await self.update_player_nick(interaction.guild, member, game)
        await interaction.response.send_message(f"✅ Фол отменён для {member.mention}.", ephemeral=True)

    async def handle_undo_foul(self, interaction, game):
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if not alive_members:
            await interaction.response.send_message("❌ Нет живых игроков.", ephemeral=True)
            return
        options = []
        for member in alive_members:
            if game.get('fouls', {}).get(member.id, 0) > 0:
                options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        if not options:
            await interaction.response.send_message("❌ Нет игроков с фолами.", ephemeral=True)
            return
        select = discord.ui.Select(placeholder="Выберите игрока для отмены фола", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может отменять фол.", ephemeral=True)
                return
            member = select_interaction.guild.get_member(int(select.values[0]))
            if member:
                await self.undo_foul(select_interaction, game, member)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для отмены фола:", view=view, ephemeral=True)

    async def handle_warning(self, interaction, game):
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if not alive_members:
            await interaction.response.send_message("❌ Нет живых игроков.", ephemeral=True)
            return
        options = []
        for member in alive_members:
            options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        select = discord.ui.Select(placeholder="Выберите игрока", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может выдавать предупреждение.", ephemeral=True)
                return
            member = select_interaction.guild.get_member(int(select.values[0]))
            if member:
                await self.give_warning(select_interaction, game, member)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для предупреждения:", view=view, ephemeral=True)

    async def give_warning(self, interaction, game, member):
        if 'warnings' not in game:
            game['warnings'] = {}
        game['warnings'][member.id] = game['warnings'].get(member.id, 0) + 1
        await self.update_player_nick(interaction.guild, member, game)
        channel = interaction.guild.get_channel(game['channel_id'])
        if channel:
            embed = MafiaMessages.get_warning_embed(
                member.display_name,
                game.get('fouls', {}).get(member.id, 0),
                game['warnings'].get(member.id, 0),
                member.display_avatar.url
            )
            view = UndoView(game, self, member, 'warning')
            await channel.send(embed=embed, view=view)
        if game['warnings'].get(member.id, 0) >= 2:
            await self.remove_player_from_game(interaction.guild, game, member, "2 предупреждения")
        await interaction.response.send_message(f"✅ Предупреждение выдано {member.mention}", ephemeral=True)

    async def undo_warning(self, interaction, game, member):
        if 'warnings' not in game or game['warnings'].get(member.id, 0) == 0:
            await interaction.response.send_message("❌ У этого игрока нет предупреждений.", ephemeral=True)
            return
        game['warnings'][member.id] -= 1
        if game['warnings'][member.id] == 0:
            del game['warnings'][member.id]
        await self.update_player_nick(interaction.guild, member, game)
        await interaction.response.send_message(f"✅ Предупреждение отменено для {member.mention}.", ephemeral=True)

    async def handle_undo_warning(self, interaction, game):
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if not alive_members:
            await interaction.response.send_message("❌ Нет живых игроков.", ephemeral=True)
            return
        options = []
        for member in alive_members:
            if game.get('warnings', {}).get(member.id, 0) > 0:
                options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        if not options:
            await interaction.response.send_message("❌ Нет игроков с предупреждениями.", ephemeral=True)
            return
        select = discord.ui.Select(placeholder="Выберите игрока для отмены предупреждения", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может отменять предупреждение.", ephemeral=True)
                return
            member = select_interaction.guild.get_member(int(select.values[0]))
            if member:
                await self.undo_warning(select_interaction, game, member)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для отмены предупреждения:", view=view, ephemeral=True)

    async def update_player_nick(self, guild, member, game):
        fouls = game.get('fouls', {}).get(member.id, 0)
        warnings = game.get('warnings', {}).get(member.id, 0)
        number = member.display_name[:2] if member.display_name[:2].isdigit() else "??"
        new_nick = f"{number}[Ф: {fouls}/4][П: {warnings}/2]"
        try:
            await member.edit(nick=new_nick)
        except:
            pass

    async def remove_player_from_game(self, guild, game, member, reason):
        if member.id in game['alive']:
            game['alive'].remove(member.id)
        if member.id in game['players']:
            game['players'].remove(member.id)
        channel = guild.get_channel(game['channel_id'])
        if channel:
            await channel.send(f"❌ {member.mention} удалён из игры ({reason}).")
        await self.game_logic.check_game_end(guild, game)

    async def handle_vote(self, interaction, game):
        if self.game_logic.vote_ongoing:
            await interaction.response.send_message("❌ Голосование уже идёт.", ephemeral=True)
            return
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if len(alive_members) < 2:
            await interaction.response.send_message("❌ Недостаточно игроков для голосования (нужно минимум 2).", ephemeral=True)
            return
        options = []
        for member in alive_members:
            options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        select = discord.ui.Select(placeholder="Выберите кандидата для голосования", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может начать голосование.", ephemeral=True)
                return
            candidate_id = int(select.values[0])
            await self.launch_vote(select_interaction, game, candidate_id)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите кандидата для голосования:", view=view, ephemeral=True)

    async def launch_vote(self, interaction, game, candidate_id):
        self.game_logic.vote_ongoing = True
        candidate = interaction.guild.get_member(candidate_id)
        if not candidate:
            await interaction.followup.send("❌ Кандидат не найден.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(game['channel_id'])
        if channel:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
            embed = MafiaMessages.get_vote_embed(candidate.mention)
            view = VoteView(game, self, candidate_id)
            await channel.send(embed=embed, view=view)
            await asyncio.sleep(10)
            if game.get('end_called', False):
                return
            await self.finish_vote(interaction, game, candidate_id)

    async def finish_vote(self, interaction, game, candidate_id):
        self.game_logic.vote_ongoing = False
        channel = interaction.guild.get_channel(game['channel_id'])
        if channel:
            try:
                await channel.set_permissions(interaction.guild.default_role, send_messages=True)
            except:
                pass
            counts = game.get('vote_counts', {})
            total = sum(counts.values())
            if total == 0:
                await channel.send("❌ Никто не проголосовал.")
            else:
                max_votes = max(counts.values()) if counts else 0
                winners = [pid for pid, v in counts.items() if v == max_votes]
                if len(winners) == 1:
                    winner_id = winners[0]
                    winner = interaction.guild.get_member(winner_id)
                    if winner:
                        if winner_id in game['alive']:
                            game['alive'].remove(winner_id)
                        if winner_id in game['players']:
                            game['players'].remove(winner_id)
                        await channel.send(f"🗳️ **{winner.mention}** выгнан! Голосов: {max_votes}")
                        game['vote_log'].append(f"<@{winner_id}>")
                        game['logs'].append(f"Голосование выгнало <@{winner_id}>")
                        await self.game_logic.check_game_end(interaction.guild, game)
                else:
                    await channel.send("❌ Ничья, никто не выгнан.")
            game['vote_counts'] = {}

    async def handle_revive(self, interaction, game):
        alive_members = [interaction.guild.get_member(pid) for pid in game['alive'] if pid != game['creator_id']]
        if not alive_members:
            await interaction.response.send_message("❌ Нет живых игроков для поднятия.", ephemeral=True)
            return
        options = []
        for member in alive_members:
            options.append(discord.SelectOption(label=member.display_name, value=str(member.id)))
        select = discord.ui.Select(placeholder="Выберите игрока", options=options)
        async def select_callback(select_interaction):
            if select_interaction.user.id != game['creator_id']:
                await select_interaction.response.send_message("❌ Только ведущий может поднимать игроков.", ephemeral=True)
                return
            member = select_interaction.guild.get_member(int(select.values[0]))
            if member:
                modal = ReviveModal(game, self, member)
                await select_interaction.response.send_modal(modal)
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Выберите игрока для поднятия со стола:", view=view, ephemeral=True)

    async def handle_end_early(self, interaction, game):
        await interaction.response.defer(ephemeral=True)
        await self.game_logic.end_game(interaction.guild, game, "Игра завершена досрочно ведущим.", early=True)
        await interaction.followup.send("✅ Игра завершена.", ephemeral=True)

    # ---------- НОВАЯ КОМАНДА /w ----------
    @app_commands.command(name="w", description="Подмигнуть игроку (только для шерифа и дона)")
    async def wink(self, interaction: discord.Interaction, player: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("❌ Эту команду можно использовать только на сервере.", ephemeral=True)
            return

        user_id = interaction.user.id
        game = None
        for g in self.games.values():
            if user_id in g.get('players', set()) and g.get('started', False):
                game = g
                break

        if not game:
            await interaction.response.send_message("❌ Вы не находитесь в активной игре.", ephemeral=True)
            return

        if user_id not in game.get('alive', set()):
            await interaction.response.send_message("❌ Вы мертвы и не можете подмигивать.", ephemeral=True)
            return

        role = game['roles'].get(user_id)
        if role not in ['шериф', 'дон']:
            await interaction.response.send_message("❌ Только шериф и дон могут подмигивать.", ephemeral=True)
            return

        target_id = player.id
        if target_id == user_id:
            await interaction.response.send_message("❌ Нельзя подмигивать самому себе.", ephemeral=True)
            return
        if target_id not in game.get('alive', set()):
            await interaction.response.send_message("❌ Этот игрок мёртв или не в игре.", ephemeral=True)
            return

        target_user = interaction.guild.get_member(target_id) or await self.bot.fetch_user(target_id)
        if not target_user:
            await interaction.response.send_message("❌ Не удалось найти получателя.", ephemeral=True)
            return

        try:
            embed = MafiaMessages.get_wink_embed(f"<@{user_id}>")
            await target_user.send(embed=embed)
            await interaction.response.send_message(f"✅ Вы подмигнули {player.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Не удалось отправить сообщение игроку (у него закрыты ЛС).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

    # ---------- КОМАНДЫ ----------
    @app_commands.command(name="mafia_ban", description="Выдать бан-роль игроку")
    async def mafia_ban(self, interaction: discord.Interaction, member: discord.Member, time: int, reason: str):
        allowed_role = interaction.guild.get_role(ALLOWED_ROLE_ID)
        if not allowed_role or allowed_role not in interaction.user.roles:
            await interaction.response.send_message("❌ У вас нет прав для использования этой команды.", ephemeral=True)
            return
        if time < 1:
            await interaction.response.send_message("❌ Время должно быть больше 0 минут.", ephemeral=True)
            return
        ban_role = interaction.guild.get_role(BAN_ROLE_ID)
        if not ban_role:
            await interaction.response.send_message("❌ Роль 'мафия бан' не найдена.", ephemeral=True)
            return
        if ban_role in member.roles:
            await interaction.response.send_message(f"❌ У {member.mention} уже есть роль 'мафия бан'.", ephemeral=True)
            return
        try:
            await member.add_roles(ban_role, reason=f"Выдана {interaction.user.name}: {reason}")
            embed = MafiaMessages.get_ban_embed(reason, time)
            await member.send(embed=embed)
            asyncio.create_task(self.remove_role_after_delay(member, ban_role, time*60))
            await interaction.response.send_message(f"✅ Роль 'мафия бан' выдана {member.mention} на {time} минут.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

    @app_commands.command(name="mafia_top", description="Топ-10 игроков по рейтингу")
    async def mafia_top(self, interaction: discord.Interaction):
        top = get_top_players(10)
        if not top:
            embed = discord.Embed(
                title="📊 ТОП-10 пользователей по рейтингу",
                description="Пока ни у кого нет очков. Сыграйте в мафию, чтобы заработать!",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
            return

        description = ""
        for i, (user_id, rating) in enumerate(top, start=1):
            user = interaction.guild.get_member(user_id) or await self.bot.fetch_user(user_id)
            name = user.mention if user else f"<@{user_id}>"
            description += f"{i}) {name} — **{rating}** оч.\n"

        embed = discord.Embed(
            title="📊 ТОП-10 пользователей по рейтингу",
            description=description,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Как получить очки? Останьтесь живым в игре: 1 минута = 5 очков.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mafia_create", description="Создать игру Мафия")
    @app_commands.choices(режим=[
        app_commands.Choice(name="Городская", value="Городская"),
        app_commands.Choice(name="Классическая", value="Классическая")
    ])
    async def mafia_create(self, interaction: discord.Interaction, режим: str):
        await interaction.response.defer(ephemeral=True)

        if not await check_allowed_role(interaction):
            await interaction.followup.send("❌ У вас нет прав для использования этой команды.")
            return

        guild = interaction.guild
        user = interaction.user

        parent_category = guild.get_channel(PARENT_CATEGORY_ID)
        if parent_category is None:
            await interaction.followup.send("❌ Родительская категория не найдена. Проверьте ID.")
            return
        if not isinstance(parent_category, discord.CategoryChannel):
            await interaction.followup.send("❌ Указанный ID не является категорией.")
            return

        category_name = f"Мафия: {режим} ㆍ {user.display_name}"
        try:
            new_category = await guild.create_category(
                category_name,
                position=parent_category.position + 1
            )
            await new_category.move(after=parent_category)
        except Exception as e:
            await interaction.followup.send(f"❌ Не удалось создать категорию: {e}")
            return

        try:
            text_channel = await new_category.create_text_channel(
                "💬ㆍзапись",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(send_messages=False, view_channel=True),
                    user: discord.PermissionOverwrite(send_messages=True, view_channel=True),
                    self.bot.user: discord.PermissionOverwrite(send_messages=True, view_channel=True)
                }
            )
            voice_waiting = await new_category.create_voice_channel("🔊ㆍОжидание")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                self.bot.user: discord.PermissionOverwrite(view_channel=True)
            }
            control_channel = await new_category.create_text_channel("Управление", overwrites=overwrites)

            max_players = 10
            game_id = text_channel.id
            self.games[game_id] = {
                'game_id': game_id,
                'creator_id': user.id,
                'players': set(),
                'mode': режим,
                'message_id': None,
                'max_players': max_players,
                'started': False,
                'waiting_voice_id': voice_waiting.id,
                'announce_message_id': None,
                'control_channel_id': control_channel.id,
                'ready_check_message_id': None,
                'category_id': new_category.id,
                'channel_id': text_channel.id,
                'ready_status': {},
                'ready_message_id': None,
                'guild_id': guild.id,
            }

            embed = self.build_registration_embed(self.games[game_id], guild)
            reg_view = RegistrationView(channel_id=text_channel.id, cog=self)
            msg = await text_channel.send(embed=embed, view=reg_view)
            self.games[game_id]['message_id'] = msg.id

            control_embed = discord.Embed(
                title="👑 Управление ивентом",
                description="Для управления используйте меню ниже.",
                color=discord.Color.green()
            )
            control_embed.add_field(name="Ведущий", value=user.mention, inline=True)
            control_embed.set_footer(text="Выберите действие в меню")

            control_view = ControlView(
                creator_id=user.id,
                category_id=new_category.id,
                channel_id=text_channel.id,
                cog=self
            )
            await control_channel.send(
                content=user.mention,
                embed=control_embed,
                view=control_view
            )

            await self.update_ready_check(guild, text_channel.id)

            await interaction.followup.send(
                f"✅ Игра «Мафия: {режим}» зарегистрирована!\n"
                f"Чтобы управлять игрой, перейди в {control_channel.mention}"
            )

        except Exception as e:
            await new_category.delete()
            await interaction.followup.send(f"❌ Не удалось создать каналы: {e}")
            return

# ---------- ОБЯЗАТЕЛЬНАЯ ФУНКЦИЯ SETUP ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(MafiaSetupCog(bot))