import discord
import random
import asyncio
import time
from collections import Counter
from database import update_role_stats, update_coins, update_rating, update_player_role, update_first_game
from .mafia_messages import MafiaMessages
from config import RESULTS_CHANNEL_ID, BAN_ROLE_ID, AFTER_GAME_VOICE_CHANNEL_ID

class MafiaGame:
    def __init__(self, bot, host_cog):
        self.bot = bot
        self.host_cog = host_cog
        self.role_confirmations = {}
        self.vote_ongoing = False
        self.vote_results = {}
        self.phase = 'night'

    def assign_roles(self, players):
        count = len(players)
        if count != 10:
            raise ValueError("Для игры нужно ровно 10 игроков")
        roles_pool = ['мирный'] * 5 + ['шериф', 'доктор', 'мафия', 'мафия', 'дон']
        random.shuffle(roles_pool)
        assigned = roles_pool[:count]
        return {pid: assigned[i] for i, pid in enumerate(players)}

    async def send_roles_to_players(self, guild, game):
        for pid, role in game['roles'].items():
            user = guild.get_member(pid) or await self.bot.fetch_user(pid)
            if not user:
                continue
            embed = MafiaMessages.get_role_embed(role)
            if role == 'мирный':
                await user.send(embed=embed)
            else:
                view = ConfirmRoleView(game, self, pid, role, user)
                await user.send(embed=embed, view=view)

    async def create_role_channel(self, guild, category, user, role, game):
        channel_name = f"управление-{role}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_member(game['creator_id']): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        try:
            channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        except Exception as e:
            print(f"Ошибка создания канала для {user.name}: {e}")
            return None

        if self.phase == 'day':
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            overwrites[user] = discord.PermissionOverwrite(view_channel=False)
        else:
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            overwrites[user] = discord.PermissionOverwrite(view_channel=True)

        embed = discord.Embed(title=f"🎭 Твоя роль: {role}", description="Выбери действие в меню ниже.", color=discord.Color.blue())
        view = None
        if role == 'шериф':
            embed.add_field(name="🔍 Способность", value="Каждую ночь ты можешь проверить одного игрока.", inline=False)
            view = SheriffView(game, self, channel.id, user.id)
        elif role == 'доктор':
            embed.add_field(name="💊 Способность", value="Каждую ночь ты можешь вылечить одного игрока (один раз себя).", inline=False)
            view = DoctorView(game, self, channel.id, user.id)
        elif role == 'дон':
            embed.add_field(name="🗡️ Способности", value="Ты можешь проверять роли (как шериф) и голосовать за убийство.", inline=False)
            view = DonView(game, self, channel.id, user.id)

        msg = await channel.send(embed=embed, view=view)
        if role in ['шериф', 'доктор', 'дон']:
            if 'role_messages' not in game:
                game['role_messages'] = {}
            game['role_messages'][user.id] = msg.id

        return channel

    async def create_mafia_channel(self, guild, category, game):
        mafia_ids = [pid for pid, role in game['roles'].items() if role in ['мафия', 'дон']]
        if not mafia_ids:
            return None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_member(game['creator_id']): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        for uid in mafia_ids:
            member = guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        if self.phase == 'day':
            for uid in mafia_ids:
                member = guild.get_member(uid)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(view_channel=False)

        try:
            channel = await category.create_text_channel("🔪ㆍмафия-чат", overwrites=overwrites)
        except Exception as e:
            print(f"Ошибка создания канала мафии: {e}")
            return None

        embed = discord.Embed(title="🔪 Мафия", description="Обсуждайте планы. Голосование за убийство проводится ведущим днём.", color=discord.Color.red())
        await channel.send(embed=embed)
        return channel

    async def start_game(self, interaction, game):
        guild = interaction.guild
        game['original_nicks'] = {}
        for member in guild.members:
            if member.id in game['players'] or member.id == game['creator_id']:
                game['original_nicks'][member.id] = member.display_name

        game['action_logs'] = {}
        game['kill_log'] = []
        game['vote_log'] = []
        game['logs'] = []
        game['early_end'] = False
        game['end_called'] = False
        game['role_messages'] = {}
        game['used_abilities'] = {}
        game['tasks'] = []

        try:
            roles = self.assign_roles(list(game['players']))
            game['roles'] = roles
            game['alive'] = set(game['players'])
            game['phase'] = 'night'
            self.phase = 'night'
            game['started'] = True
            game['role_channels'] = {}
            game['guild_id'] = interaction.guild.id
            game['start_time'] = int(time.time())
            self.role_confirmations[game['game_id']] = {pid: False for pid in game['players'] if game['roles'][pid] != 'мирный'}
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка назначения ролей: {e}", ephemeral=True)
            return

        creator = interaction.user
        try:
            await creator.edit(nick="!Ведущий")
        except:
            pass
        sorted_players = sorted(game['players'])
        for idx, pid in enumerate(sorted_players, start=1):
            member = guild.get_member(pid)
            if member:
                try:
                    await member.edit(nick=f"{idx:02d}")
                except:
                    pass

        await self.send_roles_to_players(guild, game)

        category = guild.get_channel(game['category_id'])
        if category is None:
            await interaction.followup.send("❌ Категория не найдена.", ephemeral=True)
            return

        waiting_id = game.get('waiting_voice_id')
        if waiting_id:
            waiting_channel = guild.get_channel(waiting_id)
            if waiting_channel:
                try:
                    await waiting_channel.edit(
                        name=f"🔊ㆍМафия | {game['mode']}",
                        user_limit=len(game['players'])
                    )
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=False)
                    }
                    creator_obj = guild.get_member(game['creator_id'])
                    if creator_obj:
                        overwrites[creator_obj] = discord.PermissionOverwrite(connect=True, view_channel=True)
                    overwrites[guild.me] = discord.PermissionOverwrite(connect=True, view_channel=True)
                    for uid in game['players']:
                        member = guild.get_member(uid)
                        if member:
                            overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)
                    await waiting_channel.edit(overwrites=overwrites)
                except Exception as e:
                    await interaction.followup.send(f"❌ Не удалось обновить голосовой канал: {e}", ephemeral=True)
                    return
            game['waiting_voice_id'] = None

        await self.create_mafia_channel(guild, category, game)

        channel = guild.get_channel(game['channel_id'])
        if channel:
            try:
                await channel.edit(name="💬ㆍчат")
                await channel.set_permissions(guild.default_role, send_messages=False)
            except:
                pass

        if channel:
            try:
                msg = await channel.fetch_message(game['message_id'])
                await msg.delete()
            except:
                pass
            embed = MafiaMessages.get_game_start_embed(f"<@{game['creator_id']}>")
            await channel.send(embed=embed)

        await self.host_cog.remove_ready_check(guild, game['channel_id'])

        await interaction.followup.send(f"✅ Игра «Мафия» запущена! Роли разосланы.", ephemeral=True)

        await self.host_cog.show_host_menu(guild, game)

        task = asyncio.create_task(self.wait_for_confirmations(guild, game))
        game['tasks'].append(task)

    async def wait_for_confirmations(self, guild, game):
        await asyncio.sleep(30)

        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        all_confirmed = all(self.role_confirmations[game['game_id']].values())
        if not all_confirmed:
            ban_role = guild.get_role(BAN_ROLE_ID)
            for pid, confirmed in self.role_confirmations[game['game_id']].items():
                if not confirmed:
                    if pid in game['players']:
                        game['players'].remove(pid)
                    if pid in game['alive']:
                        game['alive'].remove(pid)
                    member = guild.get_member(pid)
                    if member and ban_role:
                        try:
                            await member.add_roles(ban_role, reason="Не подтвердил роль")
                            embed = MafiaMessages.get_ban_embed("Не подтвердил роль вовремя", 2)
                            await member.send(embed=embed)
                            asyncio.create_task(self.host_cog.remove_role_after_delay(member, ban_role, 120))
                        except:
                            pass
            game['alive'] = set(game['players'])
            await self.host_cog.update_ready_check(guild, game['channel_id'])

        if not game.get('end_called', False) and game.get('game_id') in self.host_cog.games:
            task = asyncio.create_task(self.start_night_phase(guild, game))
            game['tasks'].append(task)

    async def start_night_phase(self, guild, game):
        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        self.phase = 'night'
        game['phase'] = 'night'

        game['used_abilities'] = {pid: False for pid in game['alive']}

        await self.show_role_channels(guild, game, visible=True)

        channel = guild.get_channel(game['channel_id'])
        if channel:
            try:
                await channel.set_permissions(guild.default_role, send_messages=False)
            except:
                pass
            embed = MafiaMessages.get_night_embed()
            await channel.send(embed=embed)

        if 'role_messages' in game:
            for pid, msg_id in game['role_messages'].items():
                if pid not in game['alive']:
                    continue
                role = game['roles'][pid]
                if role not in ['шериф', 'доктор', 'дон']:
                    continue
                category = guild.get_channel(game['category_id'])
                if not category:
                    continue
                for ch in category.channels:
                    if ch.name == f"управление-{role}":
                        try:
                            msg = await ch.fetch_message(msg_id)
                            if role == 'шериф':
                                view = SheriffView(game, self, ch.id, pid)
                            elif role == 'доктор':
                                view = DoctorView(game, self, ch.id, pid)
                            elif role == 'дон':
                                view = DonView(game, self, ch.id, pid)
                            else:
                                continue
                            await msg.edit(view=view)
                        except:
                            pass

        task = asyncio.create_task(self.night_timer(guild, game))
        game['tasks'].append(task)

    async def night_timer(self, guild, game):
        await asyncio.sleep(30)

        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        await self.resolve_night_actions(guild, game)

    async def start_day_phase(self, guild, game):
        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        self.phase = 'day'
        game['phase'] = 'day'
        await self.show_role_channels(guild, game, visible=False)

        channel = guild.get_channel(game['channel_id'])
        if channel:
            try:
                await channel.set_permissions(guild.default_role, send_messages=True)
            except:
                pass
            embed = MafiaMessages.get_day_embed()
            await channel.send(embed=embed)

        await self.check_game_end(guild, game)

    async def show_role_channels(self, guild, game, visible: bool):
        """Исправленный метод – теперь корректно обновляет права доступа."""
        category = guild.get_channel(game['category_id'])
        if not category:
            return
        for channel in category.channels:
            if channel.name.startswith(('управление-шериф', 'управление-доктор', 'управление-дон', '🔪ㆍмафия-чат')):
                for target, overwrite in channel.overwrites.items():
                    if isinstance(target, discord.Member):
                        try:
                            await channel.set_permissions(target, view_channel=visible)
                        except:
                            pass

    async def resolve_night_actions(self, guild, game):
        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        actions = game.get('night_actions', {})
        kill_target = actions.get('mafia_kill')
        heal_target = actions.get('doctor_heal')

        # Исправленная логика – лечение предотвращает убийство
        if kill_target and kill_target in game['alive']:
            if heal_target == kill_target:
                game['logs'].append(f"Доктор вылечил {kill_target}, убийство отменено")
            else:
                game['alive'].remove(kill_target)
                await self.send_death_notification(guild, game, kill_target)

                mafia_alive = [pid for pid, role in game['roles'].items() if role in ['мафия', 'дон'] and pid in game['alive']]
                killer_id = random.choice(mafia_alive) if mafia_alive else None
                if killer_id:
                    game['kill_log'].append({'killer_id': killer_id, 'victim_id': kill_target})
                    game['logs'].append(f"{killer_id} убил {kill_target}")
                    if killer_id not in game['action_logs']:
                        game['action_logs'][killer_id] = {'role': game['roles'][killer_id], 'actions': []}
                    game['action_logs'][killer_id]['actions'].append({'type': 'kill', 'target': kill_target})
                else:
                    game['kill_log'].append({'killer_id': None, 'victim_id': kill_target})
                    game['logs'].append(f"Мафия убила {kill_target}")

        if heal_target:
            if heal_target not in game['action_logs']:
                game['action_logs'][heal_target] = {'role': 'доктор', 'actions': []}
            game['action_logs'][heal_target]['actions'].append({'type': 'heal', 'target': heal_target})
            game['logs'].append(f"Доктор {heal_target} вылечил игрока")

        game['night_actions'] = {'mafia_votes': {}, 'mafia_kill': None, 'doctor_heal': None, 'sheriff_check': None, 'don_check': None}
        await self.start_day_phase(guild, game)

    async def send_death_notification(self, guild, game, killed_id):
        channel = guild.get_channel(game['channel_id'])
        if channel:
            embed = MafiaMessages.get_death_notification(f"<@{killed_id}>")
            await channel.send(embed=embed)

    async def check_game_end(self, guild, game):
        if game.get('end_called', False) or game.get('early_end', False):
            return
        if game.get('game_id') not in self.host_cog.games:
            return

        alive_roles = [game['roles'][pid] for pid in game['alive'] if pid in game['roles']]
        black = [r for r in alive_roles if r in ['мафия', 'дон']]
        red = [r for r in alive_roles if r in ['мирный', 'шериф', 'доктор']]
        if len(black) == 0:
            await self.end_game(guild, game, "Мирные жители победили!")
            return
        if len(red) <= len(black):
            await self.end_game(guild, game, "Мафия победила!")
            return

    async def end_game(self, guild, game, message, early=False):
        if game.get('end_called', False):
            return
        game['end_called'] = True
        game['early_end'] = early

        for task in game.get('tasks', []):
            task.cancel()
        game['tasks'] = []

        for uid, nick in game.get('original_nicks', {}).items():
            member = guild.get_member(uid)
            if member:
                try:
                    await member.edit(nick=nick)
                except:
                    pass

        if early:
            await self._send_result_and_cleanup(guild, game, message, early=True)
            return

        alive_roles = [game['roles'][pid] for pid in game['alive'] if pid in game['roles']]
        black = [r for r in alive_roles if r in ['мафия', 'дон']]
        red = [r for r in alive_roles if r in ['мирный', 'шериф', 'доктор']]
        red_won = (len(black) == 0)
        black_won = (len(red) <= len(black))

        for pid, role in game['roles'].items():
            win = False
            if red_won and role in ['мирный', 'шериф', 'доктор']:
                win = True
            elif black_won and role in ['мафия', 'дон']:
                win = True
            update_role_stats(pid, role, win=win)
            update_coins(pid, 200 if win else 100)
            update_rating(pid, 1.0 if win else 0.0)
            update_player_role(pid)
            update_first_game(pid)

        start_time = game.get('start_time')
        if start_time:
            elapsed_seconds = int(time.time()) - start_time
            minutes = elapsed_seconds // 60
            total_points = minutes * 5
            if total_points > 0:
                for pid in game['alive']:
                    update_rating(pid, total_points)

        best_player = None
        best_score = -1
        for pid, data in game.get('action_logs', {}).items():
            role = data['role']
            actions = data['actions']
            if role in ['шериф', 'дон']:
                hits = sum(1 for a in actions if a['type'] == 'check' and a['result'] == '⚫ Чёрный')
                total = len([a for a in actions if a['type'] == 'check'])
                score = hits * 2
                if score > best_score:
                    best_score = score
                    best_player = (pid, {
                        'hits': hits,
                        'total': total,
                        'targets': [a['target'] for a in actions if a['type'] == 'check']
                    })
            elif role == 'доктор':
                total = len([a for a in actions if a['type'] == 'heal'])
                score = total
                if score > best_score:
                    best_score = score
                    best_player = (pid, {
                        'hits': 0,
                        'total': total,
                        'targets': [a['target'] for a in actions if a['type'] == 'heal']
                    })
            elif role == 'мафия':
                kills = [a for a in actions if a['type'] == 'kill']
                total = len(kills)
                score = total * 2
                if score > best_score:
                    best_score = score
                    best_player = (pid, {
                        'hits': total,
                        'total': total,
                        'targets': [a['target'] for a in kills]
                    })
        if best_score >= 0:
            game['best_player'] = best_player

        await self._send_result_and_cleanup(guild, game, message, early=False)

    async def _send_result_and_cleanup(self, guild, game, message, early):
        channel = guild.get_channel(game['channel_id'])
        if channel:
            try:
                embed = MafiaMessages.get_result_embed(game, guild)
                await channel.send(embed=embed)
                await channel.send(f"🏁 Игра окончена! {message}")
            except discord.NotFound:
                pass

        results_channel = guild.get_channel(RESULTS_CHANNEL_ID)
        if results_channel:
            try:
                embed = MafiaMessages.get_result_embed(game, guild)
                await results_channel.send(embed=embed)
            except discord.NotFound:
                pass

        # Перемещение всех игроков в финальный голосовой канал
        if AFTER_GAME_VOICE_CHANNEL_ID:
            after_channel = guild.get_channel(AFTER_GAME_VOICE_CHANNEL_ID)
            if after_channel and isinstance(after_channel, discord.VoiceChannel):
                for pid in game.get('players', []):
                    member = guild.get_member(pid)
                    if member and member.voice and member.voice.channel:
                        try:
                            await member.move_to(after_channel)
                        except:
                            pass

        category = guild.get_channel(game['category_id'])
        if category:
            for ch in category.channels:
                try:
                    await ch.delete()
                except:
                    pass
            try:
                await category.delete()
            except:
                pass

        if game['game_id'] in self.host_cog.games:
            del self.host_cog.games[game['game_id']]

    async def get_voice_channel(self, guild, game):
        waiting_id = game.get('waiting_voice_id')
        if waiting_id:
            channel = guild.get_channel(waiting_id)
            if channel and isinstance(channel, discord.VoiceChannel):
                return channel
        category = guild.get_channel(game['category_id'])
        if category:
            for ch in category.channels:
                if isinstance(ch, discord.VoiceChannel) and ("Мафия" in ch.name or "Ожидание" in ch.name):
                    return ch
        return None

    async def move_to_voice(self, guild, user, game):
        voice_channel = await self.get_voice_channel(guild, game)
        if not voice_channel:
            return False
        try:
            await user.move_to(voice_channel)
            return True
        except Exception as e:
            print(f"Ошибка перемещения {user.name}: {e}")
            return False


