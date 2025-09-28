import discord
from utils.function import block_user,get_setting_cached,delete_main_account
from auth.auth_logger import send_main_delete_log
from datetime import datetime

def setup(bot: discord.Bot):

    @bot.slash_command(
        name="차단id",
        description="디스코드 ID를 직접 입력해 차단합니다",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_id(
        ctx: discord.ApplicationContext,
        user_id: discord.Option(str, description="차단할 유저의 Discord ID"),  # type: ignore
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)")  # type: ignore
    ):
        discord_id = int(user_id)
        new_blocks, already_blocked = block_user(ctx.guild_id, discord_id, reason, ctx.user.id)

        msg = []
        if new_blocks:
            msg.append("✅ 새로 차단된 정보:")
            for dtype, val in new_blocks:
                msg.append(f"- {dtype}: `{val}`")
        if already_blocked:
            msg.append("⚠️ 이미 차단된 정보:")
            for dtype, val in already_blocked:
                msg.append(f"- {dtype}: `{val}`")

        await ctx.respond("\n".join(msg) or "⚠️ 차단할 데이터가 없습니다.", ephemeral=True)

        if new_blocks:
            # 🔹 멤버 객체 확인
            member = ctx.guild.get_member(discord_id)

            # 🔹 인증정보 삭제 (DB 이관)
            main_nick, sub_list = delete_main_account(ctx.guild_id, discord_id)

            # 🔹 역할/닉네임 정리 (멤버가 서버에 있을 경우만)
            if member:
                for key in ("main_auth_role", "sub_auth_role"):
                    role_id = get_setting_cached(ctx.guild_id, key)
                    if role_id:
                        role = ctx.guild.get_role(int(role_id))
                        if role:
                            try:
                                await member.remove_roles(role)
                            except discord.Forbidden:
                                pass

                try:
                    await member.edit(nick=None)
                except discord.Forbidden:
                    pass

            # 🔹 차단 로그 전송
            await broadcast_block_log(
                bot,
                blocked_gid=ctx.guild_id,
                target_user=member,        # 있으면 멤버 객체
                raw_user_id=discord_id,    # 없으면 user_id 표시
                new_blocks=new_blocks,
                reason=reason,
                blocked_by=ctx.user.id
            )

            # 🔹 인증취소 로그 (빨간색)
            await send_main_delete_log(
                ctx.bot,
                ctx.guild_id,
                member or discord_id,  # 멤버 없으면 그냥 ID 전달
                main_nick,
                sub_list
            )

    # 2) /차단맴버
    @bot.slash_command(
        name="차단맴버",
        description="현재 서버 멤버를 선택해 차단합니다 (본계정 + 부계정 포함)",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_member(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="차단할 서버 멤버"), # type: ignore
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)") # type: ignore
    ):
        new_blocks, already_blocked = block_user(ctx.guild_id, member, reason, ctx.user.id)

        msg = [f"🚫 {member.mention} 처리 결과:"]
        if new_blocks:
            msg.append("✅ 새로 차단된 정보:")
            for dtype, val in new_blocks:
                msg.append(f"- {dtype}: `{val}`")
        if already_blocked:
            msg.append("⚠️ 이미 차단된 정보:")
            for dtype, val in already_blocked:
                msg.append(f"- {dtype}: `{val}`")

        await ctx.respond("\n".join(msg), ephemeral=True)

        if new_blocks:
            # 🔹 인증정보 이관 & 역할 회수
            main_nick, sub_list = delete_main_account(ctx.guild_id, member.id)

            # 역할 제거
            for key in ("main_auth_role", "sub_auth_role"):
                role_id = get_setting_cached(ctx.guild_id, key)
                if role_id:
                    role = ctx.guild.get_role(int(role_id))
                    if role:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

            # 닉네임 초기화
            try:
                await member.edit(nick=None)
            except discord.Forbidden:
                pass

            # 🔹 차단 로그 전송
            await broadcast_block_log(
                bot,
                blocked_gid=ctx.guild_id,
                target_user=member,
                raw_user_id=member.id,
                new_blocks=new_blocks,
                reason=reason,
                blocked_by=ctx.user.id
            )

            # 🔹 인증취소 로그 (빨간색)
            await send_main_delete_log(
                ctx.bot,
                ctx.guild_id,
                member,
                main_nick,
                sub_list
            )



