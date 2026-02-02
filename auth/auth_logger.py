import discord
from datetime import datetime
from utils.function import get_setting_cached


async def _resolve_log_member(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
) -> discord.abc.User:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return user

    try:
        member = await guild.fetch_member(user.id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return user
    else:
        return member


def _format_user_tag(user: discord.abc.User) -> str:
    return f"{user.mention} ({user.display_name} | {user.id})"

async def send_nickname_change_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    old_nick: str | None,
    new_nick: str
):
    """
    닉네임 변경 로그를 인증 로그 채널(verify_log_channel)에 전송
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return

    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    now = datetime.now().strftime("%Y-%m-%d %p %I:%M")

    embed = discord.Embed(
        title="✏️ 대표 캐릭터 변경 로그",
        description=f"{_format_user_tag(user)} 대표 캐릭터가 변경되었습니다.",
        color=0x9b59b6,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="이전 대표 캐릭터", value=old_nick or "없음", inline=True)
    embed.add_field(name="새 대표 캐릭터", value=new_nick, inline=True)
    embed.set_footer(text=f"변경 일시 • {now}")

    await channel.send(embed=embed)
    
async def send_trade_auth_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    character_name: str,
    server_name: str,
    item_level: str
):
    """
    거래소(본계정) 인증 로그 전송
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return

    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    now = datetime.now().strftime("%Y-%m-%d %p %I:%M")

    embed = discord.Embed(
        title="✅ 거래소 인증 완료",
        description=f"{_format_user_tag(user)} 님이 본계정을 인증했습니다.",
        color=0x2ecc71,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="캐릭터", value=character_name, inline=True)
    embed.add_field(name="서버", value=server_name, inline=True)
    embed.add_field(name="아이템 레벨", value=item_level, inline=True)
    embed.set_footer(text=f"인증 일시 • {now}")

    await channel.send(embed=embed)


async def send_sub_auth_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    sub_number: int,
    character_name: str,
    server_name: str,
    item_level: str
):
    """
    부계정 인증 로그 전송 (본계정 정보 포함)
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return

    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    # 🔹 본계정 닉네임 조회
    from utils.function import get_main_account_nickname
    main_nick = get_main_account_nickname(guild_id, user.id)

    now = datetime.now().strftime("%Y-%m-%d %p %I:%M")

    embed = discord.Embed(
        title="📌 부계정 인증 완료",
        description=f"{_format_user_tag(user)} 님이 **부계정 {sub_number}번**을 인증했습니다.",
        color=0x3498db,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)

    if main_nick:
        embed.add_field(name="본계정", value=main_nick, inline=False)

    embed.add_field(name="캐릭터", value=character_name, inline=True)
    embed.add_field(name="서버", value=server_name, inline=True)
    embed.add_field(name="아이템 레벨", value=item_level, inline=True)
    embed.set_footer(text=f"인증 일시 • {now}")

    await channel.send(embed=embed)
    
async def send_account_delete_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    action_text: str
):
    """
    계정 삭제 로그 전송
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return

    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    embed = discord.Embed(
        title="🗑️ 인증 계정 삭제 로그",
        description=f"{_format_user_tag(user)} {action_text}",
        color=0xe74c3c,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    await channel.send(embed=embed)
    
async def send_main_delete_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    main_nick: str | None,
    sub_list: list[tuple[int, str]],
):
    """
    본계정 + 부계정 삭제 로그
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return
    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    server = get_setting_cached(guild_id, "server") or "알 수 없음"

    embed = discord.Embed(
        title="🗑️ 본계정 인증 취소",
        description=f"{_format_user_tag(user)} 님의 \n본계정 및 모든 부계정 인증이 취소되었습니다.",
        color=0xe74c3c,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="서버", value=server, inline=False)

    embed.add_field(name="본계정", value=main_nick or "없음", inline=False)

    if sub_list:
        subs_text = "\n".join([f"{num}번 부계정: {nick}" for num, nick in sub_list])
        embed.add_field(name="부계정 목록", value=subs_text, inline=False)

    embed.set_footer(text="Develop by 주우자악8")

    await channel.send(embed=embed)


async def send_sub_delete_log(
    bot: discord.Bot,
    guild_id: int,
    user: discord.abc.User,
    sub_number: int,
    nickname: str,
):
    """
    부계정 삭제 로그
    """
    log_channel_id = get_setting_cached(guild_id, "verify_log_channel")
    if not log_channel_id:
        return
    channel = bot.get_channel(int(log_channel_id))
    if not channel:
        return
    user = await _resolve_log_member(bot, guild_id, user)

    server = get_setting_cached(guild_id, "server") or "알 수 없음"

    embed = discord.Embed(
        title="📌 부계정 인증 취소",
        description=f"{_format_user_tag(user)} 님의 \n{sub_number}번 부계정 인증이 취소되었습니다.",
        color=0xf1c40f,
        timestamp=datetime.now()
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(name="서버", value=server, inline=False)
    embed.add_field(name="닉네임", value=nickname, inline=True)

    embed.set_footer(text="Develop by 주우자악8")

    await channel.send(embed=embed)
