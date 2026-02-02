import discord
from dotenv import load_dotenv
import os
import argparse


# 인텐트 설정
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# 봇 실행 시
@bot.event
async def on_ready():
    print(f"✅ 봇 실행 완료: {bot.user} (ID: {bot.user.id})")
    

    from utils.function import get_all_settings
    from utils.cache import settings_cache
    from config.admin_embed import build_admin_embed
    from config.admin_view import AdminConfigMainView
    from config.send_default_message import send_default_message

    # ✅ DB → 캐시 초기화 (settings + server 값까지)
    all_settings = get_all_settings()
    settings_cache.clear()
    settings_cache.update(all_settings)

    # ✅ 길드별 관리자 패널 재전송
    for guild in bot.guilds:
        guild_cache = all_settings.get(guild.id, {})
        admin_channel_id = guild_cache.get("admin_channel")
        
        if admin_channel_id and admin_channel_id.isdigit():
            channel = bot.get_channel(int(admin_channel_id))
            if not channel:
                continue

            # 기존 패널 메시지 삭제 (최근 50개 중 봇이 보낸 것만)
            try:
                async for msg in channel.history(limit=50):
                    if msg.author == bot.user:
                        await msg.delete()
            except Exception as e:
                print(f"⚠️ 관리자 패널 삭제 실패: {e}")

            # 새로운 패널 메시지 전송
            embed = build_admin_embed(guild.id)
            view = AdminConfigMainView(bot, guild.id)
            await channel.send(embed=embed, view=view)
            
            
    await send_default_message(bot)
    await bot.sync_commands()

@bot.event
async def on_member_remove(member: discord.Member):
    from utils.function import delete_main_account
    from auth.auth_logger import send_main_delete_log

    main_nick, sub_list = delete_main_account(member.guild.id, member.id)
    if not main_nick and not sub_list:
        return

    await send_main_delete_log(bot, member.guild.id, member, main_nick, sub_list)

def load_extensions(target_bot: discord.Bot):
    # 설정 관련 명령어 등록
    target_bot.load_extension("config.config_commands")
    target_bot.load_extension("auth_commands")
    target_bot.load_extension("block.block_commands")
    target_bot.load_extension("utils.commands")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kadan Bot 실행 옵션")
    parser.add_argument(
        "--mode", 
        choices=["test", "prod"], 
        default="test", 
        help="실행 모드 선택 (test 또는 prod)"
    )

    args = parser.parse_args()
    load_dotenv()

    if args.mode == "test":
        token = os.getenv("BOT_TOKEN_TEST")
    else:
        token = os.getenv("BOT_TOKEN_PROD")

    if token:
        load_extensions(bot)   # ✅ 실행 전에 명령어 불러오기
        bot.run(token)
    else:
        print("❌ .env 파일에서 봇 토큰을 찾을 수 없습니다.")
