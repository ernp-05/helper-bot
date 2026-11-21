import random
import re
import discord
from discord import app_commands


class MiscCommands:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree
        self._setup_slash()

    def _highest_role_color(self, member):
        if member is None or not hasattr(member, 'roles'):
            return 0x5865F2
        best = None
        for role in member.roles:
            if role.color and role.color.value != 0:
                if best is None or role.position > best.position:
                    best = role
        if best is None:
            return 0x5865F2
        return best.color.value

    def _resolve_user(self, message):
        if message.mentions:
            return message.mentions[0]
        if message.reference:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message):
                return resolved.author
        ids = re.findall(r'(?<!<@!?)(?<!\d)(\d{15,20})(?!\d)', message.content)
        if ids:
            uid = int(ids[0])
            member = message.guild.get_member(uid) if message.guild else None
            if member is not None:
                return member
            return discord.Object(id=uid)
        return message.author

    def _format_role_list(self, roles):
        if not roles:
            return "None"
        return ", ".join(r.name for r in roles)

    def _admin_roles(self, guild):
        return [r for r in guild.roles if r.permissions.ban_members and not r.is_default()]

    def _mod_roles(self, guild, exclude_ids=None):
        exclude_ids = exclude_ids or set()
        return [
            r for r in guild.roles
            if r.permissions.manage_messages
            and not r.is_default()
            and r.id not in exclude_ids
        ]

    async def _build_serverinfo_embed(self, guild):
        owner = guild.owner
        if owner is None:
            try:
                owner = await self.bot.fetch_user(guild.owner_id)
            except Exception:
                owner = None
        owner_text = owner.display_name if owner else f"ID {guild.owner_id}"

        created_fmt = discord.utils.format_dt(guild.created_at, style="F")

        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        admin_roles = self._admin_roles(guild)
        exclude = {r.id for r in admin_roles}
        mod_roles = self._mod_roles(guild, exclude)

        embed = discord.Embed(title=guild.name, color=0x5865F2)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="Guild Name",
            value=(
                f"👑 Guild Owner: {owner_text}\n"
                f"📆 Guild Creation: {created_fmt}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Members",
            value=(
                f"👥 Total Members: {guild.member_count}\n"
                f"👤 Humans: {humans}\n"
                f"🤖 Bots: {bots}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Roles",
            value=(
                f"Total Roles: {len(guild.roles)}\n"
                f"⭐ Admin Roles: {self._format_role_list(admin_roles)}\n"
                f"✳️ Mod Roles: {self._format_role_list(mod_roles)}"
            ),
            inline=False,
        )
        return embed

    def _setup_slash(self):
        @self.tree.command(name="alea", description="Random number")
        @app_commands.describe(input="N or N-M")
        async def slash_alea(interaction: discord.Interaction, input: str):
            await interaction.response.defer(ephemeral=False)
            text = input.strip()
            m = re.match(r'^(\d+)$', text)
            if m:
                n = int(m.group(1))
                if n < 1:
                    await interaction.followup.send("❌")
                    return
                x = random.randint(1, n)
                await interaction.followup.send(f"{x}/{n}")
                return
            m = re.match(r'^(\d+)-(\d+)$', text)
            if m:
                a = int(m.group(1))
                b = int(m.group(2))
                if a > b:
                    a, b = b, a
                if a < 1:
                    await interaction.followup.send("❌")
                    return
                x = random.randint(a, b)
                await interaction.followup.send(f"{x}/{a}-{b}")
                return
            await interaction.followup.send("❌")

        @self.tree.command(name="serverinfo", description="Show server info")
        async def slash_serverinfo(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False)
            if interaction.guild is None:
                await interaction.followup.send("❌ This command only works in a server.")
                return
            try:
                embed = await self._build_serverinfo_embed(interaction.guild)
                await interaction.followup.send(embed=embed)
            except Exception:
                await interaction.followup.send("❌")

    async def handle_message(self, message):
        content = message.content.strip()
        lower = content.lower()

        if lower.startswith('!avatar'):
            user = self._resolve_user(message)
            try:
                if isinstance(user, discord.Object):
                    fetched = await self.bot.fetch_user(user.id)
                    avatar_url = fetched.display_avatar.url if fetched.display_avatar else None
                    name = fetched.display_name
                else:
                    avatar_url = user.display_avatar.url if user.display_avatar else None
                    name = user.display_name
                if avatar_url is None:
                    await message.add_reaction('❌')
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s avatar", color=color)
                embed.set_image(url=avatar_url)
                await message.channel.send(embed=embed)
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!gavatar'):
            user = self._resolve_user(message)
            try:
                if isinstance(user, discord.Object):
                    fetched = await self.bot.fetch_user(user.id)
                    member = message.guild.get_member(user.id) if message.guild else None
                    avatar_url = member.guild_avatar.url if member and member.guild_avatar else (fetched.display_avatar.url if fetched.display_avatar else None)
                    name = fetched.display_name
                else:
                    avatar_url = user.guild_avatar.url if getattr(user, 'guild_avatar', None) else (user.display_avatar.url if user.display_avatar else None)
                    name = user.display_name
                if avatar_url is None:
                    await message.add_reaction('❌')
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s server avatar", color=color)
                embed.set_image(url=avatar_url)
                await message.channel.send(embed=embed)
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!banner'):
            user = self._resolve_user(message)
            try:
                if isinstance(user, discord.Object):
                    fetched = await self.bot.fetch_user(user.id)
                elif isinstance(user, discord.Member):
                    fetched = await self.bot.fetch_user(user.id)
                else:
                    fetched = user
                banner_url = fetched.banner.url if fetched.banner else None
                if banner_url is None:
                    await message.add_reaction('❌')
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await message.channel.send(embed=embed)
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!gbanner'):
            user = self._resolve_user(message)
            try:
                if isinstance(user, discord.Object):
                    fetched = await self.bot.fetch_user(user.id)
                elif isinstance(user, discord.Member):
                    fetched = await self.bot.fetch_user(user.id)
                else:
                    fetched = user
                banner_url = fetched.banner.url if fetched.banner else None
                if banner_url is None:
                    await message.add_reaction('❌')
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await message.channel.send(embed=embed)
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!alea'):
            rest = content[len('!alea'):].strip()
            m = re.match(r'^(\d+)$', rest)
            if m:
                n = int(m.group(1))
                if n < 1:
                    await message.add_reaction('❌')
                    return True
                x = random.randint(1, n)
                await message.channel.send(f"{x}/{n}")
                return True
            m = re.match(r'^(\d+)-(\d+)$', rest)
            if m:
                a = int(m.group(1))
                b = int(m.group(2))
                if a > b:
                    a, b = b, a
                if a < 1:
                    await message.add_reaction('❌')
                    return True
                x = random.randint(a, b)
                await message.channel.send(f"{x}/{a}-{b}")
                return True
            await message.add_reaction('❌')
            return True

        if lower.startswith('!chose'):
            body = content[len('!chose'):]
            if body.startswith(' '):
                body = body[1:]
            lines = [l for l in body.split('\n') if l.strip()]
            if not lines:
                await message.add_reaction('❌')
                return True
            pick = random.choice(lines).strip()
            await message.channel.send(pick)
            return True

        if lower.startswith('!serverinfo'):
            if message.guild is None:
                await message.add_reaction('❌')
                return True
            try:
                embed = await self._build_serverinfo_embed(message.guild)
                await message.channel.send(embed=embed)
            except Exception:
                await message.add_reaction('❌')
            return True

        return False
