import discord
from function import get_bot_token
from mainview import VerificationView
from command import setup as setup_commands

# 인증 채널 ID
VERIFICATION_CHANNEL_ID = 1381206205267185704

# 인텐트 설정
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# 봇 실행 시 고정 인증 메시지 전송
@bot.event
async def on_ready():
    
    print(f"✅ 봇 실행 완료: {bot.user} (ID: {bot.user.id})")

    channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
    if channel:
        try:
            async for msg in channel.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()
        except Exception as e:
            print("❌ 메시지 삭제 오류:", e)

        embed = discord.Embed(
            title="🎮 부계정 인증 시스템",
            description="아래 버튼을 눌러 부계정 인증을 시작해주세요!\n ```부계정 정보는 사기 방지를 목적으로 \n서버 탈퇴 및 부계정 정보 삭제 이후 최대6개월 까지 보관됩니다.```\n`보관 항목 : DISCORD_USER_ID, 본계정 닉, 부계정 닉`",
            color=discord.Color.blue(),
        )
        embed.set_footer(text='Develop by 주우자악8')
        await channel.send(embed=embed, view=VerificationView(timeout=None))
        print("📌 인증 메시지 전송 완료")
        
    await bot.sync_commands()

@bot.event
async def on_member_remove(member: discord.Member):
    from function import get_user_sub_accounts, delete_sub_account, send_log_embed

    sub_list = get_user_sub_accounts(member.id)
    if not sub_list:
        return  # 부계정이 없다면 종료

    for sub_nick in sub_list:
        delete_sub_account(member.id, sub_nick)  # 내부에서 deleted_information으로 이관됨

        # 로그 전송
        await send_log_embed(
            bot=bot,
            user=member,
            main_nick=sub_nick,
            title="🗑️ 부계정 탈퇴처리 완료"
        )

# 봇 실행
token = get_bot_token()
setup_commands(bot)
if token:
    bot.run(token)
else:
    print("❌ 봇 토큰을 settings 테이블에서 찾을 수 없습니다.")
