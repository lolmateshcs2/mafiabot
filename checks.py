import discord
from config import ALLOWED_ROLE_ID

async def check_allowed_role(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False
    role = interaction.guild.get_role(ALLOWED_ROLE_ID)
    if role is None:
        return False
    return role in interaction.user.roles