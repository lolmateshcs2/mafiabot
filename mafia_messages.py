import discord
from datetime import datetime
import time
from config import NIGHT_IMAGE_URL, DAY_IMAGE_URL, VOTE_IMAGE_URL

class MafiaMessages:
    """Все шаблоны сообщений бота."""

    @staticmethod
    def get_night_embed() -> discord.Embed:
        embed = discord.Embed(
            title="# НОЧЬ",
            description="## 30 секунд на знакомство с мафией",
            color=discord.Color.dark_blue()
        )
        if NIGHT_IMAGE_URL:
            embed.set_image(url=NIGHT_IMAGE_URL)
        return embed

    @staticmethod
    def get_day_embed() -> discord.Embed:
        embed = discord.Embed(
            title="# УТРО",
            description="## Солнце выглядывает, город просыпается...",
            color=discord.Color.gold()
        )
        if DAY_IMAGE_URL:
            embed.set_image(url=DAY_IMAGE_URL)
        return embed

    @staticmethod
    def get_vote_embed(candidate_mention: str) -> discord.Embed:
        embed = discord.Embed(
            title="# ГОЛОСОВАНИЕ",
            description=f"## Голосование за {candidate_mention}",
            color=discord.Color.blue()
        )
        if VOTE_IMAGE_URL:
            embed.set_image(url=VOTE_IMAGE_URL)
        return embed

    @staticmethod
    def get_role_embed(role: str) -> discord.Embed:
        embed = discord.Embed(
            title="🎭 Твоя роль",
            description=f"Ты **{role}**!",
            color=discord.Color.green()
        )
        if role == 'мирный':
            embed.add_field(name="🛡️ Задача", value="Выжить и помочь найти мафию.", inline=False)
        else:
            embed.add_field(name="📌 Действие", value="Нажми кнопку ниже, чтобы подтвердить роль и получить доступ к управлению.", inline=False)
        return embed

    @staticmethod
    def get_death_notification(killed_mention: str) -> discord.Embed:
        return discord.Embed(
            title="💀 Смерть",
            description=f"Игрок {killed_mention} убит этой ночью!",
            color=discord.Color.red()
        )

    @staticmethod
    def get_game_start_embed(creator_mention: str) -> discord.Embed:
        return discord.Embed(
            title="🚀 Игра началась!",
            description=f"Ведущий: {creator_mention}\nРоли разосланы в ЛС. Подтвердите роль, чтобы получить доступ к управлению.",
            color=discord.Color.green()
        )

    @staticmethod
    def get_ban_embed(reason: str, duration: int) -> discord.Embed:
        embed = discord.Embed(
            title="⛔ Мафия бан",
            description=f"Вы получили бан-роль. Причина: {reason}",
            color=discord.Color.red()
        )
        embed.add_field(name="Время", value=f"{duration} минут", inline=False)
        embed.set_footer(text="Роль будет снята автоматически через указанное время.")
        return embed

    @staticmethod
    def get_wink_embed(sender_mention: str) -> discord.Embed:
        return discord.Embed(
            title="👀 Вам подмигнули!",
            description=f"Игрок {sender_mention} подмигнул(а) вам.",
            color=discord.Color.gold()
        )

    @staticmethod
    def get_ready_check_embed(ready_count: int, total: int) -> discord.Embed:
        embed = discord.Embed(
            title="⏳ Проверка готовности",
            description="Ожидаем подтверждения от игроков...",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ Приняли", value=f"{ready_count}/{total}", inline=False)
        if ready_count == total:
            embed.add_field(name="🎉 Все готовы!", value="Ведущий может запускать игру.", inline=False)
        embed.set_footer(text="Игра не начнётся автоматически. Ведущий запустит её вручную.")
        return embed

    @staticmethod
    def get_violations_embed(violations: list, time_str: str) -> discord.Embed:
        embed = discord.Embed(
            title="Проверка готовности",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Нарушения:",
            value="\n".join(violations) if violations else "Нет нарушений",
            inline=False
        )
        embed.add_field(
            name="Пояснения:",
            value=(
                "<:Mute:1544687593323761756> — Зайти в канал игры\n"
                "<:muted_audio:1544687640891105392> — Размьютить наушники"
            ),
            inline=False
        )
        embed.set_footer(text=f"У вас есть {time_str}, чтобы устранить нарушения, либо вы получите наказание")
        return embed

    @staticmethod
    def get_control_embed(host_mention: str, players: set) -> discord.Embed:
        embed = discord.Embed(
            title="👑 Управление игрой",
            description="Список записанных игроков",
            color=discord.Color.blue()
        )
        embed.add_field(name="Ведущий", value=host_mention, inline=False)
        if players:
            sorted_players = sorted(players)
            players_list = "\n".join([f"{idx+1}) <@{uid}>" for idx, uid in enumerate(sorted_players)])
            embed.add_field(name=f"Игроки ({len(players)}/10)", value=players_list, inline=False)
        else:
            embed.add_field(name="Игроки", value="*Пока никого*", inline=False)
        return embed

    @staticmethod
    def get_confirm_role_embed(user_mention: str, role: str) -> discord.Embed:
        return discord.Embed(
            title="✅ Подтверждение роли",
            description=f"{user_mention} подтвердил роль **{role}**",
            color=discord.Color.green()
        )

    @staticmethod
    def get_foul_embed(member_display_name: str, fouls: int, warnings: int, avatar_url: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚠️ {member_display_name} поаккуратнее!",
            description=f"Тебе выдали фол.\n[Ф: {fouls}/4][П: {warnings}/2]",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=avatar_url)
        return embed

    @staticmethod
    def get_warning_embed(member_display_name: str, fouls: int, warnings: int, avatar_url: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚠️ {member_display_name} поаккуратнее!",
            description=f"Тебе выдали предупреждение.\n[Ф: {fouls}/4][П: {warnings}/2]",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=avatar_url)
        return embed

    @staticmethod
    def get_revive_embed(member_mention: str, reason: str) -> discord.Embed:
        return discord.Embed(
            title="⬆️ Поднятие со стола",
            description=f"{member_mention} поднят со стола. Причина: {reason}",
            color=discord.Color.orange()
        )

    @staticmethod
    def get_result_embed(game: dict, guild: discord.Guild) -> discord.Embed:
        """Формирует embed с результатами игры строго по шаблону."""
        alive_roles = [game['roles'][pid] for pid in game['alive'] if pid in game['roles']]
        black = [r for r in alive_roles if r in ['мафия', 'дон']]
        red = [r for r in alive_roles if r in ['мирный', 'шериф', 'доктор']]

        if game.get('early_end', False):
            status = "Досрочное завершение"
            color = discord.Color.greyple()
        elif len(black) == 0:
            status = "Победа мирного города 🏆"
            color = discord.Color.red()
        elif len(red) <= len(black):
            status = "Победа мафии 🏆"
            color = discord.Color.dark_gray()
        else:
            status = "Игра не завершена"
            color = discord.Color.gold()

        now = datetime.now()
        embed = discord.Embed(
            title=f"Результат игры от {now.strftime('%d.%m.%Y %H:%M')}",
            color=color
        )
        description = (
            f"## Режим игры\n\"{game['mode']}\" Мафия\n\n"
            f"## Статус игры\n{status}\n\n"
        )

        start_time = game.get('start_time')
        if start_time:
            elapsed = int(time.time()) - start_time
            minutes = elapsed // 60
            seconds = elapsed % 60
            duration = f"{minutes} мин {seconds} сек"
            description += f"## Длительность\n{duration}\n\n"

        creator_id = game.get('creator_id')
        if creator_id:
            description += f"## Ведущий\n<@{creator_id}>\n\n"

        red_players = [pid for pid, role in game['roles'].items() if role in ['мирный', 'шериф', 'доктор']]
        if red_players:
            red_list = []
            for pid in sorted(red_players):
                member = guild.get_member(pid)
                slot = member.display_name if member else str(pid)
                role_display = game['roles'][pid].capitalize()
                red_list.append(f"{slot} <@{pid}> - {role_display}")
            description += "## Мирные жители\n" + "\n".join(red_list) + "\n\n"
        else:
            description += "## Мирные жители\nНет\n\n"

        black_players = [pid for pid, role in game['roles'].items() if role in ['мафия', 'дон']]
        if black_players:
            black_list = []
            for pid in sorted(black_players):
                member = guild.get_member(pid)
                slot = member.display_name if member else str(pid)
                role_display = game['roles'][pid].capitalize()
                black_list.append(f"{slot} <@{pid}> - {role_display}")
            description += "## Мафия\n" + "\n".join(black_list) + "\n\n"
        else:
            description += "## Мафия\nНет\n\n"

        best = game.get('best_player')
        if best:
            pid, data = best
            member = guild.get_member(pid)
            best_slot = member.display_name if member else str(pid)
            hits = data.get('hits', 0)
            total = data.get('total', 0)
            targets = data.get('targets', [])
            target_slots = []
            for tid in targets:
                m = guild.get_member(tid)
                target_slots.append(m.display_name if m else str(tid))
            targets_str = "・".join(target_slots) if target_slots else "Нет"

            description += f"**Лучший ход от {best_slot}**\n"
            description += f"Попаданий: {hits} из {total}\n"
            description += f"Указанные игроки: {targets_str}\n\n"

        kills = game.get('kill_log', [])
        if kills:
            kill_lines = []
            for entry in kills:
                killer_id = entry.get('killer_id')
                victim_id = entry.get('victim_id')
                killer = guild.get_member(killer_id) if killer_id else None
                victim = guild.get_member(victim_id) if victim_id else None
                killer_slot = killer.display_name if killer else "Мафия"
                victim_slot = victim.display_name if victim else "?"
                kill_lines.append(f"{killer_slot} → {victim_slot}")
            description += "## Убитые:\n" + "\n".join(kill_lines) + "\n\n"
        else:
            description += "## Убитые:\nНет\n\n"

        voted = game.get('vote_log', [])
        if voted:
            voted_slots = []
            for vid in voted:
                member = guild.get_member(vid)
                voted_slots.append(member.display_name if member else str(vid))
            description += "## Заголосованные:\n" + "\n".join(voted_slots) + "\n\n"
        else:
            description += "## Заголосованные:\nНет\n\n"

        logs = game.get('logs', [])
        if logs:
            log_lines = []
            for log in logs[-15:]:
                parts = log.split()
                new_parts = []
                for p in parts:
                    if p.startswith('<@') and p.endswith('>'):
                        try:
                            uid = int(p[2:-1])
                            member = guild.get_member(uid)
                            if member:
                                new_parts.append(member.display_name)
                            else:
                                new_parts.append(p)
                        except:
                            new_parts.append(p)
                    else:
                        new_parts.append(p)
                log_lines.append(" ".join(new_parts))
            description += "📜 Логи игры\n" + "\n".join(log_lines)

        embed.description = description
        return embed