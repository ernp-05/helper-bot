# minigames/hi_lo.py
import asyncio
import random
import discord
from discord import ui

RANKS = {
    1: 'A', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7',
    8: '8', 9: '9', 10: '10', 11: 'J', 12: 'Q', 13: 'K'
}
SUITS = {
    'clubs': '♣️',
    'diamonds': '♦️',
    'hearts': '♥️',
    'spades': '♠️'
}

CARD_URLS = {
    "clubs_1_ace.webp": "https://cdn.imgchest.com/files/6a3f7057be03.webp",
    "clubs_2.webp": "https://cdn.imgchest.com/files/aa575d6681dd.webp",
    "clubs_3.webp": "https://cdn.imgchest.com/files/eb9e40b6a2fa.webp",
    "clubs_4.webp": "https://cdn.imgchest.com/files/f1a5b35f166a.webp",
    "clubs_5.webp": "https://cdn.imgchest.com/files/be82c133b33e.webp",
    "clubs_6.webp": "https://cdn.imgchest.com/files/6fdde68d0777.webp",
    "clubs_7.webp": "https://cdn.imgchest.com/files/faca0c7a9010.webp",
    "clubs_8.webp": "https://cdn.imgchest.com/files/b58c03ec34cf.webp",
    "clubs_9.webp": "https://cdn.imgchest.com/files/b22cc7532200.webp",
    "clubs_10.webp": "https://cdn.imgchest.com/files/993d39fadc1b.webp",
    "clubs_11_jack.webp": "https://cdn.imgchest.com/files/390b3dbcb2fd.webp",
    "clubs_12_queen.webp": "https://cdn.imgchest.com/files/d61a61382bb8.webp",
    "clubs_13_king.webp": "https://cdn.imgchest.com/files/fe991b683f9e.webp",
    "diamonds_1_ace.webp": "https://cdn.imgchest.com/files/11289076f3d7.webp",
    "diamonds_2.webp": "https://cdn.imgchest.com/files/373c59f986cd.webp",
    "diamonds_3.webp": "https://cdn.imgchest.com/files/23aa7b0de76c.webp",
    "diamonds_4.webp": "https://cdn.imgchest.com/files/cd40f18bc05d.webp",
    "diamonds_5.webp": "https://cdn.imgchest.com/files/455f390b4b3b.webp",
    "diamonds_6.webp": "https://cdn.imgchest.com/files/a68b634bdd17.webp",
    "diamonds_7.webp": "https://cdn.imgchest.com/files/1fbb536830a0.webp",
    "diamonds_8.webp": "https://cdn.imgchest.com/files/087247eae0fb.webp",
    "diamonds_9.webp": "https://cdn.imgchest.com/files/d398813aa387.webp",
    "diamonds_10.webp": "https://cdn.imgchest.com/files/c9b9a15dfa7c.webp",
    "diamonds_11_jack.webp": "https://cdn.imgchest.com/files/5c29e5641ecd.webp",
    "diamonds_12_queen.webp": "https://cdn.imgchest.com/files/f28f29fa6cdf.webp",
    "diamonds_13_king.webp": "https://cdn.imgchest.com/files/352e97850d19.webp",
    "hearts_1_ace.webp": "https://cdn.imgchest.com/files/a6becff6cbd6.webp",
    "hearts_2.webp": "https://cdn.imgchest.com/files/51b6b01d3cfb.webp",
    "hearts_3.webp": "https://cdn.imgchest.com/files/d3d4fbcd6b19.webp",
    "hearts_4.webp": "https://cdn.imgchest.com/files/39661efc2aca.webp",
    "hearts_5.webp": "https://cdn.imgchest.com/files/1c9396ab02f2.webp",
    "hearts_6.webp": "https://cdn.imgchest.com/files/193b6309bddb.webp",
    "hearts_7.webp": "https://cdn.imgchest.com/files/31b9d999638c.webp",
    "hearts_8.webp": "https://cdn.imgchest.com/files/b193d92114de.webp",
    "hearts_9.webp": "https://cdn.imgchest.com/files/702f1021530d.webp",
    "hearts_10.webp": "https://cdn.imgchest.com/files/b21df172d717.webp",
    "hearts_11_jack.webp": "https://cdn.imgchest.com/files/cb707198f7e8.webp",
    "hearts_12_queen.webp": "https://cdn.imgchest.com/files/2e701dd860f4.webp",
    "hearts_13_king.webp": "https://cdn.imgchest.com/files/836f2c4031f6.webp",
    "spades_1_ace.webp": "https://cdn.imgchest.com/files/bb8927c25b42.webp",
    "spades_2.webp": "https://cdn.imgchest.com/files/ad00c224b9fe.webp",
    "spades_3.webp": "https://cdn.imgchest.com/files/4d12f563c7c3.webp",
    "spades_4.webp": "https://cdn.imgchest.com/files/d8f97b93f583.webp",
    "spades_5.webp": "https://cdn.imgchest.com/files/21e6ddc42b95.webp",
    "spades_6.webp": "https://cdn.imgchest.com/files/76c5384739c9.webp",
    "spades_7.webp": "https://cdn.imgchest.com/files/5e3f83e9d46c.webp",
    "spades_8.webp": "https://cdn.imgchest.com/files/d7e057df3643.webp",
    "spades_9.webp": "https://cdn.imgchest.com/files/f27efee297e1.webp",
    "spades_10.webp": "https://cdn.imgchest.com/files/2f6f558f1ffa.webp",
    "spades_11_jack.webp": "https://cdn.imgchest.com/files/412c16e2abf8.webp",
    "spades_12_queen.webp": "https://cdn.imgchest.com/files/ec1337e501ac.webp",
    "spades_13_king.webp": "https://cdn.imgchest.com/files/03da8d396e03.webp",
}


