import discord
import json
import os
from datetime import datetime, timezone

INVITE_CACHE_FILE = "invite_cache.json"

class WelcomeSystem:
    def __init__(self, client, welcome_channel_id=None):
        self.client = client
        self.welcome_channel_id = welcome_channel_id
        self.invite_cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(INVITE_CACHE_FILE):
            try:
                with open(INVITE_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for gid, invites in data.items():
                        self.invite_cache[int(gid)] = invites
            except Exception:
                self.invite_cache = {}

    def _save_cache(self):
        with open(INVITE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self.invite_cache.items()}, f, indent=2)

    async def cache_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            self._save_cache()
        except discord.Forbidden:
            print(f"[WelcomeSystem] No permission to fetch invites for {guild.name}")

    async def _find_inviter(self, guild: discord.Guild):
        try:
            new_invites = await guild.invites()
        except discord.Forbidden:
            return None

        old_cache = self.invite_cache.get(guild.id, {})
        inviter = None

        for inv in new_invites:
            old_uses = old_cache.get(inv.code, 0)
            if inv.uses > old_uses and inv.inviter:
                inviter = inv.inviter
                break

        self.invite_cache[guild.id] = {inv.code: inv.uses for inv in new_invites}
        self._save_cache()
        return inviter

    async def _get_audit_action(self, guild: discord.Guild, target_id: int, action: discord.AuditLogAction):
        try:
            async for entry in guild.audit_logs(limit=5, action=action):
                if entry.target and entry.target.id == target_id:
                    delta = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                    if delta < 10:
                        return entry.user
        except discord.Forbidden:
            pass
        return None

    async def on_member_join(self, member: discord.Member):
        guild = member.guild

        if member.bot:
            adder = await self._get_audit_action(guild, member.id, discord.AuditLogAction.bot_add)

            embed = discord.Embed(
                title="Bot Added",
                description=f"{member.mention} was added to the server",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Bot ID", value=str(member.id), inline=False)
            embed.add_field(name="Username", value=str(member), inline=False)

            if adder:
                embed.add_field(name="Added by", value=f"{adder.mention} ({adder.id})", inline=False)

            embed.add_field(name="Total Members", value=str(guild.member_count), inline=False)
            embed.set_footer(text=f"Added at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

            channel = self.client.get_channel(self.welcome_channel_id) if self.welcome_channel_id else guild.system_channel
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass
            return

        inviter = await self._find_inviter(guild)

        embed = discord.Embed(
            title="Member Joined",
            description=f"{member.mention} joined the server",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User ID", value=str(member.id), inline=False)
        embed.add_field(name="Username", value=str(member), inline=False)

        if inviter:
            embed.add_field(name="Invited by", value=f"{inviter.mention} ({inviter.id})", inline=False)

        embed.add_field(name="Total Members", value=str(guild.member_count), inline=False)
        embed.set_footer(text=f"Joined at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        channel = self.client.get_channel(self.welcome_channel_id) if self.welcome_channel_id else guild.system_channel
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    async def on_member_remove(self, member: discord.Member):
        guild = member.guild

        kicker = await self._get_audit_action(guild, member.id, discord.AuditLogAction.kick)
        banner = None
        if not kicker:
            banner = await self._get_audit_action(guild, member.id, discord.AuditLogAction.ban)

        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} left the server",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User ID", value=str(member.id), inline=False)
        embed.add_field(name="Username", value=str(member), inline=False)

        if kicker:
            embed.add_field(name="Action", value=f"Kicked by {kicker.mention} ({kicker.id})", inline=False)
        elif banner:
            embed.add_field(name="Action", value=f"Banned by {banner.mention} ({banner.id})", inline=False)
        else:
            embed.add_field(name="Action", value="Left voluntarily", inline=False)

        embed.add_field(name="Total Members", value=str(guild.member_count), inline=False)
        embed.set_footer(text=f"Left at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

        channel = self.client.get_channel(self.welcome_channel_id) if self.welcome_channel_id else guild.system_channel
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass
