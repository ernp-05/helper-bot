import sys
import asyncio
import threading
import json
import io
import re
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


def join_items(items, max_length=1990, sep="$", trailing_sep=True):
    items = [i for i in items if i]

    messages = []
    current = []
    current_len = 0

    for item in items:
        piece = item + sep
        piece_len = len(piece)

        if current_len + piece_len > max_length:
            if current:
                chunk = sep.join(current)
                if trailing_sep:
                    chunk += sep
                messages.append(chunk)
            current = [item]
            current_len = piece_len
        else:
            current.append(item)
            current_len += piece_len

    if current:
        chunk = sep.join(current)
        if trailing_sep:
            chunk += sep
        messages.append(chunk)

    return messages


def strip_trailing_decorations(name):
    if not name:
        return ""
    name = name.replace('**', '')
    name = name.replace('💞', '')
    name = name.replace('\u200b', '').replace('\ufeff', '').replace('\u200c', '').replace('\u200d', '')
    name = name.strip()
    if not name:
        return ""

    name = re.sub(
        r'\s*[0-9](?:[0-9.,]){2,4}\s*sp\s*$',
        '',
        name,
        flags=re.IGNORECASE,
    )

    cut = len(name)
    for sep in (' | ', ' · ', ' => ', '=>', '$wa', '$wg', '$hg', '$ha', 'DISABLED', '🚫'):
        idx = name.find(sep)
        if idx != -1 and idx < cut:
            cut = idx
    name = name[:cut].strip()

    name = re.sub(r'<a?:[A-Za-z0-9_]+:\d+>', '', name)
    name = re.sub(r'[\u2705\u2b50\u2b06\u2b07\u2b05\u27a1\u2934\u2935\u274c]', '', name)
    name = name.replace('🚫', '')
    name = re.sub(r'[ \t]+', ' ', name).strip()

    while name.startswith('$'):
        name = name[1:].strip()

    return name


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
    items = []
    for line in lines:
        cleaned = strip_trailing_decorations(line)
        if cleaned:
            items.append(cleaned)
    return items


def extract_items_from_message(msg):
    items = []

    if msg.content:
        lines = msg.content.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                items.append(line)

    for embed in msg.embeds:
        if embed.description:
            lines = embed.description.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    items.append(line)

    return items


def extract_names_from_embed(embed_dict):
    description = embed_dict.get('description') or ''
    names = []
    for line in description.split('\n'):
        cleaned = strip_trailing_decorations(line)
        if not cleaned:
            continue
        if cleaned.lower().startswith('total invested'):
            continue
        names.append(cleaned)
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


async def manage_list_action(source, trim=None, target_message=None, unsep=False, nolast=False):
    if isinstance(source, discord.Interaction):
        message = target_message
        ephemeral = True
        require_reply = False
        if message is None:
            await source.followup.send("❌ No target message.", ephemeral=True)
            return
    else:
        message = source
        ephemeral = False
        require_reply = True

    if require_reply and message.reference is None:
        await message.channel.send("❌ Please reply to a message and use !l or the List app command.")
        return

    if require_reply:
        try:
            referenced = await message.channel.fetch_message(message.reference.message_id)
        except Exception:
            await message.channel.send("❌ Could not fetch the referenced message.")
            return
    else:
        referenced = message

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
        else:
            content = referenced.content or ''
            if content and '\n' in content:
                items = clean_items_from_text(content)
            elif content.strip():
                items = [strip_trailing_decorations(content.strip())]
            if not items:
                items = extract_items_from_message(referenced)
                items = [strip_trailing_decorations(i) for i in items]

    items = [strip_trailing_decorations(i) for i in items]
    items = [i for i in items if i]

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

    sep = "" if unsep else "$"
    trailing_sep = not nolast
    msgs = join_items(items, sep=sep, trailing_sep=trailing_sep)

    if isinstance(source, discord.Interaction):
        for m in msgs:
            await source.followup.send(m, ephemeral=True)
            await asyncio.sleep(1)
    else:
        for m in msgs:
            await message.channel.send(m)
            await asyncio.sleep(1)


