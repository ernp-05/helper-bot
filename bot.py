import sys
import asyncio
import threading
import discord
from discord import app_commands
from flask import Flask, redirect
from list_cmd import CreateList
from json_cmd import manage_json_action
from admin_cmd import AdminCommands
from misc_cmd import MiscCommands

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


@tree.context_menu(name="Json")
async def json_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)
    await manage_json_action(interaction, target_message=message)


create_list = CreateList(client, tree)
create_list.create_list()

admin_cmd = AdminCommands(client, tree)
misc_cmd = MiscCommands(client, tree)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if await admin_cmd.handle_message(message):
        return

    if await misc_cmd.handle_message(message):
        return

    content = message.content.strip()
    if not content.lower().startswith('!l'):
        if content.lower() == '!json':
            await manage_json_action(message)
        return

    if message.reference is not None:
        rest = content[2:].strip()
        parts = rest.split()
        trim = None
        unsep = False
        nolast = False
        plus = False
        for p in parts:
            pl = p.lower()
            if pl == 'unsep':
                unsep = True
            elif pl == 'nolast':
                nolast = True
            elif pl == 'plus':
                plus = True
            elif pl == 'trim' and parts.index(p) + 1 < len(parts):
                trim = parts[parts.index(p) + 1]
            elif trim is None and (p.isdigit() or '-' in p):
                trim = p
        await create_list.manage_list_action(message, trim, unsep=unsep, nolast=nolast, plus=plus)
        return

    items, trim, plus, unsep, nolast = create_list.parse_inline_list(content)
    if not items:
        return

    await create_list.manage_list_action(message, trim, unsep=unsep, nolast=nolast, plus=plus, direct_items=items)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


threading.Thread(target=run_flask, daemon=True).start()
client.run(TOKEN)
