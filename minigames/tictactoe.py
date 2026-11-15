import asyncio
import random
import discord
from discord import ui

LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6)
]


def has_winner(board, player):
    return any(all(board[i] == player for i in line) for line in LINES)


def is_full(board):
    return all(c != ' ' for c in board)


def free_cells(board):
    return [i for i, c in enumerate(board) if c == ' ']


def find_winning_move(board, player):
    for i in free_cells(board):
        copy = board[:]
        copy[i] = player
        if has_winner(copy, player):
            return i
    return None


def find_fork(board, player):
    for i in free_cells(board):
        copy = board[:]
        copy[i] = player
        threats = sum(
            1 for j in free_cells(copy)
            if has_winner([player if k == j else c for k, c in enumerate(copy)], player)
        )
        if threats >= 2:
            return i
    return None


def find_opponent_fork(board, player, opponent):
    for i in free_cells(board):
        copy = board[:]
        copy[i] = opponent
        threats = sum(
            1 for j in free_cells(copy)
            if has_winner([opponent if k == j else c for k, c in enumerate(copy)], opponent)
        )
        if threats >= 2:
            return i
    return None


def choose_move(board, player, opponent):
    free = free_cells(board)

    move = find_winning_move(board, player)
    if move is not None:
        return move

    move = find_winning_move(board, opponent)
    if move is not None:
        return move

    move = find_fork(board, player)
    if move is not None:
        return move

    move = find_opponent_fork(board, player, opponent)
    if move is not None:
        return move

    if 4 in free:
        return 4

    corners = [0, 2, 6, 8]
    opposite = {0: 8, 8: 0, 2: 6, 6: 2}
    for corner in corners:
        if board[corner] == opponent and opposite[corner] in free:
            return opposite[corner]

    for corner in corners:
        if corner in free:
            return corner

    for side in [1, 3, 5, 7]:
        if side in free:
            return side

    return free[0]


class TicTacToeButton(ui.Button):
    def __init__(self, index, game):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=index // 3)
        self.index = index
        self.game = game

    async def callback(self, interaction: discord.Interaction):
        await self.game.handle_click(interaction, self.index)


class TicTacToeView(ui.View):
    def __init__(self, game):
        super().__init__(timeout=300)
        self.game = game
        for i in range(9):
            self.add_item(TicTacToeButton(i, game))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.game.player_x.id, self.game.player_o.id):
            await interaction.response.send_message("❌ You are not part of this game.", ephemeral=True)
            return False
        return True