def card_filename(rank, suit):
    if rank == 1:
        suffix = 'ace'
    elif rank == 11:
        suffix = 'jack'
    elif rank == 12:
        suffix = 'queen'
    elif rank == 13:
        suffix = 'king'
    else:
        suffix = str(rank)
    return f"{suit}_{rank}_{suffix}.webp" if suffix != str(rank) else f"{suit}_{rank}.webp"


def card_label(rank, suit):
    return f"{RANKS[rank]}{SUITS[suit]}"


def build_deck():
    deck = []
    for suit in SUITS:
        for rank in RANKS:
            deck.append((rank, suit))
    random.shuffle(deck)
    for i in range(1, len(deck)):
        if deck[i][0] == deck[i - 1][0]:
            for j in range(i + 1, len(deck)):
                if deck[j][0] != deck[i - 1][0]:
                    deck[i], deck[j] = deck[j], deck[i]
                    break
    return deck


class HiLoButton(ui.Button):
    def __init__(self, label, choice, game):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=f"hilo_{choice}")
        self.choice = choice
        self.game = game

    async def callback(self, interaction: discord.Interaction):
        await self.game.handle_choice(interaction, self.choice)


class HiLoView(ui.View):
    def __init__(self, game):
        super().__init__(timeout=86400)
        self.game = game
        self.add_item(HiLoButton("Higher", "higher", game))
        self.add_item(HiLoButton("Lower", "lower", game))

    async def on_timeout(self):
        try:
            if self.game.message is not None:
                await self.game.message.edit(content="⌛ Game timed out.", view=None)
        except Exception:
            pass