async def broadcast_block_log(
    bot: discord.Bot,
    blocked_gid: int,
    target_user: discord.Member | None,
    new_blocks: list[tuple[str, str]],
    reason: str,
    blocked_by: int,
    raw_user_id: int | None = None  # 🔹 추가: 멤버 없을 때 직접 user_id 넘기기
):
    """
    등록된 모든 길드의 blocked_channel 에 차단 로그 전송 (Embed 버전)
    """
    all_settings = get_setting_cached()  # {guild_id: {key:value, ...}}

    now = datetime.now()
    date_str = now.strftime("%Y년 %m월 %d일 %a %p %I:%M")

    # ✅ 차단자 멘션 + 서버명
    blocked_by_mention = f"<@{blocked_by}>" if blocked_by else "알 수 없음"
    server_name = get_setting_cached(blocked_gid, "server") or str(blocked_gid)

    # ✅ 대상자 (멤버 or user_id 멘션)
    if target_user:
        target_mention = target_user.mention
        target_id = str(target_user.id)
    elif raw_user_id:
        target_mention = f"<@{raw_user_id}>"
        target_id = str(raw_user_id)
    else:
        target_mention = "알 수 없음"
        target_id = "N/A"

    # ✅ 차단 항목들
    block_values = "\n".join([f"- {dtype}: {val}" for dtype, val in new_blocks])

    # ✅ Embed 생성
    embed = discord.Embed(
        title="🚫 차단 로그",
        description=f"{target_mention} 차단됨",
        color=0xe74c3c,
        timestamp=now
    )

    embed.add_field(name="ID", value=target_id, inline=False)
    embed.add_field(name="제재 일시", value=date_str, inline=False)
    embed.add_field(name="사유", value=reason, inline=False)
    embed.add_field(name="차단자", value=f"[{server_name}] {blocked_by_mention}", inline=False)

    embed.add_field(name="차단 항목", value=f"```\n{block_values}\n```", inline=False)
    embed.set_footer(text="Develop by 주우자악8")

    # ✅ 모든 길드 blocked_channel 에 전송
    for gid, settings in all_settings.items():
        channel_id = settings.get("blocked_channel")
        if not channel_id:
            continue
        channel = bot.get_channel(int(channel_id))
        if not channel:
            continue
        try:
            await channel.send(embed=embed)
        except Exception:
            continue
        
        
        
        
        
        
        
        
        
    # # 3) /차단닉네임
    # @bot.slash_command(
    #     name="차단닉네임",
    #     description="로스트아크 닉네임을 기준으로 차단합니다",
    #     default_member_permissions=discord.Permissions(administrator=True)
    # )
    # async def block_by_nickname(
    #     ctx: discord.ApplicationContext,
    #     nickname: discord.Option(str, description="차단할 로스트아크 닉네임"),
    #     reason: discord.Option(str, description="차단 사유")
    # ):
    #     new_blocks, already_blocked = block_user(ctx.guild_id, nickname, reason, ctx.user.id)

    #     msg = [f"🚫 닉네임 `{nickname}` 처리 결과:"]
    #     if new_blocks:
    #         msg.append("✅ 새로 차단된 정보:")
    #         for dtype, val in new_blocks:
    #             msg.append(f"- {dtype}: `{val}`")
    #     if already_blocked:
    #         msg.append("⚠️ 이미 차단된 정보:")
    #         for dtype, val in already_blocked:
    #             msg.append(f"- {dtype}: `{val}`")

    #     await ctx.respond("\n".join(msg), ephemeral=True)
