import sys
import asyncio
import threading
import json
import io
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
    port = int(10000)
    app.run(host="0.0.0.0", port=port, use_reloader=False)


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def clean_asterisks(name):
    if not name:
        return name
    result = []
    i = 0
    while i < len(name):
        if name[i] == '\\' and i + 1 < len(name) and name[i + 1] == '\\':
            result.append('\\')
            i += 2
        elif name[i] == '\\':
            i += 1
        else:
            result.append(name[i])
            i += 1
    return ''.join(result)


def clean_items_from_text(text):
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        cleaned = line.strip()
        cleaned = cleaned.replace('\u200b', '').replace('\ufeff', '').replace('\u200c', '').replace('\u200d', '')
        cleaned_lines.append(cleaned)

    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()

    last_empty_index = -1
    for i in range(len(cleaned_lines) - 1, -1, -1):
        if not cleaned_lines[i]:
            last_empty_index = i
            break

    if last_empty_index == -1:
        items = []
        for line in cleaned_lines:
            if line:
                line = line.replace('💞', '')
                if line.strip():
                    items.append(clean_asterisks(line.strip()))
        return items

    items = []
    for i in range(last_empty_index + 1, len(cleaned_lines)):
        line = cleaned_lines[i]
        if not line:
            continue
        line = line.replace('💞', '')
        if not line.strip():
            continue
        items.append(clean_asterisks(line.strip()))
    return items


def extract_names_from_embed(embed_dict):
    description = embed_dict.get('description') or ''
    names = []
    for line in description.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('**') and line.endswith('**') and len(line) > 4:
            name = line[2:-2].strip()
            if name:
                names.append(name)
        elif '<:' in line or '<a:' in line:
            continue
        else:
            names.append(line)
    return names


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
                    items.extend(clean_items_from_text(text))
                except Exception:
                    pass
    else:
        if referenced.author.bot and referenced.embeds:
            for embed in referenced.embeds:
                items.extend(extract_names_from_embed({'description': embed.description or ''}))
            items = [clean_asterisks(i) for i in items]
        else:
            content = referenced.content or ''
            if content and '\n' in content:
                items = clean_items_from_text(content)
            elif content.strip():
                items = [clean_asterisks(content.strip())]

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


def build_full_json(message):
    return message._raw_data


async def manage_json_action(source, target_message=None):
    if isinstance(source, discord.Interaction):
        message = target_message or source.target
        ephemeral = True
    else:
        message = source
        ephemeral = False

    if message.reference is None:
        if isinstance(source, discord.Interaction):
            await source.followup.send("❌ Please reply to a message and use !json or the Json app command.", ephemeral=True)
        else:
            await message.channel.send("❌ Please reply to a message and use !json or the Json app command.")
        return

    try:
        referenced = await message.channel.fetch_message(message.reference.message_id)
    except Exception:
        if isinstance(source, discord.Interaction):
            await source.followup.send("❌ Could not fetch the referenced message.", ephemeral=True)
        else:
            await message.channel.send("❌ Could not fetch the referenced message.")
        return

    data = build_full_json(referenced)
    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    if len(json_str) > 1900:
        buf = io.BytesIO(json_str.encode("utf-8"))
        file = discord.File(buf, filename=f"message_{referenced.id}.json")
        if isinstance(source, discord.Interaction):
            await source.followup.send(file=file, ephemeral=True)
        else:
            await message.channel.send(file=file)
    else:
        text = f"```json\n{json_str}\n```"
        if isinstance(source, discord.Interaction):
            await source.followup.send(text, ephemeral=True)
        else:
            await message.channel.send(text)


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


@tree.context_menu(name="Json")
async def json_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)
    await manage_json_action(interaction, target_message=message)


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
        return
    if content.lower() == '!json':
        await manage_json_action(message)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


threading.Thread(target=run_flask, daemon=True).start()
client.run(TOKEN)
