import discord
from utils.function import get_setting_cached

def build_admin_embed(guild_id: int, extra_text: str = None) -> discord.Embed:
    """
    관리자 패널 Embed 생성
    :param guild_id: 서버 ID
    :param extra_text: 추가로 하단에 표시할 안내 텍스트
    """
    server = get_setting_cached(guild_id, "server")
    embed = discord.Embed(
        title=f"⚙️{server} 서버 설정 패널",
        description=f"{server} 서버의 설정 값입니다.",
        color=discord.Color.blurple()
    )

    items = [
        ("인증 채널", "verify_channel"),
        ("인증 로그 채널", "verify_log_channel"),
        ("본계정 인증 역할", "main_auth_role"),
        ("부계정 인증 역할", "sub_auth_role"),
        ("문의 채널", "ticket_channel"),
        ("문의 로그 채널", "ticket_log_channel"),
        ("문의 채널 카테고리", "ticket_category"),        # ✅ 추가
        ("차단 로그 채널", "blocked_channel"),        # ✅ 추가
        ("본계정 인증 제한 레벨", "main_auth_min_level"), # ✅ 추가
        ("타임아웃 채널", "timeout_channel"),
    ]

    for label, key in items:
        value = get_setting_cached(guild_id, key)  # ✅ 캐시에서 가져오기

        if value and value.isdigit():
            if "role" in key:
                display_value = f"<@&{value}>"
            elif "category" in key:
                # 📂 카테고리는 일부 클라이언트에서 멘션 안 보일 수 있으니 이모지 붙임
                display_value = f"📂 <#{value}>"
            elif "channel" in key:
                display_value = f"<#{value}>"
            else:
                display_value = value
        else:
            display_value = value or "❌ 미설정"

        embed.add_field(
            name=label,
            value=display_value,
            inline=False
        )

    if extra_text:
        embed.add_field(
            name="ℹ️ 안내",
            value=extra_text,
            inline=False
        )

    return embed


def build_admin_commands_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📖 관리자 명령어 안내",
        description="관리자 전용 명령어 사용법입니다. 필요한 명령어를 확인해 주세요.",
        color=discord.Color.green(),
    )

    embed.add_field(
        name="✅ 인증 관리",
        value=(
            "`/계정확인` : 유저 계정이 닉네임과 일치하는지 확인\n"
            "`/인증해제` : 인증 정보 강제 삭제 (discord_id/member/stove_member_no)\n"
            "`/인증정리` : 서버에 없는 인증 기록 정리\n"
            "`/인증검색` : 인증 기록 조회 (discord_id/nickname/stove_member_no)"
        ),
        inline=False,
    )

    embed.add_field(
        name="🚫 차단 관리",
        value=(
            "`/차단id` : 디스코드 ID로 차단\n"
            "`/차단맴버` : 서버 멤버 선택 차단\n"
            "`/차단닉네임` : 로스트아크 닉네임 기준 차단"
        ),
        inline=False,
    )

    embed.add_field(
        name="🧾 문의 관리",
        value="`/문의삭제` : 문의 채널 로그 저장 후 삭제",
        inline=False,
    )

    embed.set_footer(text="※ /서버등록, /관리자채널 명령어는 별도 설정용입니다.")
    return embed
