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
        ids = re.findall(r'(?<!<@!)(?<!<@)(?<!\d)(\d{15,20})(?!\d)', message.content)
        if ids:
            uid = int(ids[0])
            member = message.guild.get_member(uid) if message.guild else None
            if member is not None:
                return member
            return discord.Object(id=uid)
        return message.author

    def _chunk_text(self, text, limit=1900):
        chunks = []
        current = ""
        for piece in text.split(", "):
            add = piece if not current else ", " + piece
            if len(current) + len(add) > limit:
                if current:
                    chunks.append(current)
                current = piece
            else:
                current += add
        if current:
            chunks.append(current)
        return chunks

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
            except Exception as e:
                print(f"SERVERINFO OWNER FETCH ERROR: {e!r}")
                owner = None
        owner_text = owner.mention if owner else f"ID {guild.owner_id}"

        created_fmt = discord.utils.format_dt(guild.created_at, style="F")

        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        admin_roles = self._admin_roles(guild)
        exclude = {r.id for r in admin_roles}
        mod_roles = self._mod_roles(guild, exclude)

        description = (guild.description or "").strip()

        embed = discord.Embed(title=guild.name, color=0x5865F2)
        if guild.icon:
            try:
                embed.set_thumbnail(url=guild.icon.url)
            except Exception as e:
                print(f"SERVERINFO ICON ERROR: {e!r}")

        first_lines = []
        if description:
            first_lines.append(f"📝 {description}")
        first_lines.append(f"👑 Guild Owner: {owner_text}")
        first_lines.append(f"📆 Guild Creation: {created_fmt}")

        embed.add_field(
            value="\n".join(first_lines),
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
                f"⭐ Admin Roles: {len(admin_roles)}\n"
                f"✳️ Mod Roles: {len(mod_roles)}"
            ),
            inline=False,
        )
        return embed, admin_roles, mod_roles

    async def _safe_send(self, channel, *args, **kwargs):
        try:
            return await channel.send(*args, **kwargs)
        except discord.HTTPException as e:
            print(f"SEND HTTP ERROR: {e!r}")
            return None
        except Exception as e:
            print(f"SEND ERROR: {e!r}")
            return None

    async def _safe_error(self, message):
        try:
            await message.channel.send("❌", delete_after=3)
        except Exception as e:
            print(f"ERROR SEND FAILED: {e!r}")

    async def _send_roles_extra(self, channel, admin_roles, mod_roles):
        for label, roles in (("⭐ Admin Roles", admin_roles), ("✳️ Mod Roles", mod_roles)):
            if not roles:
                continue
            ordered = sorted(roles, key=lambda r: r.position, reverse=True)
            text = ", ".join(r.mention for r in ordered)
            chunks = self._chunk_text(text)
            for i, chunk in enumerate(chunks):
                header = f"**{label}** ({len(roles)}):\n" if i == 0 else ""
                await self._safe_send(channel, header + chunk)

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
            print(f"SLASH SERVERINFO START guild={interaction.guild_id}")
            try:
                await interaction.response.defer(ephemeral=False)
            except Exception as e:
                print(f"SLASH SERVERINFO DEFER ERROR: {e!r}")
                return
            if interaction.guild is None:
                try:
                    await interaction.followup.send("❌ This command only works in a server.")
                except Exception as e:
                    print(f"SLASH SERVERINFO NOGUILD SEND ERROR: {e!r}")
                return
            try:
                embed, admin_roles, mod_roles = await self._build_serverinfo_embed(interaction.guild)
                print(f"SLASH SERVERINFO EMBED BUILT fields={len(embed.fields)}")
                await interaction.followup.send(embed=embed)
                print("SLASH SERVERINFO EMBED SENT")
                for label, roles in (("⭐ Admin Roles", admin_roles), ("✳️ Mod Roles", mod_roles)):
                    if not roles:
                        continue
                    ordered = sorted(roles, key=lambda r: r.position, reverse=True)
                    text = ", ".join(r.mention for r in ordered)
                    chunks = self._chunk_text(text)
                    for i, chunk in enumerate(chunks):
                        header = f"**{label}** ({len(roles)}):\n" if i == 0 else ""
                        await interaction.followup.send(header + chunk)
                print("SLASH SERVERINFO DONE")
            except Exception as e:
                print(f"SLASH SERVERINFO ERROR: {e!r}")
                try:
                    await interaction.followup.send("❌")
                except Exception as e2:
                    print(f"SLASH SERVERINFO FOLLOWUP ERROR: {e2!r}")

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
                    await self._safe_error(message)
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s avatar", color=color)
                embed.set_image(url=avatar_url)
                await self._safe_send(message.channel, embed=embed)
            except Exception as e:
                print(f"AVATAR ERROR: {e!r}")
                await self._safe_error(message)
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
                    await self._safe_error(message)
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s server avatar", color=color)
                embed.set_image(url=avatar_url)
                await self._safe_send(message.channel, embed=embed)
            except Exception as e:
                print(f"GAVATAR ERROR: {e!r}")
                await self._safe_error(message)
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
                    await self._safe_error(message)
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await self._safe_send(message.channel, embed=embed)
            except Exception as e:
                print(f"BANNER ERROR: {e!r}")
                await self._safe_error(message)
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
                    await self._safe_error(message)
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await self._safe_send(message.channel, embed=embed)
            except Exception as e:
                print(f"GBANNER ERROR: {e!r}")
                await self._safe_error(message)
            return True

        if lower.startswith('!alea'):
            rest = content[len('!alea'):].strip()
            m = re.match(r'^(\d+)$', rest)
            if m:
                n = int(m.group(1))
                if n < 1:
                    await self._safe_error(message)
                    return True
                x = random.randint(1, n)
                await self._safe_send(message.channel, f"{x}/{n}")
                return True
            m = re.match(r'^(\d+)-(\d+)$', rest)
            if m:
                a = int(m.group(1))
                b = int(m.group(2))
                if a > b:
                    a, b = b, a
                if a < 1:
                    await self._safe_error(message)
                    return True
                x = random.randint(a, b)
                await self._safe_send(message.channel, f"{x}/{a}-{b}")
                return True
            await self._safe_error(message)
            return True

        if lower.startswith('!chose'):
            body = content[len('!chose'):]
            if body.startswith(' '):
                body = body[1:]
            lines = [l for l in body.split('\n') if l.strip()]
            if not lines:
                await self._safe_error(message)
                return True
            pick = random.choice(lines).strip()
            await self._safe_send(message.channel, pick)
            return True

        if lower.startswith('!serverinfo'):
            print(f"MSG SERVERINFO START guild={message.guild.id if message.guild else None}")
            if message.guild is None:
                await self._safe_error(message)
                return True
            try:
                embed, admin_roles, mod_roles = await self._build_serverinfo_embed(message.guild)
                print(f"MSG SERVERINFO EMBED BUILT fields={len(embed.fields)}")
                await self._safe_send(message.channel, embed=embed)
                print("MSG SERVERINFO EMBED SENT")
                await self._send_roles_extra(message.channel, admin_roles, mod_roles)
                print("MSG SERVERINFO DONE")
            except Exception as e:
                print(f"SERVERINFO ERROR: {e!r}")
                await self._safe_error(message)
            return True

        return False
