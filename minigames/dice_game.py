import random
import re
import discord


class DiceGame:
    def __init__(self, bot, tree):
        self.bot = bot
        self.tree = tree

    def _flip(self, choice):
        result = random.choice(["Heads", "Tails"])
        won = result.lower() == choice.lower()
        verdict = "you win!" if won else "you lose!"
        return f"**{result}** — {verdict}"

    def _roll(self, sides, count):
        return [random.randint(1, sides) for _ in range(count)]

    def _format_rolls(self, rolls):
        if len(rolls) == 1:
            return f"**🎲 {rolls[0]}**"
        parts = [f"**🎲 {r}**" for r in rolls]
        return " — ".join(parts)

    async def handle_message(self, message):
        content = message.content.strip()
        lower = content.lower()

        if lower in ('!head', '!heads'):
            await message.channel.send(self._flip("Heads"))
            return True
        if lower in ('!tail', '!tails'):
            await message.channel.send(self._flip("Tails"))
            return True

        dice_map = {
            '!dice': 6,
            '!dice4': 4,
            '!dice8': 8,
            '!dice10': 10,
            '!dice12': 12,
            '!dice20': 20,
            '!dice100': 100,
        }

        for cmd, sides in dice_map.items():
            if lower.startswith(cmd):
                rest = content[len(cmd):].strip()
                count = 1
                if rest:
                    if re.match(r'^-?\d+$', rest):
                        count = int(rest)
                    else:
                        continue
                if count > 10:
                    await message.add_reaction('❌')
                    await message.add_reaction('▶️')
                    await message.add_reaction('🔟')
                    return True
                if count < 1:
                    await message.add_reaction('❌')
                    await message.add_reaction('◀️')
                    await message.add_reaction('1️⃣')
                    return True
                rolls = self._roll(sides, count)
                await message.channel.send(self._format_rolls(rolls))
                return True

        return False
