import discord
import random

def build_auth_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🛡️ 인증 시스템",
        description=(
            "원하시는 작업을 선택해주세요!\n\n"
            "⚙️ 작업 선택\n"
            "`거래소 인증`, `부계정 인증`, `닉네임 변경`, `인증 계정 설정` 중에서 선택할 수 있습니다.\n\n"
            "아래 버튼을 눌러 인증을 시작해주세요!\n"
            "모든 인증 정보는 사기 방지를 목적으로  \n"
            "서버 탈퇴 및 인증 정보 삭제 이후 최대 6개월 까지 보관됩니다.\n\n"
            "📦 보관 항목: DISCORD_USER_ID, STOVE_MEMBER_ID, 닉네임"
        ),
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Develop by 주우자악8")
    return embed

def build_trade_intro_embed(level=1680) -> discord.Embed:
    """
    거래소 인증 시작 안내 임베드
    - 조건 설명
    - 대표캐릭터 변경 절차 안내
    """
    embed = discord.Embed(
        title="🔑 거래소 인증 안내",
        description="아래 조건을 충족해야 거래소 인증이 가능합니다.",
        color=discord.Color.blue()
    )

    # ✅ 조건 리스트
    embed.add_field(
        name="필수 조건",
        value=(
            f"• 아이템 레벨 **{level} 이상**\n"
            "• 인증 과정에서 **대표 캐릭터 변경** 가능\n"
        ),
        inline=False
    )

    # ℹ️ 안내
    embed.add_field(
        name="인증 절차",
        value=(
            "1️⃣ **진행하기** 버튼 클릭\n"
            "2️⃣ 스토브 **마이페이지 링크 입력**\n"
            "3️⃣ 대표 캐릭터를 봇이 지정한 캐릭터로 변경\n"
            "4️⃣ 변경 확인 후 인증 완료"
        ),
        inline=False
    )

    # 📷 추후 이미지 (예: 어디서 대표캐릭터 변경하는지 캡처)
    embed.set_image(url="https://example.com/guide_image.png")  # TODO: 실제 이미지 링크로 교체

    embed.set_footer(text="대표 캐릭터 변경이 불가능하다면 인증을 진행할 수 없습니다.")
    return embed

def build_sub_intro_embed() -> discord.Embed:
    embed = discord.Embed(
        title="👥 부계정 인증",
        description="부계정 인증 절차를 시작합니다.\n"
                    "다음 안내에 따라 진행해주세요.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📋 안내",
        value=(
            "1. 부계정은 반드시 본계정 인증을 완료한 유저만 등록 가능합니다.\n"
            "2. 부계정도 마찬가지로 전투정보실을 통해 확인됩니다.\n"
            "3. 인증 완료 시 닉네임에 **'| 부계정O'** 표시가 추가됩니다."
        ),
        inline=False
    )
    return embed


def build_rep_change_embed(main_char: str, server: str, candidates: list[dict]) -> tuple[discord.Embed, str]:
    """
    대표캐릭터 변경 요청 임베드
    :param main_char: 현재 대표캐릭터 닉네임
    :param server: 서버 이름 (예: '카단')
    :param candidates: 필터된 캐릭터 리스트 (dicts)
    :return: (Embed, target_char)
    """
    # 랜덤 캐릭터 선택
    target_char = main_char
    while target_char == main_char:
        target_char = random.choice(candidates)["CharacterName"]
    
    embed = discord.Embed(
        title="🌀 대표 캐릭터 변경 요청",
        description=(
            f"현재 대표 캐릭터는 **{main_char}** 입니다.\n\n"
            f"➡️ 대표 캐릭터를 **{target_char}** 으로 변경한 뒤 "
            f"아래 **변경 확인** 버튼을 눌러주세요."
        ),
        color=discord.Color.orange()
    )

    embed.add_field(
        name="\n",
        value="대표 캐릭터 변경은 홈페이지의 [전투정보실] → [대표 캐릭터 지정] 메뉴에서 가능합니다.",
        inline=False
    )

    return embed, target_char