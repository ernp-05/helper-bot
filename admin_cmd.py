import re
import sys
import json
import asyncio
import aiohttp
import discord
from discord import app_commands
from datetime import timedelta

TOKEN = sys.argv[1] if len(sys.argv) > 1 else None

BLACKLIST_FILE = 'blacklist.json'
BLACKLIST_LEVELS = ('low', 'high', 'mute', 'kick', 'ban')


class BlacklistView(discord.ui.View):
    def __init__(self, entries, page=0):
        super().__init__(timeout=120)
        self.entries = entries
        self.page = page
        self.per_page = 25

    def build_embed(self):
        total = len(self.entries)
        max_page = max(0, (total - 1) // self.per_page) if total else 0
        if self.page > max_page:
            self.page = max_page
        start = self.page * self.per_page
        chunk = self.entries[start:start + self.per_page]
        embed = discord.Embed(title="Blacklist", color=0x5865F2)
        if chunk:
            embed.description = "\n".join(f"`{w}` — **{lvl}**" for w, lvl in chunk)
        else:
            embed.description = "Empty."
        embed.set_footer(text=f"Page {self.page + 1}/{max_page + 1} · Total: {total}")
        return embed

    def update_buttons(self):
        total = len(self.entries)
        max_page = max(0, (total - 1) // self.per_page) if total else 0
        self.prev.disabled = self.page <= 0
        self.next.disabled = self.page >= max_page

    async def send_to(self, channel):
        self.update_buttons()
        await channel.send(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        total = len(self.entries)
        max_page = max(0, (total - 1) // self.per_page) if total else 0
        if self.page < max_page:
            self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class AdminCommands:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree
        self.blacklist = self._load_blacklist()
        self._setup_slash()

    def _load_blacklist(self):
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {str(k).lower(): str(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_blacklist(self):
        try:
            with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.blacklist, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _is_owner(self, guild, user_id):
        if guild is None:
            return False
        return guild.owner_id == user_id

    def _can_manage_channels(self, member):
        if member is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        perms = member.guild_permissions
        return perms.administrator or perms.manage_channels

    def _can_moderate(self, member, perm_name):
        if member is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        perms = member.guild_permissions
        if perms.administrator:
            return True
        return getattr(perms, perm_name, False)

    def _can_manage_messages(self, member):
        if member is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        perms = member.guild_permissions
        return perms.administrator or perms.manage_messages

    def _can_manage_nicknames(self, member):
        if member is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        perms = member.guild_permissions
        return perms.administrator or perms.manage_nicknames

    def _can_create_invite(self, member):
        if member is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        perms = member.guild_permissions
        return perms.administrator or perms.create_instant_invite

    def _bot_can(self, guild, perm_name):
        if guild is None or guild.me is None:
            return False
        perms = guild.me.guild_permissions
        if perms.administrator:
            return True
        return getattr(perms, perm_name, False)

    def _can_act_on(self, actor, target, guild):
        if guild is None or target is None or actor is None:
            return False
        if target.id == guild.owner_id:
            return False
        if target.id == self.bot.user.id:
            return False
        if target.id == actor.id:
            return False
        if not self._is_owner(guild, actor.id):
            actor_top = actor.top_role.position if hasattr(actor, 'top_role') else -1
            target_top = target.top_role.position if hasattr(target, 'top_role') else -1
            if actor_top <= target_top:
                return False
        bot_member = guild.me
        if bot_member is None:
            return False
        target_top = target.top_role.position if hasattr(target, 'top_role') else -1
        if bot_member.top_role.position <= target_top:
            return False
        return True

    def _extract_ids(self, text):
        ids = []
        for m in re.findall(r'<#(\d+)>', text):
            ids.append(int(m))
        for m in re.findall(r'(?<!<#)(?<!\d)(\d{15,20})(?!\d)', text):
            ids.append(int(m))
        seen = set()
        out = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return out

    def _parse_duration(self, token):
        if not token:
            return None
        token = token.strip().lower()
        pattern = re.compile(r'^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$')
        m = pattern.match(token)
        if not m:
            return None
        if not any(m.groups()):
            return None
        days = int(m.group(1)) if m.group(1) else 0
        hours = int(m.group(2)) if m.group(2) else 0
        minutes = int(m.group(3)) if m.group(3) else 0
        seconds = int(m.group(4)) if m.group(4) else 0
        total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if total.total_seconds() <= 0:
            return None
        if total > timedelta(days=28):
            total = timedelta(days=28)
        return total

    def _resolve_targets(self, message):
        if message.mentions:
            return list(message.mentions)
        if message.reference:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message):
                return [resolved.author]
        return []

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

    def _member_type(self, guild, member):
        if member is None:
            return "None"
        if guild is not None and guild.owner_id == member.id:
            return "Owner"
        perms = member.guild_permissions
        if perms.administrator:
            return "Admin"
        if perms.manage_messages or perms.manage_channels or perms.kick_members or perms.ban_members:
            return "Mod"
        return "Member"

    def _level_perm_required(self, level):
        if level == 'mute':
            return 'moderate_members'
        if level == 'kick':
            return 'kick_members'
        if level == 'ban':
            return 'ban_members'
        return None

    def _can_set_level(self, member, level):
        if level in ('low', 'high'):
            return self._can_manage_messages(member)
        perm = self._level_perm_required(level)
        if perm is None:
            return False
        if self._is_owner(member.guild, member.id):
            return True
        if member.guild_permissions.administrator:
            return True
        return getattr(member.guild_permissions, perm, False)

    async def _apply_lock(self, channel):
        try:
            overwrites = channel.overwrites
            everyone = channel.guild.default_role
            ow = overwrites.get(everyone)
            if ow is None:
                ow = discord.PermissionOverwrite()
            ow.send_messages = False
            await channel.set_permissions(everyone, overwrite=ow)
            return True
        except Exception:
            return False

    async def _apply_open(self, channel):
        try:
            overwrites = channel.overwrites
            everyone = channel.guild.default_role
            ow = overwrites.get(everyone)
            if ow is None:
                ow = discord.PermissionOverwrite()
            ow.send_messages = None
            await channel.set_permissions(everyone, overwrite=ow)
            return True
        except Exception:
            return False

    async def _apply_hide(self, channel):
        try:
            overwrites = channel.overwrites
            everyone = channel.guild.default_role
            ow = overwrites.get(everyone)
            if ow is None:
                ow = discord.PermissionOverwrite()
            ow.view_channel = False
            await channel.set_permissions(everyone, overwrite=ow)
            return True
        except Exception:
            return False

    async def _apply_show(self, channel):
        try:
            overwrites = channel.overwrites
            everyone = channel.guild.default_role
            ow = overwrites.get(everyone)
            if ow is None:
                ow = discord.PermissionOverwrite()
            ow.view_channel = None
            await channel.set_permissions(everyone, overwrite=ow)
            return True
        except Exception:
            return False

    async def _apply_clone(self, source, target):
        try:
            await target.edit(overwrites=source.overwrites)
            return True
        except Exception:
            return False

    async def _apply_slowmode(self, channel, seconds):
        try:
            await channel.edit(slowmode_delay=seconds)
            return True
        except Exception:
            return False

    async def _apply_kick(self, member, reason):
        try:
            await member.kick(reason=reason)
            return True
        except Exception:
            return False

    async def _apply_ban(self, member, reason):
        try:
            await member.ban(reason=reason)
            return True
        except Exception:
            return False

    async def _apply_mute(self, member, duration, reason):
        try:
            await member.timeout(duration, reason=reason)
            return True
        except Exception:
            return False

    async def _apply_unmute(self, member):
        try:
            await member.timeout(None)
            return True
        except Exception:
            return False

    async def _apply_unban(self, guild, user_id, reason):
        try:
            user = discord.Object(id=user_id)
            await guild.unban(user, reason=reason)
            return True
        except Exception:
            return False

    async def _apply_blacklist_action(self, message, level):
        try:
            try:
                await message.delete()
            except Exception:
                pass
            if level == 'mute':
                try:
                    await message.author.timeout(timedelta(hours=6), reason="Blacklist filter")
                except Exception:
                    pass
            elif level == 'kick':
                try:
                    await message.author.kick(reason="Blacklist filter")
                except Exception:
                    pass
            elif level == 'ban':
                try:
                    await message.author.ban(reason="Blacklist filter", delete_message_days=0)
                except Exception:
                    pass
        except Exception:
            pass

    def _check_blacklist(self, message):
        if message.guild is None:
            return None
        if message.author.id == self.bot.user.id:
            return None
        if not message.content:
            return None
        content = message.content.lower()
        author = message.author
        can_bypass = False
        if isinstance(author, discord.Member):
            can_bypass = self._can_manage_messages(author)
        for word, level in self.blacklist.items():
            if word and word in content:
                if level in ('low', 'mute', 'kick', 'ban') and can_bypass:
                    return None
                return level
        return None

    async def _send_userinfo(self, channel, user):
        if isinstance(user, discord.Object):
            fetched = await self.bot.fetch_user(user.id)
            member = channel.guild.get_member(user.id) if channel.guild else None
        else:
            fetched = user
            member = user if isinstance(user, discord.Member) else (channel.guild.get_member(user.id) if channel.guild else None)
        color = self._highest_role_color(member)
        embed = discord.Embed(title=f"User info: {fetched.name}", color=color)
        embed.set_thumbnail(url=fetched.display_avatar.url if fetched.display_avatar else None)
        embed.add_field(name="Global name", value=fetched.global_name or "None", inline=True)
        embed.add_field(name="Username", value=fetched.name, inline=True)
        if member is not None:
            embed.add_field(name="Guild nickname", value=member.nick or "None", inline=True)
            embed.add_field(name="Member type", value=self._member_type(channel.guild, member), inline=True)
        else:
            embed.add_field(name="Guild nickname", value="None", inline=True)
            embed.add_field(name="Member type", value="None", inline=True)
        embed.add_field(name="Account created", value=discord.utils.format_dt(fetched.created_at, style="R"), inline=True)
        if member is not None and member.joined_at is not None:
            embed.add_field(name="Joined server", value=discord.utils.format_dt(member.joined_at, style="R"), inline=True)
        else:
            embed.add_field(name="Joined server", value="None", inline=True)
        embed.add_field(name="User ID", value=str(fetched.id), inline=False)
        await channel.send(embed=embed)

    def _invite_help_embed(self):
        embed = discord.Embed(title="Invite help", color=0x5865F2)
        embed.add_field(
            name="Usage",
            value="`!invite [expire=Xt] [uses=N] [temp=bool] [@role ...]`",
            inline=False,
        )
        embed.add_field(
            name="Parameters",
            value=(
                "• `expire=Xt` — duration (e.g. `expire=1d`, `expire=2h30m`). Default: `1d`. `0` = never expires.\n"
                "• `uses=N` — max uses. Default: `0` (infinite).\n"
                "• `temp=bool` — `true`/`false`. Default: `false`. Temporary invites kick members after 24h if no role is given.\n"
                "• `@role ...` — optional roles to assign on join. Requires Manage Roles. Only roles below your highest role (owner can assign any)."
            ),
            inline=False,
        )
        embed.add_field(
            name="Examples",
            value=(
                "`!invite`\n"
                "`!invite expire=0 uses=0`\n"
                "`!invite expire=7d uses=50`\n"
                "`!invite temp=true @Member`"
            ),
            inline=False,
        )
        return embed

    async def _send_invite(self, message):
        if not self._can_create_invite(message.author):
            await message.add_reaction('❌')
            return True
        if not self._bot_can(message.guild, 'create_instant_invite'):
            await message.add_reaction('❌')
            return True
        max_age = 86400
        max_uses = 0
        temporary = False
        roles = []
        rest = message.content[len('!invite'):].strip()
        for tok in rest.split():
            low = tok.lower()
            if low.startswith('expire='):
                raw = tok[len('expire='):]
                if raw == '0':
                    max_age = 0
                else:
                    d = self._parse_duration(raw)
                    if d is None:
                        await message.add_reaction('❌')
                        return True
                    max_age = int(d.total_seconds())
            elif low.startswith('uses='):
                val = tok[len('uses='):]
                if not val.isdigit():
                    await message.add_reaction('❌')
                    return True
                max_uses = int(val)
            elif low.startswith('temp='):
                val = tok[len('temp='):].lower()
                if val in ('true', '1', 'yes'):
                    temporary = True
                elif val in ('false', '0', 'no'):
                    temporary = False
                else:
                    await message.add_reaction('❌')
                    return True
        for role in message.role_mentions:
            roles.append(role)
        if roles:
            if not self._is_owner(message.guild, message.author.id):
                actor_top = message.author.top_role.position
                for role in roles:
                    if role.position >= actor_top:
                        await message.add_reaction('❌')
                        return True
        payload = {
            'max_age': max_age,
            'max_uses': max_uses,
            'temporary': temporary,
            'unique': False,
            'reason': f"Invite created by {message.author}",
        }
        if roles:
            payload['role_ids'] = [str(r.id) for r in roles]
        url = f"https://discord.com/api/v10/channels/{message.channel.id}/invites"
        headers = {
            'Authorization': f"Bot {TOKEN}",
            'Content-Type': 'application/json',
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        code = data.get('code')
                        if code:
                            await message.channel.send(f"https://discord.gg/{code}")
                        else:
                            await message.add_reaction('❌')
                    else:
                        await message.add_reaction('❌')
        except Exception:
            await message.add_reaction('❌')
        return True

    async def _handle_nick(self, message):
        if not self._can_manage_nicknames(message.author):
            await message.add_reaction('❌')
            return True
        if not self._bot_can(message.guild, 'manage_nicknames'):
            await message.add_reaction('❌')
            return True
        rest = message.content[len('!nick'):].strip()
        if not rest:
            await message.add_reaction('❌')
            return True
        target = None
        new_nick = rest
        if message.mentions:
            target = message.mentions[0]
            for m in message.mentions:
                new_nick = new_nick.replace(f'<@{m.id}>', '').replace(f'<@!{m.id}>', '')
            new_nick = new_nick.strip()
        else:
            parts = rest.split(None, 1)
            if parts and parts[0].isdigit() and len(parts[0]) >= 15:
                candidate = message.guild.get_member(int(parts[0]))
                if candidate is not None:
                    target = candidate
                    new_nick = parts[1].strip() if len(parts) > 1 else ''
        if target is not None:
            if not self._can_act_on(message.author, target, message.guild):
                await message.add_reaction('❌')
                return True
        else:
            target = message.author
        if not new_nick:
            await message.add_reaction('❌')
            return True
        try:
            await target.edit(nick=new_nick)
            await message.add_reaction('✅')
        except Exception:
            await message.add_reaction('❌')
        return True

    def _setup_slash(self):
        @self.tree.command(name="slowmode", description="Set channel slowmode")
        @app_commands.describe(input="Slowmode in seconds (0-21600)")
        async def slash_slowmode(interaction: discord.Interaction, input: int):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if input < 0 or input > 21600:
                await interaction.followup.send("❌ Time must be between 0 and 21600 seconds.", ephemeral=True)
                return
            ok = await self._apply_slowmode(interaction.channel, input)
            if ok:
                await interaction.followup.send("✅", ephemeral=True)
            else:
                await interaction.followup.send("❌", ephemeral=True)

    async def handle_message(self, message):
        if message.guild is None:
            return False
        content = message.content.strip()
        lower = content.lower()

        bl_level = self._check_blacklist(message)
        if bl_level is not None:
            await self._apply_blacklist_action(message, bl_level)

        if lower.startswith('!blacklist'):
            if not self._can_manage_messages(message.author):
                await message.add_reaction('❌')
                return True
            rest = content[len('!blacklist'):].strip()
            if not rest:
                entries = sorted(self.blacklist.items())
                view = BlacklistView(entries)
                await view.send_to(message.channel)
                return True
            parts = rest.split()
            sub = parts[0].lower()
            if sub == 'add':
                if len(parts) < 2:
                    await message.add_reaction('❌')
                    return True
                word = parts[1].lower()
                level = parts[2].lower() if len(parts) >= 3 else 'low'
                if level not in BLACKLIST_LEVELS:
                    await message.add_reaction('❌')
                    return True
                if not self._can_set_level(message.author, level):
                    await message.add_reaction('❌')
                    return True
                self.blacklist[word] = level
                self._save_blacklist()
                await message.add_reaction('✅')
                return True
            if sub in ('rem', 'remove', 'del', 'delete'):
                if len(parts) < 2:
                    await message.add_reaction('❌')
                    return True
                word = parts[1].lower()
                if word in self.blacklist:
                    del self.blacklist[word]
                    self._save_blacklist()
                    await message.add_reaction('✅')
                else:
                    await message.add_reaction('❌')
                return True
            await message.add_reaction('❌')
            return True

        if lower.startswith('!userinfo'):
            user = self._resolve_user(message)
            try:
                await self._send_userinfo(message.channel, user)
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!invite'):
            rest = content[len('!invite'):].strip()
            if rest.lower() in ('help', '?', '-h', '--help'):
                await message.channel.send(embed=self._invite_help_embed())
                return True
            return await self._send_invite(message)

        if lower.startswith('!nick'):
            return await self._handle_nick(message)

        if lower.startswith('!slowmode'):
            rest = content[len('!slowmode'):].strip()
            if not rest or not rest.isdigit():
                await message.add_reaction('❌')
                return True
            if not self._can_manage_channels(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_channels'):
                await message.add_reaction('❌')
                return True
            seconds = int(rest)
            if seconds < 0 or seconds > 21600:
                await message.add_reaction('❌')
                return True
            ok = await self._apply_slowmode(message.channel, seconds)
            await message.add_reaction('✅' if ok else '❌')
            return True

        for cmd, action, emoji in (
            ('!lockchannel', self._apply_lock, '🔒'),
            ('!openchannel', self._apply_open, '🔓'),
            ('!hidechannel', self._apply_hide, '🔒'),
            ('!showchannel', self._apply_show, '🔓'),
        ):
            if lower.startswith(cmd):
                if not self._can_manage_channels(message.author):
                    await message.add_reaction('❌')
                    return True
                if not self._bot_can(message.guild, 'manage_channels'):
                    await message.add_reaction('❌')
                    return True
                rest = content[len(cmd):].strip()
                ids = self._extract_ids(rest)
                if ids:
                    channels = []
                    for cid in ids:
                        ch = message.guild.get_channel(cid)
                        if ch is not None and isinstance(ch, discord.TextChannel):
                            channels.append(ch)
                else:
                    channels = [message.channel]
                if not channels:
                    await message.add_reaction('❌')
                    return True
                ok_any = False
                for ch in channels:
                    ok = await action(ch)
                    if ok:
                        ok_any = True
                await message.add_reaction(emoji if ok_any else '❌')
                return True

        if lower.startswith('!cloneset'):
            if not self._can_manage_channels(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_channels'):
                await message.add_reaction('❌')
                return True
            rest = content[len('!cloneset'):].strip()
            ids = self._extract_ids(rest)
            if len(ids) != 1:
                await message.add_reaction('❌')
                return True
            source = message.guild.get_channel(ids[0])
            if source is None or not isinstance(source, discord.TextChannel):
                await message.add_reaction('❌')
                return True
            ok = await self._apply_clone(source, message.channel)
            await message.add_reaction('✅' if ok else '❌')
            return True

        if lower.startswith('!renamechannel'):
            rest = content[len('!renamechannel'):].strip()
            if not rest:
                await message.add_reaction('❌')
                return True
            if not self._can_manage_channels(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_channels'):
                await message.add_reaction('❌')
                return True
            try:
                await message.channel.edit(name=rest)
                await message.add_reaction('✅')
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!purge'):
            if not self._can_manage_messages(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_messages'):
                await message.add_reaction('❌')
                return True
            rest = content[len('!purge'):].strip()
            try:
                if message.reference is not None:
                    target_id = message.reference.message_id
                    to_delete = []
                    async for msg in message.channel.history(limit=None, after=discord.Object(id=target_id), oldest_first=False):
                        to_delete.append(msg)
                    try:
                        target_msg = await message.channel.fetch_message(target_id)
                        to_delete.append(target_msg)
                    except Exception:
                        pass
                    to_delete.append(message)
                    to_delete = [m for m in to_delete if not m.pinned]
                    now = discord.utils.utcnow()
                    bulk = [m for m in to_delete if (now - m.created_at).days < 14]
                    old = [m for m in to_delete if m not in bulk]
                    if 2 <= len(bulk) <= 100:
                        try:
                            await message.channel.delete_messages(bulk)
                        except Exception:
                            for m in bulk:
                                try:
                                    await m.delete()
                                except Exception:
                                    pass
                    else:
                        for m in bulk:
                            try:
                                await m.delete()
                            except Exception:
                                pass
                    for m in old:
                        try:
                            await m.delete()
                        except Exception:
                            pass
                    return True
                else:
                    if not rest.isdigit():
                        await message.add_reaction('❌')
                        return True
                    n = int(rest)
                    if n < 1 or n > 100:
                        await message.add_reaction('❌')
                        return True
                    await message.channel.purge(limit=n + 1)
                    return True
            except Exception:
                try:
                    await message.channel.send("❌", delete_after=3)
                except Exception:
                    pass
                return True

        if lower.startswith('!pin'):
            if not self._can_manage_messages(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_messages'):
                await message.add_reaction('❌')
                return True
            if message.reference is None:
                await message.add_reaction('❌')
                return True
            try:
                target = await message.channel.fetch_message(message.reference.message_id)
                if target.pinned:
                    await target.unpin()
                else:
                    await target.pin()
                await message.add_reaction('✅')
            except Exception:
                await message.add_reaction('❌')
            return True

        if lower.startswith('!kick'):
            if not self._can_moderate(message.author, 'kick_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'kick_members'):
                await message.add_reaction('❌')
                return True
            targets = self._resolve_targets(message)
            if not targets:
                await message.add_reaction('❌')
                return True
            ok_any = False
            for t in targets:
                if not self._can_act_on(message.author, t, message.guild):
                    continue
                ok = await self._apply_kick(t, f"Kicked by {message.author}")
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        if lower.startswith('!ban'):
            if not self._can_moderate(message.author, 'ban_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'ban_members'):
                await message.add_reaction('❌')
                return True
            targets = self._resolve_targets(message)
            if not targets:
                await message.add_reaction('❌')
                return True
            ok_any = False
            for t in targets:
                if not self._can_act_on(message.author, t, message.guild):
                    continue
                ok = await self._apply_ban(t, f"Banned by {message.author}")
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        if lower.startswith('!mute'):
            if not self._can_moderate(message.author, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            rest = content[len('!mute'):].strip()
            tokens = rest.split()
            duration = None
            for tok in tokens:
                d = self._parse_duration(tok)
                if d is not None:
                    duration = d
                    break
            if duration is None:
                await message.add_reaction('❌')
                return True
            targets = self._resolve_targets(message)
            if not targets:
                await message.add_reaction('❌')
                return True
            ok_any = False
            for t in targets:
                if not self._can_act_on(message.author, t, message.guild):
                    continue
                ok = await self._apply_mute(t, duration, f"Muted by {message.author}")
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        if lower.startswith('!unmute'):
            if not self._can_moderate(message.author, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            targets = self._resolve_targets(message)
            if not targets:
                await message.add_reaction('❌')
                return True
            ok_any = False
            for t in targets:
                if not self._can_act_on(message.author, t, message.guild):
                    continue
                ok = await self._apply_unmute(t)
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        if lower.startswith('!unban'):
            if not self._can_moderate(message.author, 'ban_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'ban_members'):
                await message.add_reaction('❌')
                return True
            rest = content[len('!unban'):].strip()
            ids = re.findall(r'\b(\d{15,20})\b', rest)
            if not ids:
                await message.add_reaction('❌')
                return True
            ok_any = False
            for uid in ids:
                ok = await self._apply_unban(message.guild, int(uid), f"Unbanned by {message.author}")
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        return False
