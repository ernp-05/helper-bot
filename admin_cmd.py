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

BUTTON_STYLES = {
    'primary': discord.ButtonStyle.primary,
    'secondary': discord.ButtonStyle.secondary,
    'success': discord.ButtonStyle.success,
    'danger': discord.ButtonStyle.danger,
}


def _parse_hex_color(value):
    if value is None:
        return None
    v = value.strip().lstrip('#').lower()
    if len(v) != 6:
        return None
    if not re.fullmatch(r'[0-9a-f]{6}', v):
        return None
    return int(v, 16)


def _normalize(content):
    if content is None:
        return ''
    s = content.strip()
    if not s.startswith('!'):
        return s
    s = s[1:].lstrip()
    return s.lower()


class DynamicRoleButton(discord.ui.DynamicItem[discord.ui.Button], template=r'role_(?P<id>\d+)_(?P<style>primary|secondary|success|danger)(?:_(?P<emoji>.+))?'):
    def __init__(self, role_id: int, label: str = "Role", style: str = "primary", emoji: str = None):
        super().__init__(
            discord.ui.Button(
                style=BUTTON_STYLES.get(style, discord.ButtonStyle.primary),
                label=label[:80],
                emoji=emoji or None,
                custom_id=f"role_{role_id}_{style}" + (f"_{emoji}" if emoji else ""),
            )
        )
        self.role_id = role_id
        self.style_name = style
        self.emoji = emoji

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match, /):
        role_id = int(match['id'])
        style = match['style'] or "primary"
        emoji = match['emoji'] or None
        label = item.label or "Role"
        return cls(role_id, label, style, emoji)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return
        me = guild.me
        if me is None or (not me.guild_permissions.administrator and not me.guild_permissions.manage_roles):
            await interaction.response.send_message("❌ I can't manage roles.", ephemeral=True)
            return
        if me.top_role.position <= role.position:
            await interaction.response.send_message("❌ That role is above my highest role.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌", ephemeral=True)
            return
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Role button (toggle)")
                await interaction.response.send_message(f"➖ Removed {role.mention}", ephemeral=True)
            else:
                await member.add_roles(role, reason="Role button (toggle)")
                await interaction.response.send_message(f"➕ Added {role.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to manage that role.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌", ephemeral=True)


class RoleButtonsView(discord.ui.View):
    def __init__(self, roles, style="primary", emoji=None):
        super().__init__(timeout=None)
        for role in roles[:25]:
            self.add_item(DynamicRoleButton(role.id, role.name, style, emoji))


class ImagePositionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="thumbnail", value="thumbnail", description="Small image at the top-right corner"),
            discord.SelectOption(label="image", value="image", description="Large image below the text"),
            discord.SelectOption(label="none", value="none", description="No image"),
        ]
        super().__init__(placeholder="Image position", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        pass


class SendMsgModal(discord.ui.Modal):
    def __init__(self, color, channel, roles, button_style, button_emoji, image_position="thumbnail"):
        super().__init__(title="Send message")
        self.color = color
        self.channel = channel
        self.roles = roles
        self.button_style = button_style
        self.button_emoji = button_emoji
        self.image_position_value = image_position
        self.text = discord.ui.TextInput(
            label="Text",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
        )
        self.image_url = discord.ui.TextInput(
            label="Image URL",
            style=discord.TextStyle.short,
            required=False,
            placeholder="https://...",
            max_length=512,
        )
        self.add_item(self.text)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        pos = self.image_position_value
        if pos not in ("thumbnail", "image", "none"):
            pos = "thumbnail"
        embed = discord.Embed(description=str(self.text.value), color=self.color)
        img = str(self.image_url.value).strip() if self.image_url.value else ""
        if img and pos != "none":
            if pos == "image":
                embed.set_image(url=img)
            else:
                embed.set_thumbnail(url=img)
        view = RoleButtonsView(self.roles, self.button_style, self.button_emoji) if self.roles else None
        try:
            await self.channel.send(embed=embed, view=view)
        except Exception:
            await interaction.response.send_message("❌ Could not send message.", ephemeral=True)
            return
        await interaction.response.send_message("✅", ephemeral=True)


class ImagePositionView(discord.ui.View):
    def __init__(self, color, channel, roles, button_style, button_emoji):
        super().__init__(timeout=120)
        self.color = color
        self.channel = channel
        self.roles = roles
        self.button_style = button_style
        self.button_emoji = button_emoji
        self.image_position = "thumbnail"

    @discord.ui.select(
        placeholder="Image position",
        options=[
            discord.SelectOption(label="thumbnail", value="thumbnail", description="Small image at the top-right corner"),
            discord.SelectOption(label="image", value="image", description="Large image below the text"),
            discord.SelectOption(label="none", value="none", description="No image"),
        ],
    )
    async def select_position(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.image_position = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SendMsgModal(
            self.color, self.channel, self.roles,
            self.button_style, self.button_emoji, self.image_position
        )
        await interaction.response.send_modal(modal)


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
        try:
            self.bot.add_dynamic_items(DynamicRoleButton)
        except Exception:
            pass

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

    def _is_guild_owner(self, guild, user_id):
        if guild is None:
            return False
        return guild.owner_id == user_id

    def _can_manage_channels(self, member):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_channels

    def _can_moderate(self, member, perm_name):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        if p.administrator:
            return True
        return getattr(p, perm_name, False)

    def _can_manage_messages(self, member):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_messages

    def _can_manage_nicknames(self, member):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_nicknames

    def _can_create_invite(self, member):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        return p.administrator or p.create_instant_invite

    def _can_manage_roles(self, member):
        if member is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_roles

    def _bot_can(self, guild, perm_name):
        if guild is None or guild.me is None:
            return False
        p = guild.me.guild_permissions
        if p.administrator:
            return True
        return getattr(p, perm_name, False)

    def _can_act_on(self, actor, target, guild):
        if guild is None or target is None or actor is None:
            return False
        if target.id == self.bot.user.id:
            return False
        if target.id == actor.id:
            return False
        if not self._is_guild_owner(guild, actor.id):
            if not actor.guild_permissions.administrator:
                actor_top = actor.top_role.position if hasattr(actor, 'top_role') else -1
                target_top = target.top_role.position if hasattr(target, 'top_role') else -1
                if actor_top <= target_top:
                    return False
        bot_member = guild.me or guild.get_member(self.bot.user.id)
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
        p = member.guild_permissions
        if p.administrator:
            return "Admin"
        if p.manage_messages or p.manage_channels or p.kick_members or p.ban_members:
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
        if member is None:
            return False
        if level in ('low', 'high'):
            return self._can_manage_messages(member)
        perm = self._level_perm_required(level)
        if perm is None:
            return False
        if self._is_guild_owner(member.guild, member.id):
            return True
        p = member.guild_permissions
        if p.administrator:
            return True
        return getattr(p, perm, False)

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
                "• `@role ...` — optional roles to assign on join. Requires Manage Roles. Only roles below your highest role."
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

    async def _send_invite(self, message, rest):
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
            if not self._is_guild_owner(message.guild, message.author.id):
                if not message.author.guild_permissions.administrator:
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

    async def _handle_nick(self, message, rest):
        if not self._can_manage_nicknames(message.author):
            await message.add_reaction('❌')
            return True
        if not self._bot_can(message.guild, 'manage_nicknames'):
            await message.add_reaction('❌')
            return True
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
        if target is None:
            target = message.author
        if not new_nick:
            await message.add_reaction('❌')
            return True
        if target.id != message.author.id:
            if not self._can_act_on(message.author, target, message.guild):
                await message.add_reaction('❌')
                return True
        try:
            await target.edit(nick=new_nick)
            await message.add_reaction('✅')
        except discord.Forbidden as e:
            print(f"NICK FORBIDDEN: {e}")
            await message.add_reaction('❌')
        except Exception as e:
            print(f"NICK ERROR: {e}")
            await message.add_reaction('❌')
        return True

    def _setup_slash(self):
        tree = self.tree

        @tree.command(name="slowmode", description="Set channel slowmode")
        @app_commands.describe(seconds="Slowmode in seconds (0-21600)", channel="Target channel (default: current)")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_slowmode(interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            target = channel or interaction.channel
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if seconds < 0 or seconds > 21600:
                await interaction.followup.send("❌ Time must be between 0 and 21600 seconds.", ephemeral=True)
                return
            ok = await self._apply_slowmode(target, seconds)
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="lockchannel", description="Lock channels")
        @app_commands.describe(channels="Space-separated channel IDs (default: current)")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_lock(interaction: discord.Interaction, channels: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            targets = self._slash_channels(interaction, channels) or [interaction.channel]
            ok_any = False
            for ch in targets:
                if await self._apply_lock(ch):
                    ok_any = True
            await interaction.followup.send("🔒" if ok_any else "❌", ephemeral=True)

        @tree.command(name="openchannel", description="Open channels")
        @app_commands.describe(channels="Space-separated channel IDs (default: current)")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_open(interaction: discord.Interaction, channels: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            targets = self._slash_channels(interaction, channels) or [interaction.channel]
            ok_any = False
            for ch in targets:
                if await self._apply_open(ch):
                    ok_any = True
            await interaction.followup.send("🔓" if ok_any else "❌", ephemeral=True)

        @tree.command(name="hidechannel", description="Hide channels")
        @app_commands.describe(channels="Space-separated channel IDs (default: current)")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_hide(interaction: discord.Interaction, channels: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            targets = self._slash_channels(interaction, channels) or [interaction.channel]
            ok_any = False
            for ch in targets:
                if await self._apply_hide(ch):
                    ok_any = True
            await interaction.followup.send("🔒" if ok_any else "❌", ephemeral=True)

        @tree.command(name="showchannel", description="Show channels")
        @app_commands.describe(channels="Space-separated channel IDs (default: current)")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_show(interaction: discord.Interaction, channels: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            targets = self._slash_channels(interaction, channels) or [interaction.channel]
            ok_any = False
            for ch in targets:
                if await self._apply_show(ch):
                    ok_any = True
            await interaction.followup.send("🔓" if ok_any else "❌", ephemeral=True)

        @tree.command(name="cloneset", description="Copy overwrites from a channel to the current one")
        @app_commands.describe(source_id="Source channel ID")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_cloneset(interaction: discord.Interaction, source_id: str):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            try:
                src = interaction.guild.get_channel(int(source_id))
            except Exception:
                src = None
            if src is None or not isinstance(src, discord.TextChannel):
                await interaction.followup.send("❌ Invalid source channel.", ephemeral=True)
                return
            ok = await self._apply_clone(src, interaction.channel)
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="renamechannel", description="Rename the current channel")
        @app_commands.describe(name="New name")
        @app_commands.default_permissions(manage_channels=True)
        async def slash_rename(interaction: discord.Interaction, name: str):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_channels'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            try:
                await interaction.channel.edit(name=name)
                await interaction.followup.send("✅", ephemeral=True)
            except Exception:
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="purge", description="Delete the last N messages")
        @app_commands.describe(amount="Number of messages (1-100)")
        @app_commands.default_permissions(manage_messages=True)
        async def slash_purge(interaction: discord.Interaction, amount: int):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_messages(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_messages'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if amount < 1 or amount > 100:
                await interaction.followup.send("❌ Amount must be between 1 and 100.", ephemeral=True)
                return
            try:
                await interaction.channel.purge(limit=amount, bulk=False)
                await interaction.followup.send(f"✅ Deleted {amount}", ephemeral=True)
            except Exception:
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="pin", description="Pin or unpin the given message ID")
        @app_commands.describe(message_id="Message ID")
        @app_commands.default_permissions(manage_messages=True)
        async def slash_pin(interaction: discord.Interaction, message_id: str):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_messages(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'manage_messages'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            try:
                msg = await interaction.channel.fetch_message(int(message_id))
                if msg.pinned:
                    await msg.unpin()
                else:
                    await msg.pin()
                await interaction.followup.send("✅", ephemeral=True)
            except Exception:
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="kick", description="Kick a member")
        @app_commands.describe(member="Member to kick", reason="Reason")
        @app_commands.default_permissions(kick_members=True)
        async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_moderate(interaction.user, 'kick_members'):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'kick_members'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if not self._can_act_on(interaction.user, member, interaction.guild):
                await interaction.followup.send("❌ Can't act on that member.", ephemeral=True)
                return
            ok = await self._apply_kick(member, reason or f"Kicked by {interaction.user}")
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="ban", description="Ban a member")
        @app_commands.describe(member="Member to ban", reason="Reason")
        @app_commands.default_permissions(ban_members=True)
        async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_moderate(interaction.user, 'ban_members'):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'ban_members'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if not self._can_act_on(interaction.user, member, interaction.guild):
                await interaction.followup.send("❌ Can't act on that member.", ephemeral=True)
                return
            ok = await self._apply_ban(member, reason or f"Banned by {interaction.user}")
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="mute", description="Timeout a member")
        @app_commands.describe(member="Member to mute", duration="e.g. 10m, 1h, 1d", reason="Reason")
        @app_commands.default_permissions(moderate_members=True)
        async def slash_mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_moderate(interaction.user, 'moderate_members'):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'moderate_members'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            d = self._parse_duration(duration)
            if d is None:
                await interaction.followup.send("❌ Invalid duration.", ephemeral=True)
                return
            if not self._can_act_on(interaction.user, member, interaction.guild):
                await interaction.followup.send("❌ Can't act on that member.", ephemeral=True)
                return
            ok = await self._apply_mute(member, d, reason or f"Muted by {interaction.user}")
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="unmute", description="Remove timeout from a member")
        @app_commands.describe(member="Member to unmute")
        @app_commands.default_permissions(moderate_members=True)
        async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
            await interaction.response.defer(ephemeral=True)
            if not self._can_moderate(interaction.user, 'moderate_members'):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'moderate_members'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            ok = await self._apply_unmute(member)
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="unban", description="Unban a user")
        @app_commands.describe(user_id="User ID to unban", reason="Reason")
        @app_commands.default_permissions(ban_members=True)
        async def slash_unban(interaction: discord.Interaction, user_id: str, reason: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_moderate(interaction.user, 'ban_members'):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'ban_members'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            if not user_id.isdigit():
                await interaction.followup.send("❌ Invalid user ID.", ephemeral=True)
                return
            ok = await self._apply_unban(interaction.guild, int(user_id), reason or f"Unbanned by {interaction.user}")
            await interaction.followup.send("✅" if ok else "❌", ephemeral=True)

        @tree.command(name="nick", description="Change a member's nickname")
        @app_commands.describe(member="Member (default: yourself)", nickname="New nickname")
        @app_commands.default_permissions(manage_nicknames=True)
        async def slash_nick(interaction: discord.Interaction, nickname: str, member: discord.Member = None):
            await interaction.response.defer(ephemeral=True)
            target = member or interaction.user
            if target.id != interaction.user.id:
                if not self._can_manage_nicknames(interaction.user):
                    await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                    return
                if not self._can_act_on(interaction.user, target, interaction.guild):
                    await interaction.followup.send("❌ Can't act on that member.", ephemeral=True)
                    return
            if not self._bot_can(interaction.guild, 'manage_nicknames'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            try:
                await target.edit(nick=nickname)
                await interaction.followup.send("✅", ephemeral=True)
            except discord.Forbidden as e:
                print(f"NICK FORBIDDEN: {e}")
                await interaction.followup.send("❌", ephemeral=True)
            except Exception as e:
                print(f"NICK ERROR: {e}")
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="userinfo", description="Show user info")
        @app_commands.describe(user="User (default: yourself)")
        async def slash_userinfo(interaction: discord.Interaction, user: discord.User = None):
            await interaction.response.defer(ephemeral=True)
            target = user or interaction.user
            try:
                await self._send_userinfo(interaction.channel, target)
            except Exception:
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="invite", description="Create an invite")
        @app_commands.describe(expire="e.g. 1d, 2h30m, or 0 for never", uses="Max uses, 0 = infinite", temporary="Temporary invite", role="Role to grant on join")
        @app_commands.default_permissions(create_instant_invite=True)
        async def slash_invite(interaction: discord.Interaction, expire: str = None, uses: int = None, temporary: bool = None, role: discord.Role = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_create_invite(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            if not self._bot_can(interaction.guild, 'create_instant_invite'):
                await interaction.followup.send("❌ I don't have permission.", ephemeral=True)
                return
            max_age = 86400
            if expire is not None:
                if expire == '0':
                    max_age = 0
                else:
                    d = self._parse_duration(expire)
                    if d is None:
                        await interaction.followup.send("❌ Invalid expire.", ephemeral=True)
                        return
                    max_age = int(d.total_seconds())
            max_uses = 0 if uses is None else max(0, int(uses))
            temp_flag = bool(temporary) if temporary is not None else False
            roles = [role] if role is not None else []
            if roles:
                if not self._is_guild_owner(interaction.guild, interaction.user.id):
                    if not interaction.user.guild_permissions.administrator:
                        if interaction.user.top_role.position <= role.position:
                            await interaction.followup.send("❌ Role is not below your highest role.", ephemeral=True)
                            return
            payload = {
                'max_age': max_age,
                'max_uses': max_uses,
                'temporary': temp_flag,
                'unique': False,
                'reason': f"Invite created by {interaction.user}",
            }
            if roles:
                payload['role_ids'] = [str(r.id) for r in roles]
            url = f"https://discord.com/api/v10/channels/{interaction.channel.id}/invites"
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
                                await interaction.followup.send(f"https://discord.gg/{code}", ephemeral=True)
                            else:
                                await interaction.followup.send("❌", ephemeral=True)
                        else:
                            await interaction.followup.send("❌", ephemeral=True)
            except Exception:
                await interaction.followup.send("❌", ephemeral=True)

        @tree.command(name="blacklist", description="Manage the blacklist")
        @app_commands.describe(action="list / add / remove", word="Word (for add/remove)", level="low / high / mute / kick / ban")
        @app_commands.default_permissions(manage_messages=True)
        async def slash_blacklist(interaction: discord.Interaction, action: str = "list", word: str = None, level: str = None):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_messages(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            act = action.lower().strip()
            if act in ("list", "show", ""):
                entries = sorted(self.blacklist.items())
                view = BlacklistView(entries)
                view.update_buttons()
                await interaction.followup.send(embed=view.build_embed(), view=view if entries else None, ephemeral=True)
                return
            if act == "add":
                if not word:
                    await interaction.followup.send("❌ Missing word.", ephemeral=True)
                    return
                lvl = (level or "low").lower()
                if lvl not in BLACKLIST_LEVELS:
                    await interaction.followup.send("❌ Invalid level.", ephemeral=True)
                    return
                if not self._can_set_level(interaction.user, lvl):
                    await interaction.followup.send("❌ You can't set that level.", ephemeral=True)
                    return
                self.blacklist[word.lower()] = lvl
                self._save_blacklist()
                await interaction.followup.send(f"✅ `{word.lower()}` → **{lvl}**", ephemeral=True)
                return
            if act in ("remove", "rem", "del", "delete"):
                if not word:
                    await interaction.followup.send("❌ Missing word.", ephemeral=True)
                    return
                if word.lower() in self.blacklist:
                    del self.blacklist[word.lower()]
                    self._save_blacklist()
                    await interaction.followup.send(f"✅ Removed `{word.lower()}`", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Not found.", ephemeral=True)
                return
            await interaction.followup.send("❌ Unknown action.", ephemeral=True)

        @tree.command(name="sendmsg", description="Send a message as the bot")
        @app_commands.describe(
            color="Hex color (000000-FFFFFF, optional #)",
            channel="Target channel ID (default: current)",
            role_text="Space-separated button labels for role buttons",
            role_id="Space-separated role IDs matching role_text",
            button_style="primary / secondary / success / danger",
            button_emoji="Emoji for role buttons (optional)",
        )
        @app_commands.default_permissions(manage_channels=True)
        @app_commands.choices(button_style=[
            app_commands.Choice(name="primary", value="primary"),
            app_commands.Choice(name="secondary", value="secondary"),
            app_commands.Choice(name="success", value="success"),
            app_commands.Choice(name="danger", value="danger"),
        ])
        async def slash_sendmsg(
            interaction: discord.Interaction,
            color: str = "5865F2",
            channel: str = None,
            role_text: str = None,
            role_id: str = None,
            button_style: app_commands.Choice[str] = None,
            button_emoji: str = None,
        ):
            await interaction.response.defer(ephemeral=True)
            if not self._can_manage_channels(interaction.user):
                await interaction.followup.send("❌ You don't have permission.", ephemeral=True)
                return
            parsed_color = _parse_hex_color(color)
            if parsed_color is None:
                await interaction.followup.send("❌ Invalid color. Use 000000-FFFFFF.", ephemeral=True)
                return
            target = interaction.channel
            if channel:
                try:
                    target = interaction.guild.get_channel(int(channel.strip()))
                except Exception:
                    target = None
                if target is None or not isinstance(target, discord.TextChannel):
                    await interaction.followup.send("❌ Invalid channel ID.", ephemeral=True)
                    return
            style_value = button_style.value if button_style else "primary"
            emoji_value = button_emoji.strip() if button_emoji else None
            roles = []
            if role_text or role_id:
                texts = role_text.split() if role_text else []
                ids = role_id.split() if role_id else []
                if len(texts) != len(ids):
                    await interaction.followup.send("❌ role_text and role_id must have the same number of items.", ephemeral=True)
                    return
                if len(texts) > 25:
                    await interaction.followup.send("❌ Maximum 25 roles.", ephemeral=True)
                    return
                if not self._can_manage_roles(interaction.user):
                    await interaction.followup.send("❌ You need Manage Roles to add role buttons.", ephemeral=True)
                    return
                if not self._bot_can(interaction.guild, 'manage_roles'):
                    await interaction.followup.send("❌ I need Manage Roles to add role buttons.", ephemeral=True)
                    return
                me = interaction.guild.me
                for rid in ids:
                    if not rid.isdigit():
                        await interaction.followup.send(f"❌ Invalid role ID: {rid}", ephemeral=True)
                        return
                    role = interaction.guild.get_role(int(rid))
                    if role is None:
                        await interaction.followup.send(f"❌ Role not found: {rid}", ephemeral=True)
                        return
                    if not self._is_guild_owner(interaction.guild, interaction.user.id):
                        if not interaction.user.guild_permissions.administrator:
                            if interaction.user.top_role.position <= role.position:
                                await interaction.followup.send(f"❌ Role {role.name} is not below your highest role.", ephemeral=True)
                                return
                    if me is None or me.top_role.position <= role.position:
                        await interaction.followup.send(f"❌ Role {role.name} is above my highest role.", ephemeral=True)
                        return
                    if role.managed:
                        await interaction.followup.send(f"❌ Role {role.name} is managed by an integration.", ephemeral=True)
                        return
                    roles.append(role)
            view = ImagePositionView(parsed_color, target, roles, style_value, emoji_value)
            await interaction.followup.send(
                "Elige la posición de la imagen y pulsa Continue:",
                view=view,
                ephemeral=True
            )

    def _slash_channels(self, interaction, channels_arg):
        if not channels_arg:
            return []
        out = []
        for tok in channels_arg.split():
            try:
                cid = int(tok.strip('<#>'))
            except Exception:
                continue
            ch = interaction.guild.get_channel(cid)
            if isinstance(ch, discord.TextChannel):
                out.append(ch)
        return out

    async def handle_message(self, message):
        if message.guild is None:
            return False
        if not message.content:
            return False
        stripped = message.content.strip()
        if not stripped.startswith('!'):
            return False
        normalized = _normalize(stripped)
        if not normalized:
            return False

        bl_level = self._check_blacklist(message)
        if bl_level is not None:
            await self._apply_blacklist_action(message, bl_level)

        if normalized.startswith('blacklist'):
            if not self._can_manage_messages(message.author):
                await message.add_reaction('❌')
                return True
            rest = normalized[len('blacklist'):].strip()
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

        if normalized.startswith('userinfo'):
            user = self._resolve_user(message)
            try:
                await self._send_userinfo(message.channel, user)
            except Exception:
                await message.add_reaction('❌')
            return True

        if normalized.startswith('invite'):
            rest = normalized[len('invite'):].strip()
            if rest in ('help', '?', '-h', '--help'):
                await message.channel.send(embed=self._invite_help_embed())
                return True
            return await self._send_invite(message, rest)

        if normalized.startswith('nick'):
            rest = stripped[stripped.lower().index('nick') + 4:].strip()
            return await self._handle_nick(message, rest)

        if normalized.startswith('slowmode'):
            rest = normalized[len('slowmode'):].strip()
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
            ('lockchannel', self._apply_lock, '🔒'),
            ('openchannel', self._apply_open, '🔓'),
            ('hidechannel', self._apply_hide, '🔒'),
            ('showchannel', self._apply_show, '🔓'),
        ):
            if normalized.startswith(cmd):
                if not self._can_manage_channels(message.author):
                    await message.add_reaction('❌')
                    return True
                if not self._bot_can(message.guild, 'manage_channels'):
                    await message.add_reaction('❌')
                    return True
                rest = normalized[len(cmd):].strip()
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

        if normalized.startswith('cloneset'):
            if not self._can_manage_channels(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_channels'):
                await message.add_reaction('❌')
                return True
            rest = normalized[len('cloneset'):].strip()
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

        if normalized.startswith('renamechannel'):
            rest = stripped[stripped.lower().index('renamechannel') + len('renamechannel'):].strip()
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

        if normalized.startswith('purge'):
            if not self._can_manage_messages(message.author):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'manage_messages'):
                await message.add_reaction('❌')
                return True
            rest = normalized[len('purge'):].strip()
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
                    for m in to_delete:
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
                    await message.channel.purge(limit=n + 1, bulk=False)
                    return True
            except Exception:
                try:
                    await message.channel.send("❌", delete_after=3)
                except Exception:
                    pass
                return True

        if normalized.startswith('pin'):
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

        if normalized.startswith('kick'):
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

        if normalized.startswith('ban'):
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

        if normalized.startswith('mute'):
            if not self._can_moderate(message.author, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'moderate_members'):
                await message.add_reaction('❌')
                return True
            rest = normalized[len('mute'):].strip()
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

        if normalized.startswith('unmute'):
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

        if normalized.startswith('unban'):
            if not self._can_moderate(message.author, 'ban_members'):
                await message.add_reaction('❌')
                return True
            if not self._bot_can(message.guild, 'ban_members'):
                await message.add_reaction('❌')
                return True
            rest = normalized[len('unban'):].strip()
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