class HiLoGame:
    def __init__(self, bot, channel, player, mode, lives, opponent=None, ai=None):
        self.bot = bot
        self.channel = channel
        self.player = player
        self.mode = mode
        self.lives = lives
        self.opponent = opponent
        self.ai = ai
        self.deck = build_deck()
        self.index = 0
        self.message = None
        self.view = HiLoView(self)
        self.points = {player.id: 0}
        if opponent is not None:
            self.points[opponent.id] = 0
        self.turn = player.id
        self.bot_knows_all = random.random() < 0.0001
        self.bot_knows_next = random.random() < 0.02
        self.finished = False

    def current_card(self):
        if self.index < len(self.deck):
            return self.deck[self.index]
        return None

    def next_card(self):
        if self.index + 1 < len(self.deck):
            return self.deck[self.index + 1]
        return None

    def _display(self):
        card = self.current_card()
        if card is None:
            return "No cards left."
        rank, suit = card
        title = card_label(rank, suit)
        filename = card_filename(rank, suit)
        url = CARD_URLS.get(filename)

        embed = discord.Embed(title=title, color=0x5865F2)
        if url:
            embed.set_image(url=url)

        if self.opponent is None:
            lines = [f"♥️ = {self.lives}"]
            if self.ai is not None:
                lines.append(f"Points: {self.points[self.player.id]}")
            embed.description = "\n".join(lines)
        else:
            p1 = self.player.display_name
            p2 = self.opponent.display_name
            lines = [f"**{p1}**: {self.points[self.player.id]}",
                     f"**{p2}**: {self.points[self.opponent.id]}"]
            if self.turn == self.player.id:
                lines.append(f"Turn: **{p1}**")
            else:
                lines.append(f"Turn: **{p2}**")
            embed.description = "\n".join(lines)

        return embed

    def _check_game_over(self):
        if self.mode == 'survival':
            while self.index + 1 >= len(self.deck):
                self._extend_deck()
            return None

        if self.index + 1 >= len(self.deck):
            if self.opponent is not None:
                p1 = self.points[self.player.id]
                p2 = self.points[self.opponent.id]
                if p1 > p2:
                    winner = self.player.display_name
                elif p2 > p1:
                    winner = self.opponent.display_name
                else:
                    winner = "Draw"
                return f"Game over. Winner: **{winner}**" if winner != "Draw" else "Game over. Draw!"
            else:
                return f"Game over. Points: **{self.points[self.player.id]}**"
        return None

    def _extend_deck(self):
        extra = build_deck()
        self.deck.extend(extra)

    async def start(self):
        if self.ai is not None and self.ai == 'first':
            await self._play_ai_first()
            return
        await self._send_initial()

    async def _send_initial(self):
        embed = self._display()
        self.message = await self.channel.send(embed=embed, view=self.view, allowed_mentions=discord.AllowedMentions.none())
        await self._maybe_ai_turn()

    async def _play_ai_first(self):
        embed = self._display()
        self.message = await self.channel.send(embed=embed, view=self.view, allowed_mentions=discord.AllowedMentions.none())
        await asyncio.sleep(1)
        await self._ai_move()

    async def handle_choice(self, interaction, choice):
        if self.finished:
            await interaction.response.send_message("❌ Game is over.", ephemeral=True)
            return
        if self.ai is not None:
            await interaction.response.send_message("❌ You're playing against the bot. Wait for its turn.", ephemeral=True)
            return
        if self.opponent is not None and interaction.user.id not in (self.player.id, self.opponent.id):
            await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            return
        if self.opponent is not None and interaction.user.id != self.turn:
            await interaction.response.send_message("❌ Not your turn.", ephemeral=True)
            return
        if self.opponent is None and interaction.user.id != self.player.id:
            await interaction.response.send_message("❌ Not your game.", ephemeral=True)
            return
        await self._resolve(interaction, choice, interaction.user.id)

    async def _resolve(self, interaction, choice, user_id):
        current = self.current_card()
        nxt = self.next_card()
        if current is None or nxt is None:
            return
        correct = (nxt[0] > current[0] and choice == 'higher') or (nxt[0] < current[0] and choice == 'lower')
        self.index += 1

        if correct:
            self.points[user_id] = self.points.get(user_id, 0) + 1
        else:
            if self.opponent is None:
                self.lives -= 1
            else:
                self.turn = self.opponent.id if user_id == self.player.id else self.player.id

        if self.opponent is None and self.lives <= 0:
            self.finished = True
            embed = self._display()
            embed.description = f"Game over. Points: **{self.points[user_id]}**"
            try:
                if interaction is not None:
                    await interaction.response.edit_message(embed=embed, view=None)
                else:
                    await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
            return

        over = self._check_game_over()
        if over is not None:
            self.finished = True
            embed = self._display()
            embed.description = over
            try:
                if interaction is not None:
                    await interaction.response.edit_message(embed=embed, view=None)
                else:
                    await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
            return

        embed = self._display()
        try:
            if interaction is not None:
                await interaction.response.edit_message(embed=embed, view=self.view)
            else:
                await self.message.edit(embed=embed, view=self.view)
        except Exception:
            pass

        if self.ai is not None:
            await self._maybe_ai_turn()

    async def _maybe_ai_turn(self):
        if self.ai is None:
            return
        if self.ai == 'first':
            return
        await asyncio.sleep(1)
        await self._ai_move()

    async def _ai_move(self):
        if self.finished:
            return
        current = self.current_card()
        nxt = self.next_card()
        if current is None or nxt is None:
            return

        knows = self.bot_knows_all or self.bot_knows_next
        if knows:
            if nxt[0] > current[0]:
                choice = 'higher'
            elif nxt[0] < current[0]:
                choice = 'lower'
            else:
                choice = random.choice(['higher', 'lower'])
        else:
            remaining = self.deck[self.index + 1:]
            total = len(remaining)
            if total == 0:
                choice = random.choice(['higher', 'lower'])
            else:
                higher = sum(1 for r, s in remaining if r > current[0])
                lower = sum(1 for r, s in remaining if r < current[0])
                if higher > lower:
                    choice = 'higher'
                elif lower > higher:
                    choice = 'lower'
                else:
                    choice = random.choice(['higher', 'lower'])

        await self._resolve(None, choice, self.player.id)


