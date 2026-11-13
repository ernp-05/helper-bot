import sys
import asyncio
import threading
import discord
from discord import app_commands
from flask import Flask, redirect

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
    app.run(port=5000, use_reloader=False)


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def apply_trim(items, trim):
    if trim is None:
        return items, None
    if isinstance(trim, str) and '-' in trim:
        try:
            start, end = trim.split('-')
            start = int(start.strip())
            end = int(end.strip())
            if 1 <= start <= len(items) and 1 <= end <= len(items) and start <= end:
                return items[start-1:end], None
            return None, f"❌ Invalid range: {trim}. Valid range is 1-{len(items)}"
        except ValueError:
            return None, f"❌ Invalid range format: {trim}. Use format like '5-7'"
    elif isinstance(trim, int) or (isinstance(trim, str) and trim.isdigit()):
        n = int(trim) if isinstance(trim, str) else trim
        if n < 0:
            return items[n:], None
        return items[:n], None
    return items, None


async def manage_list_action(source, trim=None, target_message=None):
    if isinstance(source, discord.Interaction):
        message = target_message or source.target
        ephemeral = True
    else:
        message = source
        ephemeral = False

    if message.reference is None:
        if isinstance(source, discord.Interaction):
            await source.followup.send("❌ Please reply to a message and use !l or the List app command.", ephemeral=True)
        else:
            await message.channel.send("❌ Please reply to a message and use !l or the List app command.")
        return

    try:
        referenced = await message.channel.fetch_message(message.reference.message_id)
    except Exception:
        if isinstance(source, discord.Interaction):
            await source.followup.send("❌ Could not fetch the referenced message.", ephemeral=True)
        else:
            await message.channel.send("❌ Could not fetch the referenced message.")
        return

    items = []

    if referenced.attachments:
        for att in referenced.attachments:
            if att.filename.endswith('.txt') or (att.content_type or '').startswith('text/plain'):
                try:
                    data = await att.read()
                    text = data.decode('utf-8', errors='ignore')
                    for line in text.splitlines():
                        line = line.strip().replace('💞', '').replace('\u200b', '')
                        if line:
                            items.append(line)
                except Exception:
                    pass
    else:
        content = referenced.content or ''
        if '\n' in content:
            for line in content.splitlines():
                line = line.strip().replace('💞', '').replace('\u200b', '')
                if line:
                    items.append(line)
        elif content.strip():
            items.append(content.strip())

    if not items:
        if isinstance(source, discord.Interaction):
            await source.followup.send("❌ No items found in the referenced message.", ephemeral=True)
        else:
            await message.channel.send("❌ No items found in the referenced message.")
        return

    items, error = apply_trim(items, trim)
    if error:
        if isinstance(source, discord.Interaction):
            await source.followup.send(error, ephemeral=True)
        else:
            await message.channel.send(error)
        return

    chunks = []
    current = ""
    for item in items:
        piece = item if not current else "\n" + item
        if len(current) + len(piece) > 1900:
            chunks.append(current)
            current = item
        else:
            current += piece
    if current:
        chunks.append(current)

    if isinstance(source, discord.Interaction):
        for chunk in chunks:
            await source.followup.send(chunk, ephemeral=True)
            await asyncio.sleep(1)
    else:
        for chunk in chunks:
            await message.channel.send(chunk)
            await asyncio.sleep(1)


class TrimModal(discord.ui.Modal, title="List"):
    trim_input = discord.ui.TextInput(
        label="Trim (optional)",
        placeholder="e.g. 5 or 5-7",
        required=False,
        max_length=20,
    )

    def __init__(self, message: discord.Message):
        super().__init__()
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        trim = self.trim_input.value.strip() or None
        await manage_list_action(interaction, trim, target_message=self.message)


@tree.context_menu(name="List")
async def list_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(TrimModal(message))


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    content = message.content.strip()
    if content.lower() == '!l':
        await manage_list_action(message)
        return
    if content.lower().startswith('!l '):
        rest = content[3:].strip()
        parts = rest.split()
        trim = None
        if parts:
            if parts[0].lower() == 'trim' and len(parts) >= 2:
                trim = parts[1]
            elif parts[0].isdigit() or '-' in parts[0]:
                trim = parts[0]
        await manage_list_action(message, trim)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


threading.Thread(target=run_flask, daemon=True).start()
client.run(TOKEN)
