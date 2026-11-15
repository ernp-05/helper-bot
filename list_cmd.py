import asyncio
import re
import discord


class CreateList:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree

    def join_items(self, items, max_length=1990, sep="$", trailing_sep=True):
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

    def strip_trailing_decorations(self, name):
        if not name:
            return ""
        name = name.replace('**', '')
        name = name.replace('💞', '')
        name = name.replace('\\~', '~')
        name = name.replace('\u200b', '').replace('\ufeff', '').replace('\u200c', '').replace('\u200d', '')
        name = name.strip()
        if not name:
            return ""
        name = re.sub(r'^\s*·\s*', '', name)
        name = re.sub(r'^#\d+(?:\.\d+)?\s*-\s*', '', name)
        name = re.sub(r'[\u2705\u2b50\u2b06\u2b07\u2b05\u27a1\u2934\u2935\u274c]', '', name)
        name = name.replace('🚫', '')
        name = re.sub(r'\s*\+\d+%', '', name)
        name = re.sub(r'[ \t]+', ' ', name).strip()
        cut = len(name)
        for sep in (' | ', ' · ', ' - ', ' . ', ' => ', '=>', '$wa', '$wg', '$hg', '$ha', 'DISABLED', '🚫'):
            idx = name.find(sep)
            if idx != -1 and idx < cut:
                cut = idx
        if cut < len(name):
            name = name[:cut].strip()
        else:
            name = re.sub(r'\s*\d[\d.,]{2,}\s*sp\s*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s*\d[\d.,]{2,}\s*ka\s*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s*\(\s*#?\s*[0-9A-Fa-f]{6}\s*\)\s*$', '', name)
            name = re.sub(r'\s*#\s*[0-9A-Fa-f]{6}\s*$', '', name)
            name = re.sub(r'\s*\(\s*Soulkeys:\s*[\d.,]+\s*\)\s*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s*\(\s*\d+\s*tags?\s*\)\s*$', '', name, flags=re.IGNORECASE)
            name = re.sub(r'\s*\(\s*\d[\d.,]*\s*\)\s*$', '', name)
        name = re.sub(r'<a?:[A-Za-z0-9_]+:\d+>', '', name)
        name = re.sub(r'[ \t]+', ' ', name).strip()
        name = name.rstrip(' .')
        while name.startswith('$'):
            name = name[1:].strip()
        return name

    def clean_items_from_text(self, text):
        items = []
        for line in text.split('\n'):
            cleaned = self.strip_trailing_decorations(line)
            if cleaned:
                items.append(cleaned)
        return items

    def is_bundle_list(self, text):
        first = text.strip().split('\n', 1)[0] if text.strip() else ''
        return bool(re.match(r'^\d+\s+(bundles?\b.*|paquetes?\b.*|pacotes?\b.*)', first, flags=re.IGNORECASE))

    def clean_bundle_list(self, text):
        items = []
        for line in text.split('\n'):
            raw = line.strip()
            if not raw:
                continue
            if re.match(r'^\d+\s+(bundles?\b|paquetes?\b|pacotes?\b)', raw, flags=re.IGNORECASE):
                continue
            cleaned = self.strip_trailing_decorations(raw)
            if not cleaned:
                continue
            cleaned = cleaned.lstrip('·').strip()
            if not cleaned:
                continue
            cleaned = re.sub(r'\s*\(\s*\d[\d.,]*\s*\)\s*$', '', cleaned).strip()
            if cleaned:
                items.append(cleaned)
        return items

    def extract_items_from_message(self, msg):
        items = []
        if msg.content:
            for line in msg.content.split('\n'):
                line = line.strip()
                if line:
                    items.append(line)
        for embed in msg.embeds:
            if embed.description:
                for line in embed.description.split('\n'):
                    line = line.strip()
                    if line:
                        items.append(line)
        return items

    def extract_names_from_embed(self, embed_dict):
        description = embed_dict.get('description') or ''
        lines = description.split('\n')

        has_subheaders = any(re.match(r'^\*\*.+ - \d+/\d+\*\*$', line.strip()) for line in lines)
        has_bundle_list = any(re.match(r'^·\s*.+?\s*\(\*\*\d+\*\*\)$', line.strip()) for line in lines)
        has_disablelist = any(re.match(r'^\*\*.+\*\*\s*\(.+\)$', line.strip()) for line in lines)

        if not has_subheaders and not has_bundle_list and not has_disablelist:
            start = 0
            for i, line in enumerate(lines):
                if line.strip() == '':
                    start = i + 1
            lines = lines[start:]

        names = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            if raw.startswith('*') and raw.endswith('*') and len(raw) > 1:
                continue
            if raw.lower().startswith('avg:') or raw.lower().startswith('top 15 value:'):
                continue
            if raw.lower().startswith('limits of your') or raw.lower().startswith('use $limroul'):
                continue
            if re.match(r'^[\d.,/\s$wakgh]+$', raw):
                continue
            if re.match(r'^\*\*.+ - \d+/\d+\*\*$', raw):
                continue
            m = re.match(r'^·\s*(.+?)\s*\(\*\*\d+\*\*\)$', raw)
            if m:
                cleaned = self.strip_trailing_decorations(m.group(1))
                if cleaned:
                    names.append(cleaned)
                continue
            m = re.match(r'^\*\*(.+?)\*\*\s*\(.+\)$', raw)
            if m:
                cleaned = self.strip_trailing_decorations(m.group(1))
                if cleaned:
                    names.append(cleaned)
                continue
            cleaned = self.strip_trailing_decorations(raw)
            if not cleaned:
                continue
            if cleaned.lower().startswith('total invested'):
                continue
            names.append(cleaned)
        return names

    def apply_trim(self, items, trim):
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

    def parse_inline_list(self, content):
        body = content
        if body.lower().startswith('!l'):
            body = body[2:]
        if body.startswith(' '):
            body = body[1:]

        if not body:
            return None, None, False, False, False

        lines = body.split('\n')
        first = lines[0]
        rest = lines[1:]

        trim = None
        plus = False
        unsep = False
        nolast = False

        tokens = first.split()
        data_start = None

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            low = tok.lower()
            if low == 'plus':
                plus = True
                i += 1
            elif low == 'unsep':
                unsep = True
                i += 1
            elif low == 'nolast':
                nolast = True
                i += 1
            elif low == 'trim':
                if i + 1 < len(tokens):
                    val = tokens[i + 1]
                    if re.match(r'^\d+$', val) or re.match(r'^\d+-\d+$', val):
                        trim = val
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
            else:
                data_start = i
                break

        raw_items = []
        if data_start is not None:
            raw_items.append(' '.join(tokens[data_start:]))
        for line in rest:
            raw_items.append(line)

        items = []
        for raw in raw_items:
            if not raw:
                continue
            cleaned = self.strip_trailing_decorations(raw)
            if cleaned:
                items.append(cleaned)

        return items, trim, plus, unsep, nolast

    async def manage_list_action(self, source, trim=None, target_message=None, unsep=False, nolast=False, plus=False, direct_items=None):
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

        if direct_items is not None:
            items = direct_items
        else:
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
                            if self.is_bundle_list(text):
                                items.extend(self.clean_bundle_list(text))
                            else:
                                items.extend(self.clean_items_from_text(text))
                        except Exception:
                            pass
            else:
                if referenced.author.bot and referenced.embeds:
                    for embed in referenced.embeds:
                        items.extend(self.extract_names_from_embed({'description': embed.description or ''}))
                else:
                    content = referenced.content or ''
                    if self.is_bundle_list(content):
                        items = self.clean_bundle_list(content)
                    elif content and '\n' in content:
                        items = self.clean_items_from_text(content)
                    elif content.strip():
                        items = [self.strip_trailing_decorations(content.strip())]
                    if not items:
                        items = self.extract_items_from_message(referenced)
                        items = [self.strip_trailing_decorations(i) for i in items]

            items = [self.strip_trailing_decorations(i) for i in items]
            items = [i for i in items if i]

        if not items:
            if isinstance(source, discord.Interaction):
                await source.followup.send("❌ No items found in the referenced message.", ephemeral=True)
            else:
                await message.channel.send("❌ No items found in the referenced message.")
            return

        items, error = self.apply_trim(items, trim)
        if error:
            if isinstance(source, discord.Interaction):
                await source.followup.send(error, ephemeral=True)
            else:
                await message.channel.send(error)
            return

        if unsep:
            sep = ""
        elif plus:
            sep = " + "
        else:
            sep = "$"
        trailing_sep = not nolast
        msgs = self.join_items(items, sep=sep, trailing_sep=trailing_sep)

        if isinstance(source, discord.Interaction):
            for m in msgs:
                await source.followup.send(m, ephemeral=True)
                await asyncio.sleep(1)
        else:
            for m in msgs:
                await message.channel.send(m)
                await asyncio.sleep(1)

    def create_list(self):
        class TrimModal(discord.ui.Modal, title="List"):
            trim_input = discord.ui.TextInput(
                label="Trim (optional)",
                placeholder="e.g. 5 or 5-7",
                required=False,
                max_length=20,
            )

            def __init__(modal_self, message):
                super().__init__()
                modal_self.message = message

            async def on_submit(modal_self, interaction):
                await interaction.response.defer(ephemeral=True)
                trim = modal_self.trim_input.value.strip() or None
                await self.manage_list_action(interaction, trim, target_message=modal_self.message)

        @self.tree.context_menu(name="List")
        async def list_context(interaction: discord.Interaction, message: discord.Message):
            await interaction.response.send_modal(TrimModal(message))

        return list_context
