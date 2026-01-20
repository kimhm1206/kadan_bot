import argparse
import asyncio
import os

import discord
from dotenv import load_dotenv


intents = discord.Intents.default()
intents.members = True
second_bot = discord.Bot(intents=intents)


@second_bot.event
async def on_ready():
    print(f"✅ 세컨드 봇 실행 완료: {second_bot.user} (ID: {second_bot.user.id})")
    await second_bot.sync_commands()


def load_secondary_extensions(target_bot: discord.Bot):
    target_bot.load_extension("utils.secondary_commands")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kadan Bot 세컨드 봇 실행")
    parser.parse_args()

    load_dotenv()
    token = os.getenv("BOT_TOKEN_SECOND")

    async def runner():
        if token:
            load_secondary_extensions(second_bot)
            await second_bot.start(token)
        else:
            print("❌ .env 파일에서 세컨드 봇 토큰을 찾을 수 없습니다.")

    asyncio.run(runner())
