import discord

def build_ticket_panel_embed(server_id: int) -> discord.Embed:
    """
    고객센터 티켓 패널 임베드 생성
    :param server_name: 길드명
    :return: discord.Embed
    """
    from utils.function import get_setting_cached
    server_name = get_setting_cached(server_id,"server")
    embed = discord.Embed(
        title=f"🚨 고객센터 {server_name} 서버",
        description=(
            "📌 **이용 안내**\n"
            "아래 버튼을 눌러 문의를 시작하세요.\n\n"
            "✅ **문의** : 서버 운영과 관련된 일반 문의/건의\n"
            "🚨 **신고** : 사기 피해, 규칙 위반 등 관리자에게 전달할 내용\n"
            "🔑 **인증** : 정상적으로 인증이 되지 않는 경우\n\n"
            "⏳ **안내 사항**\n"
            "생성된 채널에서 서버 관리자와 직접 대화하실 수 있습니다.\n"
            "서로 존중하는 태도로 문의해 주세요.\n"
            "관리자에게 직접 DM은 답변하지 않습니다."
        ),
        color=discord.Color.red()
    )
    embed.set_footer(text="Develop by 주우자악8")  # ✅ Footer 추가
    return embed