# ---------- КНОПКА ПОДТВЕРЖДЕНИЯ РОЛИ ----------
class ConfirmRoleView(discord.ui.View):
    def __init__(self, game, mafia_game, pid, role, user):
        super().__init__(timeout=None)
        self.game = game
        self.mafia_game = mafia_game
        self.pid = pid
        self.role = role
        self.user = user

    @discord.ui.button(label="✅ Подтвердить роль", style=discord.ButtonStyle.success, custom_id="confirm_role")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.pid:
            await interaction.response.send_message("❌ Это не твоя роль!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if self.game['game_id'] not in self.mafia_game.role_confirmations:
            self.mafia_game.role_confirmations[self.game['game_id']] = {}
        self.mafia_game.role_confirmations[self.game['game_id']][self.pid] = True

        guild = self.mafia_game.bot.get_guild(self.game['guild_id'])
        if not guild:
            await interaction.followup.send("❌ Сервер не найден.", ephemeral=True)
            return

        if self.role in ['шериф', 'доктор', 'дон']:
            category = guild.get_channel(self.game['category_id'])
            if category:
                channel = await self.mafia_game.create_role_channel(
                    guild, category, self.user, self.role, self.game
                )
                if channel:
                    await interaction.followup.send(f"✅ Ты подтвердил роль! Канал управления создан: {channel.mention}", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Не удалось создать канал управления.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Категория не найдена.", ephemeral=True)
        else:
            await interaction.followup.send("✅ Ты подтвердил роль! Ты получил доступ к каналу мафии.", ephemeral=True)

        control_channel = guild.get_channel(self.game['control_channel_id'])
        if control_channel:
            embed = MafiaMessages.get_confirm_role_embed(self.user.mention, self.role)
            await control_channel.send(embed=embed)


# ---------- КНОПКИ ДЛЯ РОЛЕЙ ----------
class PlayerSelect(discord.ui.Select):
    def __init__(self, game, mafia_game, channel_id, action_type, current_user_id):
        self.game = game
        self.mafia_game = mafia_game
        self.channel_id = channel_id
        self.action_type = action_type
        self.current_user_id = current_user_id

        alive = [uid for uid in game['alive'] if uid != current_user_id]
        if action_type == 'doctor' and not game.get('doctor_self_heal_used', False):
            alive.append(current_user_id)

        options = []
        for uid in alive:
            user = mafia_game.bot.get_user(uid)
            name = user.name if user else f"ID {uid}"
            options.append(discord.SelectOption(label=name, value=str(uid)))
        super().__init__(placeholder="Выберите игрока", options=options)

    async def callback(self, interaction: discord.Interaction):
        target = int(self.values[0])
        user_id = interaction.user.id
        role = self.game['roles'].get(user_id)

        if role in ['шериф', 'доктор']:
            if self.game.get('used_abilities', {}).get(user_id, False):
                await interaction.response.send_message("❌ Ты уже использовал способность в эту ночь!", ephemeral=True)
                return

        if self.action_type == 'sheriff':
            target_role = self.game['roles'][target]
            if target_role in ['мирный', 'доктор']:
                color = "🔴 Красный"
            elif target_role in ['мафия', 'дон']:
                color = "⚫ Чёрный"
            else:
                color = "❓ Неизвестно"
            await interaction.response.send_message(f"🔍 Роль игрока: **{color}**", ephemeral=True)
            self.game['night_actions']['sheriff_check'] = target
            if target not in self.game['action_logs']:
                self.game['action_logs'][target] = {'role': 'шериф', 'actions': []}
            self.game['action_logs'][target]['actions'].append({'type': 'check', 'target': target, 'result': color})
            self.game['logs'].append(f"Шериф {interaction.user.display_name} проверил {target}: {color}")

        elif self.action_type == 'doctor':
            if target == interaction.user.id:
                self.game['doctor_self_heal_used'] = True
            self.game['night_actions']['doctor_heal'] = target
            await interaction.response.send_message(f"💊 Ты вылечил игрока <@{target}>", ephemeral=True)
            if target not in self.game['action_logs']:
                self.game['action_logs'][target] = {'role': 'доктор', 'actions': []}
            self.game['action_logs'][target]['actions'].append({'type': 'heal', 'target': target})
            self.game['logs'].append(f"Доктор {interaction.user.display_name} вылечил {target}")

        elif self.action_type == 'don':
            target_role = self.game['roles'][target]
            if target_role in ['мирный', 'доктор']:
                color = "🔴 Красный"
            elif target_role in ['мафия', 'дон']:
                color = "⚫ Чёрный"
            else:
                color = "❓ Неизвестно"
            await interaction.response.send_message(f"🔍 Роль игрока: **{color}**", ephemeral=True)
            self.game['night_actions']['don_check'] = target
            if target not in self.game['action_logs']:
                self.game['action_logs'][target] = {'role': 'дон', 'actions': []}
            self.game['action_logs'][target]['actions'].append({'type': 'check', 'target': target, 'result': color})
            self.game['logs'].append(f"Дон {interaction.user.display_name} проверил {target}: {color}")

        if role in ['шериф', 'доктор']:
            self.game['used_abilities'][user_id] = True
            msg_id = self.game.get('role_messages', {}).get(user_id)
            if msg_id:
                guild = interaction.guild
                channel = guild.get_channel(self.channel_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(msg_id)
                        await msg.edit(view=None)
                    except:
                        pass

class SheriffView(discord.ui.View):
    def __init__(self, game, mafia_game, channel_id, user_id):
        super().__init__(timeout=None)
        self.add_item(PlayerSelect(game, mafia_game, channel_id, 'sheriff', user_id))

class DoctorView(discord.ui.View):
    def __init__(self, game, mafia_game, channel_id, user_id):
        super().__init__(timeout=None)
        self.add_item(PlayerSelect(game, mafia_game, channel_id, 'doctor', user_id))

class DonView(discord.ui.View):
    def __init__(self, game, mafia_game, channel_id, user_id):
        super().__init__(timeout=None)
        self.add_item(PlayerSelect(game, mafia_game, channel_id, 'don', user_id))


# ---------- КНОПКИ ГОЛОСОВАНИЯ МАФИИ ----------
class MafiaVoteSelect(discord.ui.Select):
    def __init__(self, game, mafia_game, channel_id):
        self.game = game
        self.mafia_game = mafia_game
        self.channel_id = channel_id
        options = []
        for uid in game['alive']:
            if uid != game.get('current_user_id'):
                user = mafia_game.bot.get_user(uid)
                name = user.name if user else f"ID {uid}"
                options.append(discord.SelectOption(label=name, value=str(uid)))
        super().__init__(placeholder="Выберите жертву", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in [pid for pid, role in self.game['roles'].items() if role in ['мафия', 'дон']]:
            await interaction.response.send_message("❌ Ты не мафия!", ephemeral=True)
            return
        target = int(self.values[0])
        self.game['night_actions']['mafia_votes'][interaction.user.id] = target
        await interaction.response.send_message(f"🗳️ Ты проголосовал за игрока <@{target}>", ephemeral=True)
        mafia_ids = [pid for pid, role in self.game['roles'].items() if role in ['мафия', 'дон'] and pid in self.game['alive']]
        if all(pid in self.game['night_actions']['mafia_votes'] for pid in mafia_ids):
            votes = list(self.game['night_actions']['mafia_votes'].values())
            if votes:
                counter = Counter(votes)
                max_count = max(counter.values())
                candidates = [k for k, v in counter.items() if v == max_count]
                if len(candidates) == 1:
                    self.game['night_actions']['mafia_kill'] = candidates[0]
                else:
                    self.game['night_actions']['mafia_kill'] = None

class MafiaVoteView(discord.ui.View):
    def __init__(self, game, mafia_game, channel_id):
        super().__init__(timeout=None)
        self.add_item(MafiaVoteSelect(game, mafia_game, channel_id))