def build_full_json(message):
    data = {
        "id": str(message.id),
        "content": message.content,
        "channel_id": str(message.channel.id),
        "guild_id": str(message.guild.id) if message.guild else None,
        "author": {
            "id": str(message.author.id),
            "name": message.author.name,
            "display_name": message.author.display_name,
            "bot": message.author.bot,
            "avatar_url": str(message.author.display_avatar.url) if message.author.display_avatar else None,
        },
        "created_at": message.created_at.isoformat(),
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "pinned": message.pinned,
        "tts": message.tts,
        "type": str(message.type),
        "reference": None,
        "embeds": [],
        "attachments": [],
        "reactions": [],
        "components": [],
    }

    if message.reference:
        data["reference"] = {
            "message_id": str(message.reference.message_id) if message.reference.message_id else None,
            "channel_id": str(message.reference.channel_id) if message.reference.channel_id else None,
            "guild_id": str(message.reference.guild_id) if message.reference.guild_id else None,
        }

    for embed in message.embeds:
        ed = embed.to_dict()
        if "color" in ed and ed["color"] is not None:
            ed["color_hex"] = f"#{ed['color']:06x}"
        data["embeds"].append(ed)

    for att in message.attachments:
        data["attachments"].append({
            "id": str(att.id),
            "filename": att.filename,
            "size": att.size,
            "url": att.url,
            "proxy_url": att.proxy_url,
            "content_type": att.content_type,
            "height": att.height,
            "width": att.width,
            "spoiler": att.is_spoiler(),
        })

    for reaction in message.reactions:
        data["reactions"].append({
            "emoji": str(reaction.emoji),
            "count": reaction.count,
            "me": reaction.me,
            "animated": getattr(reaction.emoji, "animated", False),
            "id": str(reaction.emoji.id) if getattr(reaction.emoji, "id", None) else None,
        })

    if message.components:
        for row in message.components:
            row_data = {"type": row.type.value if hasattr(row.type, "value") else int(row.type), "components": []}
            for comp in row.children:
                comp_data = {
                    "type": comp.type.value if hasattr(comp.type, "value") else int(comp.type),
                    "custom_id": getattr(comp, "custom_id", None),
                    "label": getattr(comp, "label", None),
                    "disabled": getattr(comp, "disabled", None),
                    "url": getattr(comp, "url", None),
                }
                style = getattr(comp, "style", None)
                if style is not None:
                    style_val = style.value if hasattr(style, "value") else int(style)
                    comp_data["style"] = style_val
                    comp_data["style_name"] = {
                        1: "primary",
                        2: "secondary",
                        3: "success",
                        4: "danger",
                        5: "link",
                    }.get(style_val, "unknown")
                    comp_data["style_color"] = {
                        1: "#5865F2",
                        2: "#4F545C",
                        3: "#3BA55D",
                        4: "#ED4245",
                        5: "#4F545C",
                    }.get(style_val, None)
                emoji = getattr(comp, "emoji", None)
                if emoji:
                    comp_data["emoji"] = {
                        "name": emoji.name,
                        "id": str(emoji.id) if emoji.id else None,
                        "animated": getattr(emoji, "animated", False),
                    }
                row_data["components"].append(comp_data)
            data["components"].append(row_data)

    return data


async def manage_json_action(source, target_message=None):
    if isinstance(source, discord.Interaction):
        message = target_message
        ephemeral = True
        require_reply = False
        if message is None:
            await source.followup.send("❌ No target message.", ephemeral=True)
            return
    else:
        message = source
        ephemeral = False
        require_reply = True

    if require_reply and message.reference is None:
        await message.channel.send("❌ Please reply to a message and use !json or the Json app command.")
        return

    if require_reply:
        try:
            referenced = await message.channel.fetch_message(message.reference.message_id)
        except Exception:
            await message.channel.send("❌ Could not fetch the referenced message.")
            return
    else:
        referenced = message

    data = build_full_json(referenced)
    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)

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
        unsep = False
        nolast = False
        for p in parts:
            pl = p.lower()
            if pl == 'unsep':
                unsep = True
            elif pl == 'nolast':
                nolast = True
            elif pl == 'trim' and parts.index(p) + 1 < len(parts):
                trim = parts[parts.index(p) + 1]
            elif trim is None and (p.isdigit() or '-' in p):
                trim = p
        await manage_list_action(message, trim, unsep=unsep, nolast=nolast)
        return
    if content.lower() == '!json':
        await manage_json_action(message)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


threading.Thread(target=run_flask, daemon=True).start()
client.run(TOKEN)
