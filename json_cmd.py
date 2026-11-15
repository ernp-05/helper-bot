import json
import io
import discord


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
                    comp_data["style_name"] = {1: "primary", 2: "secondary", 3: "success", 4: "danger", 5: "link"}.get(style_val, "unknown")
                    comp_data["style_color"] = {1: "#5865F2", 2: "#4F545C", 3: "#3BA55D", 4: "#ED4245", 5: "#4F545C"}.get(style_val, None)
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
