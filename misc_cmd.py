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

    def _roles_text(self, roles):
        if not roles:
            return "None"
        ordered = sorted(roles, key=lambda r: r.position, reverse=True)
        return ", ".join(r.mention for r in ordered)

    def _split_by_limit(self, text, limit):
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

    async def _build_serverinfo_embeds(self, guild):
        owner = guild.owner
        if owner is None:
            owner = await self.bot.fetch_user(guild.owner_id)
        owner_text = owner.mention if owner else f"ID {guild.owner_id}"

        created_fmt = discord.utils.format_dt(guild.created_at, style="F")

        humans = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)

        admin_roles = self._admin_roles(guild)
        exclude = {r.id for r in admin_roles}
        mod_roles = self._mod_roles(guild, exclude)

        description = (guild.description or "").strip()

        admin_text = self._roles_text(admin_roles)
        mod_text = self._roles_text(mod_roles)

        full_roles_text = f"⭐ Admin Roles: {admin_text}\n✳️ Mod Roles: {mod_text}"

        first_lines = []
        if description:
            first_lines.append(f"📝 {description}")
        first_lines.append(f"👑 Guild Owner: {owner_text}")
        first_lines.append(f"📆 Guild Creation: {created_fmt}")

        roles_value = (
            f"Total Roles: {len(guild.roles)}\n"
            f"⭐ Admin Roles: {len(admin_roles)}\n"
            f"✳️ Mod Roles: {len(mod_roles)}\n\n"
            f"{full_roles_text}"
        )

        embed = discord.Embed(title=guild.name, color=0x5865F2)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="\u200b", value="\n".join(first_lines), inline=False)
        embed.add_field(
            name="Members",
            value=(
                f"👥 Total Members: {guild.member_count}\n"
                f"👤 Humans: {humans}\n"
                f"🤖 Bots: {bots}"
            ),
            inline=False,
        )

        total_len = len(embed.title or "") + len("\u200b") + len("\n".join(first_lines)) + len("Members") + len(embed.fields[1].value) + len("Roles") + len(roles_value)
        field_limit = 1024

        if len(roles_value) <= field_limit and total_len <= 6000:
            embed.add_field(name="Roles", value=roles_value, inline=False)
            return [embed]

        embed.add_field(
            name="Roles",
            value=(
                f"Total Roles: {len(guild.roles)}\n"
                f"⭐ Admin Roles: {len(admin_roles)}\n"
                f"✳️ Mod Roles: {len(mod_roles)}"
            ),
            inline=False,
        )
        embeds = [embed]

        for label, text in (("⭐ Admin Roles", admin_text), ("✳️ Mod Roles", mod_text)):
            if text == "None":
                continue
            chunks = self._split_by_limit(text, 4000)
            total = len(chunks)
            for i, chunk in enumerate(chunks):
                e = discord.Embed(color=0x5865F2)
                e.title = label if i == 0 else f"{label} ({i + 1})"
                e.description = chunk
                e.set_footer(text=f"{label} · {i + 1}/{total}")
                embeds.append(e)

        return embeds

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
                embeds = await self._build_serverinfo_embeds(interaction.guild)
                for embed in embeds:
                    await interaction.followup.send(embed=embed)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await interaction.followup.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")

        user_group = app_commands.Group(name="user", description="User info commands")

        @user_group.command(name="avatar", description="Show a user's avatar")
        @app_commands.describe(user="User (default: yourself)")
        async def user_avatar(interaction: discord.Interaction, user: discord.User = None):
            await interaction.response.defer(ephemeral=False)
            target = user or interaction.user
            try:
                if isinstance(target, discord.Object):
                    fetched = await self.bot.fetch_user(target.id)
                else:
                    fetched = target
                avatar_url = fetched.display_avatar.url if fetched.display_avatar else None
                if avatar_url is None:
                    await interaction.followup.send("❌ No avatar.")
                    return
                color = self._highest_role_color(target if isinstance(target, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s avatar", color=color)
                embed.set_image(url=avatar_url)
                await interaction.followup.send(embed=embed)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await interaction.followup.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")

        @user_group.command(name="banner", description="Show a user's banner")
        @app_commands.describe(user="User (default: yourself)")
        async def user_banner(interaction: discord.Interaction, user: discord.User = None):
            await interaction.response.defer(ephemeral=False)
            target = user or interaction.user
            try:
                if isinstance(target, discord.Object):
                    fetched = await self.bot.fetch_user(target.id)
                else:
                    fetched = target
                banner_url = fetched.banner.url if fetched.banner else None
                if banner_url is None:
                    await interaction.followup.send("❌ No banner.")
                    return
                color = self._highest_role_color(target if isinstance(target, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await interaction.followup.send(embed=embed)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await interaction.followup.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")

        @user_group.command(name="principal", description="Show a user's main info")
        @app_commands.describe(user="User (default: yourself)")
        async def user_principal(interaction: discord.Interaction, user: discord.User = None):
            await interaction.response.defer(ephemeral=False)
            target = user or interaction.user
            try:
                if isinstance(target, discord.Object):
                    fetched = await self.bot.fetch_user(target.id)
                else:
                    fetched = target
                member = interaction.guild.get_member(fetched.id) if interaction.guild else None
                color = self._highest_role_color(member)
                embed = discord.Embed(title=f"User info: {fetched.name}", color=color)
                embed.set_thumbnail(url=fetched.display_avatar.url if fetched.display_avatar else None)
                embed.add_field(name="Global name", value=fetched.global_name or "None", inline=True)
                embed.add_field(name="Username", value=fetched.name, inline=True)
                embed.add_field(name="Guild nickname", value=(member.nick if member and member.nick else "None"), inline=True)
                embed.add_field(name="Account created", value=discord.utils.format_dt(fetched.created_at, style="R"), inline=True)
                if member is not None and member.joined_at is not None:
                    embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, style="R"), inline=True)
                else:
                    embed.add_field(name="Joined server", value="None", inline=True)
                embed.add_field(name="User ID", value=str(fetched.id), inline=False)
                await interaction.followup.send(embed=embed)
            except discord.HTTPException as e:
                await interaction.followup.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await interaction.followup.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")

        self.tree.add_command(user_group)

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
                    await message.channel.send("❌ No avatar.")
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s avatar", color=color)
                embed.set_image(url=avatar_url)
                await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                await message.channel.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await message.channel.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")
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
                    await message.channel.send("❌ No avatar.")
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{name}'s server avatar", color=color)
                embed.set_image(url=avatar_url)
                await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                await message.channel.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await message.channel.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")
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
                    await message.channel.send("❌ No banner.")
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                await message.channel.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await message.channel.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")
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
                    await message.channel.send("❌ No banner.")
                    return True
                color = self._highest_role_color(user if isinstance(user, discord.Member) else None)
                embed = discord.Embed(title=f"{fetched.display_name}'s banner", color=color)
                embed.set_image(url=banner_url)
                await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                await message.channel.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await message.channel.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")
            return True

        if lower.startswith('!alea'):
            rest = content[len('!alea'):].strip()
            m = re.match(r'^(\d+)$', rest)
            if m:
                n = int(m.group(1))
                if n < 1:
                    await message.channel.send("❌ N must be >= 1")
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
                    await message.channel.send("❌ Range must start >= 1")
                    return True
                x = random.randint(a, b)
                await message.channel.send(f"{x}/{a}-{b}")
                return True
            await message.channel.send("❌ Invalid format. Use N or N-M")
            return True

        if lower.startswith('!chose'):
            body = content[len('!chose'):]
            if body.startswith(' '):
                body = body[1:]
            lines = [l for l in body.split('\n') if l.strip()]
            if not lines:
                await message.channel.send("❌ No options.")
                return True
            pick = random.choice(lines).strip()
            await message.channel.send(pick)
            return True

        if lower.startswith('!serverinfo'):
            if message.guild is None:
                await message.channel.send("❌ This command only works in a server.")
                return True
            try:
                embeds = await self._build_serverinfo_embeds(message.guild)
                for embed in embeds:
                    await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                await message.channel.send(f"❌ HTTP {e.status}: {str(e.text)[:1900]}")
            except Exception as e:
                await message.channel.send(f"❌ {type(e).__name__}: {str(e)[:1900]}")
            return True

        return False