class HiLoInviteView(ui.View):
    def __init__(self, inviter, invited):
        super().__init__(timeout=86400)
        self.inviter = inviter
        self.invited = invited
        self.accepted = None

    @ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.invited.id:
            await interaction.response.send_message("❌ Not for you.", ephemeral=True)
            return
        self.accepted = True
        await interaction.response.defer()
        self.stop()

    @ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.invited.id and interaction.user.id != self.inviter.id:
            await interaction.response.send_message("❌ Not for you.", ephemeral=True)
            return
        self.accepted = False
        await interaction.response.defer()
        self.stop()


class HiLoCommands:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree

    async def handle_message(self, message):
        content = message.content.strip()
        lower = content.lower()
        if not lower.startswith('!hi-lo'):
            return False
        if not message.guild:
            await message.add_reaction('❌')
            return True

        parts = content.split()
        mode = 'solo'
        lives = 3
        target = None

        for p in parts[1:]:
            pl = p.lower()
            if pl == 'survival':
                mode = 'survival'
            elif pl.startswith('lifes='):
                val = p[len('lifes='):]
                if not val.isdigit():
                    await message.add_reaction('❌')
                    return True
                lives = int(val)

        if message.mentions:
            target = message.mentions[0]

        if mode == 'survival':
            if lives > 5:
                await message.add_reaction('❌')
                return True
        else:
            if lives > 10 or lives < 1:
                await message.add_reaction('❌')
                return True

        inviter = message.author

        if target is not None and target.id == inviter.id:
            await message.add_reaction('❌')
            return True

        if target is not None and target.bot and target.id != self.bot.user.id:
            await message.channel.send("You can't cheat me with another bot!!!")
            return True

        if target is not None and target.id == self.bot.user.id:
            ai_first = random.random() < 0.5
            game = HiLoGame(self.bot, message.channel, inviter, mode, lives, opponent=None, ai='first' if ai_first else 'second')
            await game.start()
            return True

        if target is not None:
            inviter_starts = random.random() < 0.25
            if inviter_starts:
                player = inviter
                opponent = target
            else:
                player = target
                opponent = inviter

            view = HiLoInviteView(inviter, target)
            invite_msg = await message.channel.send(
                f"{target.mention}, do you accept the Hi-Lo invite from {inviter.mention}?",
                view=view,
                allowed_mentions=discord.AllowedMentions(users=[target, inviter])
            )
            await view.wait()
            if view.accepted is None:
                try:
                    await invite_msg.edit(content="⌛ Invite expired.", view=None)
                except Exception:
                    pass
                return True
            if not view.accepted:
                try:
                    await invite_msg.edit(content="❌ Invite declined.", view=None)
                except Exception:
                    pass
                return True
            try:
                await invite_msg.delete()
            except Exception:
                pass

            game = HiLoGame(self.bot, message.channel, player, mode, lives, opponent=opponent)
            await game.start()
            return True

        game = HiLoGame(self.bot, message.channel, inviter, mode, lives)
        await game.start()
        return True
