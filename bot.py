import sys
import threading
import discord
from discord import app_commands
from flask import Flask, redirect
from list_cmd import CreateList
from json_cmd import JsonCommands
from admin_cmd import AdminCommands
from misc_cmd import MiscCommands
from minigames.dice_game import DiceGame
from minigames.tictactoe import TicTacToeCommands
from minigames.hi_lo import HiLoCommands

if len(sys.argv) < 2:
    print("Usage: python bot.py <TOKEN>")
    sys.exit(1)

TOKEN = sys.argv[1]

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path == '':
        return "True"
    return redirect('/')


def run_flask():
    port = int(10000)
    app.run(host="0.0.0.0", port=port, use_reloader=False)


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

create_list = CreateList(client, tree)
create_list.create_list()

json_cmd = JsonCommands(client, tree)
admin_cmd = AdminCommands(client, tree)
misc_cmd = MiscCommands(client, tree)
dice_game = DiceGame(client, tree)
ttt_cmd = TicTacToeCommands(client, tree)
hilo_cmd = HiLoCommands(client, tree)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if message.guild is not None and message.content:
        bl_level = admin_cmd._check_blacklist(message)
        if bl_level is not None:
            await admin_cmd._apply_blacklist_action(message, bl_level)
            return
    if await admin_cmd.handle_message(message):
        return
    if await misc_cmd.handle_message(message):
        return
    if await create_list.handle_message(message):
        return
    if await json_cmd.handle_message(message):
        return
    if await dice_game.handle_message(message):
        return
    if await ttt_cmd.handle_message(message):
        return
    if await hilo_cmd.handle_message(message):
        return


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


threading.Thread(target=run_flask, daemon=True).start()
client.run(TOKEN)
