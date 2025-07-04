import discord
from function import (
    get_setting,
    has_exchange_role,
    check_lostark_nickname,
    get_user_sub_count,
    get_max_subs
)
from registerview import RegisterStartView

OPERATING_GUILD_ID = 743375510003777618

async def handle_auth(interaction: discord.Interaction):
    user = interaction.user
    discord_id = user.id
    bot = interaction.client

    # 0. 설정값 확인
    if get_setting("auth") != "main":
        await interaction.response.send_message(
            "⚠️ 현재 인증 방식은 관리자 인증(admin)으로 설정되어 있어, 부계정 인증을 진행할 수 없습니다.",
            ephemeral=True
        )
        return

    # 1. 거래소 역할 확인
    if not has_exchange_role(bot, discord_id):
        await interaction.response.send_message(
            "❌ 운영 서버에서 유저 정보를 찾을 수 없거나, 거래소 인증 역할이 없습니다.\n먼저 로아와 인증을 완료해주세요.",
            ephemeral=True
        )
        return

    # 2. 닉네임 유효성 확인 (서버 닉 우선, 없으면 사용자명)
    nickname = user.nick
    if user.nick == None:    
        nickname = user.display_name or user.global_name
        
    # ✅ " / 부계정O" 제거
    if " / 부계정O" in nickname:
        nickname = nickname.replace(" / 부계정O", "").strip()
        
    valid = await check_lostark_nickname(nickname)
    if not valid:
        await interaction.response.send_message(
            f"❌ 닉네임 `{nickname}` 은(는) 로스트아크에서 찾을 수 없습니다.\n로아와 인증 초기화 & 최초인증을 통해 닉네임을 변경해주세요.",
            ephemeral=True
        )
        return

    # 3. 현재 부계정 수 확인
    current = get_user_sub_count(discord_id)
    max_subs = get_max_subs()

    if current >= max_subs:
        await interaction.response.send_message(
            f"⚠️ 이미 {current}개의 부계정이 등록되어 있어 더 이상 추가할 수 없습니다.",
            ephemeral=True
        )
        return

    # ✅ 모든 조건 통과 → 안내 이미지 + 버튼 View 전송
    file = discord.File("인증.png", filename="인증.png")
    embed = discord.Embed(
        title="📘 부계정 등록 안내",
        description="위 이미지처럼 **전투정보실 링크**를 복사해서 등록을 진행해주세요.",
        color=discord.Color.green()
    ).set_image(url="attachment://인증.png")

    await interaction.response.send_message(
        embed=embed,
        file=file,
        view=RegisterStartView(),
        ephemeral=True
    )
