import re
import asyncio
import discord
from discord import app_commands
from datetime import timedelta


class AdminCommands:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree
        self._setup_slash()

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
                ok = await self._apply_kick(t, None)
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
                ok = await self._apply_ban(t, None)
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
                ok = await self._apply_mute(t, duration, None)
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
                ok = await self._apply_unban(message.guild, int(uid), None)
                if ok:
                    ok_any = True
            await message.add_reaction('✅' if ok_any else '❌')
            return True

        return False