class TicTacToeGame:
    def __init__(self, bot, channel, player_x, player_o, ai_side=None):
        self.bot = bot
        self.channel = channel
        self.player_x = player_x
        self.player_o = player_o
        self.ai_side = ai_side
        self.board = [' '] * 9
        self.turn = 'X'
        self.message = None
        self.view = TicTacToeView(self)

    def _display(self):
        x = self.player_x
        o = self.player_o
        if self.ai_side == 'X':
            x_line = f"❌ **{x.display_name}** (AI)"
        else:
            x_line = f"❌ **{x.display_name}**"
        if self.ai_side == 'O':
            o_line = f"⭕ **{o.display_name}** (AI)"
        else:
            o_line = f"⭕ **{o.display_name}**"

        if self.turn == 'X':
            turn_line = f"Turn: ❌ **{x.display_name}**"
        else:
            turn_line = f"Turn: ⭕ **{o.display_name}**"

        if has_winner(self.board, 'X'):
            turn_line = f"Winner: ❌ **{x.display_name}**"
        elif has_winner(self.board, 'O'):
            turn_line = f"Winner: ⭕ **{o.display_name}**"
        elif is_full(self.board):
            turn_line = "Draw!"

        return f"{x_line} vs {o_line}\n{turn_line}"

    def _update_buttons(self):
        for child in self.view.children:
            if isinstance(child, TicTacToeButton):
                c = self.board[child.index]
                if c == 'X':
                    child.label = '❌'
                    child.style = discord.ButtonStyle.danger
                    child.disabled = True
                elif c == 'O':
                    child.label = '⭕'
                    child.style = discord.ButtonStyle.success
                    child.disabled = True
                else:
                    child.label = '\u200b'
                    child.style = discord.ButtonStyle.secondary
                    child.disabled = False
        if has_winner(self.board, 'X') or has_winner(self.board, 'O') or is_full(self.board):
            for child in self.view.children:
                child.disabled = True

    async def start(self):
        self._update_buttons()
        self.message = await self.channel.send(
            self._display(),
            view=self.view,
            allowed_mentions=discord.AllowedMentions.none()
        )
        if self.ai_side == 'X':
            await asyncio.sleep(1)
            await self._ai_move()

    async def handle_click(self, interaction, index):
        if self.board[index] != ' ':
            await interaction.response.send_message("❌ Occupied.", ephemeral=True)
            return

        if has_winner(self.board, 'X') or has_winner(self.board, 'O') or is_full(self.board):
            await interaction.response.send_message("❌ Game over.", ephemeral=True)
            return

        if self.turn == 'X' and self.ai_side == 'X':
            await interaction.response.send_message("❌ It's the AI's turn.", ephemeral=True)
            return
        if self.turn == 'O' and self.ai_side == 'O':
            await interaction.response.send_message("❌ It's the AI's turn.", ephemeral=True)
            return

        self.board[index] = self.turn
        self._update_buttons()
        self.turn = 'O' if self.turn == 'X' else 'X'
        await interaction.response.edit_message(
            content=self._display(),
            view=self.view,
            allowed_mentions=discord.AllowedMentions.none()
        )

        if has_winner(self.board, 'X') or has_winner(self.board, 'O') or is_full(self.board):
            return

        if self.ai_side == self.turn:
            await asyncio.sleep(1)
            await self._ai_move()

    async def _ai_move(self):
        if has_winner(self.board, 'X') or has_winner(self.board, 'O') or is_full(self.board):
            return
        ai = self.ai_side
        human = 'O' if ai == 'X' else 'X'
        move = choose_move(self.board, ai, human)
        self.board[move] = ai
        self._update_buttons()
        self.turn = human
        await self.message.edit(
            content=self._display(),
            view=self.view,
            allowed_mentions=discord.AllowedMentions.none()
        )


class InviteView(ui.View):
    def __init__(self, inviter, invited):
        super().__init__(timeout=60)
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


class TicTacToeCommands:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree

    async def handle_message(self, message):
        content = message.content.strip()
        if not content.lower().startswith('!ttt'):
            return False

        if not message.guild:
            await message.add_reaction('❌')
            return True

        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❌ Usage: `!ttt @user` (or mention the bot to play vs AI)")
            return True

        if not message.mentions:
            await message.channel.send("❌ Mention a user or the bot.")
            return True

        target = message.mentions[0]
        inviter = message.author

        if target.id == inviter.id:
            await message.add_reaction('❌')
            return True

        if target.id == self.bot.user.id:
            ai_side = random.choice(['X', 'O'])
            if ai_side == 'X':
                player_x = target
                player_o = inviter
            else:
                player_x = inviter
                player_o = target
            game = TicTacToeGame(self.bot, message.channel, player_x, player_o, ai_side=ai_side)
            await game.start()
            return True

        inviter_starts = random.random() < 0.25
        if inviter_starts:
            player_x = inviter
            player_o = target
        else:
            player_x = target
            player_o = inviter

        view = InviteView(inviter, target)
        invite_msg = await message.channel.send(
            f"❌ **{player_x.display_name}** vs ⭕ **{player_o.display_name}**\n"
            f"{target.mention}, do you accept the Tic-Tac-Toe invite from {inviter.mention}?",
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

        game = TicTacToeGame(self.bot, message.channel, player_x, player_o)
        await game.start()
        return True
