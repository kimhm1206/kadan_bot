import asyncio
from datetime import datetime
from typing import Optional

import discord

from auth.auth_logger import send_main_delete_log
from utils.function import (
    add_timeout_record,
    block_user,
    delete_main_account,
    get_main_account_memberno,
    get_main_account_nickname,
    get_setting_cached,
    get_conn,
    get_timeout_reason_count,
)


async def purge_user_messages(guild: Optional[discord.Guild], target_id: int) -> tuple[int, int]:
    """길드 전체 텍스트 채널에서 대상자의 메시지를 삭제하고 (채널 수, 메시지 수)를 반환"""

    if not guild or not guild.me or not target_id:
        return 0, 0

    touched_channels = 0
    deleted_count = 0

    for channel in guild.text_channels:
        perms = channel.permissions_for(guild.me)
        if not perms.read_messages or not perms.read_message_history or not perms.manage_messages:
            continue

        channel_deleted = 0
        try:
            while True:
                deleted_messages = await channel.purge(
                    limit=100,
                    check=lambda m, _tid=target_id: m.author.id == _tid,
                    bulk=False,
                )
                if not deleted_messages:
                    break
                channel_deleted += len(deleted_messages)
                await asyncio.sleep(0)
        except (discord.Forbidden, discord.HTTPException):
            continue

        if channel_deleted:
            touched_channels += 1
            deleted_count += channel_deleted

    return touched_channels, deleted_count

def setup(bot: discord.Bot):
    timeout_policy = {
        "판매 채널 구매글 작성": {
            "timeout_1_2": 1,
            "timeout_3_4": 7,
            "block_at": 5,
        },
        "거래 채널 구매,판매시 가격 미기재": {
            "timeout_1_2": 1,
            "timeout_3_4": 7,
            "block_at": 5,
        },
        "미인증 계정 거래": {
            "timeout_1_2": 7,
            "timeout_3_4": None,
            "block_at": 3,
        },
    }

    @bot.slash_command(
        name="차단id",
        description="디스코드 ID를 직접 입력해 차단합니다",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_id(
        ctx: discord.ApplicationContext,
        user_id: discord.Option(str, description="차단할 유저의 Discord ID"),  # type: ignore
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)"),  # type: ignore
        ban_member: discord.Option(
            str,
            description="서버에서 추방(벤)까지 수행할지 선택 (기본: X)",
            required=False,
            choices=["O", "X"],
            default="X",
        ),  # type: ignore
    ):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있는 명령입니다.", ephemeral=True)
            return

        try:
            discord_id = int(user_id)
        except ValueError:
            await ctx.followup.send("❌ 유효한 디스코드 ID를 입력해 주세요.", ephemeral=True)
            return

        new_blocks, already_blocked = block_user(ctx.guild_id, discord_id, reason, ctx.user.id)

        msg = [f"🚫 <@{discord_id}> 처리 결과:"]
        if new_blocks:
            msg.append("✅ 새로 차단된 정보:")
            for dtype, val in new_blocks:
                msg.append(f"- {dtype}: `{val}`")
        if already_blocked:
            msg.append("⚠️ 이미 차단된 정보:")
            for dtype, val in already_blocked:
                msg.append(f"- {dtype}: `{val}`")

        if new_blocks:
            ban_requested = ban_member == "O"
            # 🔹 멤버 객체 확인
            member = guild.get_member(discord_id)

            # 🔹 인증정보 삭제 (DB 이관)
            main_nick, sub_list = delete_main_account(ctx.guild_id, discord_id)

            # 🔹 역할/닉네임 정리 (멤버가 서버에 있을 경우만)
            kick_success = False

            if member:
                for key in ("main_auth_role", "sub_auth_role"):
                    role_id = get_setting_cached(ctx.guild_id, key)
                    if role_id:
                        role = guild.get_role(int(role_id))
                        if role:
                            try:
                                await member.remove_roles(role)
                            except discord.Forbidden:
                                pass

                try:
                    await member.edit(nick=None)
                except discord.Forbidden:
                    pass

                cleaned_channels, cleaned_messages = await purge_user_messages(guild, member.id)

                try:
                    await member.kick(reason=f"차단 조치: {reason}")
                    kick_success = True
                except (discord.Forbidden, discord.HTTPException):
                    pass

                if ban_requested:
                    try:
                        await guild.ban(member, reason=f"차단 조치: {reason}", delete_message_days=0)
                        msg.append("⛔ 서버 밴 처리 완료")
                    except (discord.Forbidden, discord.HTTPException):
                        msg.append("⚠️ 서버 밴 처리 실패(권한 확인 필요)")
            else:
                cleaned_channels, cleaned_messages = (0, 0)
                if ban_requested:
                    try:
                        await guild.ban(discord.Object(id=discord_id), reason=f"차단 조치: {reason}", delete_message_days=0)
                        msg.append("⛔ 서버 밴 처리 완료")
                    except (discord.Forbidden, discord.HTTPException):
                        msg.append("⚠️ 서버 밴 처리 실패(권한 확인 필요)")

            if cleaned_channels or cleaned_messages:
                msg.append(
                    f"🧹 메시지 삭제: {cleaned_channels}개 채널에서 {cleaned_messages}개 메시지 삭제"
                )

            if kick_success:
                msg.append(f"🚪 <@{discord_id}> 서버에서 추방 완료")

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

        await ctx.followup.send("\n".join(msg) or "⚠️ 차단할 데이터가 없습니다.", ephemeral=True)

    # 2) /차단맴버
    @bot.slash_command(
        name="차단맴버",
        description="현재 서버 멤버를 선택해 차단합니다 (본계정 + 부계정 포함)",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_member(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="차단할 서버 멤버"), # type: ignore
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)"), # type: ignore
        ban_member: discord.Option(
            str,
            description="서버에서 추방(벤)까지 수행할지 선택 (기본: X)",
            required=False,
            choices=["O", "X"],
            default="X",
        ), # type: ignore
    ):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있는 명령입니다.", ephemeral=True)
            return

        new_blocks, already_blocked = block_user(ctx.guild_id, member, reason, ctx.user.id)
        ban_requested = ban_member == "O"

        msg = [f"🚫 {member.mention} 처리 결과:"]
        if new_blocks:
            msg.append("✅ 새로 차단된 정보:")
            for dtype, val in new_blocks:
                msg.append(f"- {dtype}: `{val}`")
        if already_blocked:
            msg.append("⚠️ 이미 차단된 정보:")
            for dtype, val in already_blocked:
                msg.append(f"- {dtype}: `{val}`")

        if new_blocks:
            # 🔹 인증정보 이관 & 역할 회수
            main_nick, sub_list = delete_main_account(ctx.guild_id, member.id)

            # 역할 제거
            kick_success = False
            for key in ("main_auth_role", "sub_auth_role"):
                role_id = get_setting_cached(ctx.guild_id, key)
                if role_id:
                    role = guild.get_role(int(role_id))
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

            cleaned_channels, cleaned_messages = await purge_user_messages(guild, member.id)

            try:
                await member.kick(reason=f"차단 조치: {reason}")
                kick_success = True
            except (discord.Forbidden, discord.HTTPException):
                pass

            if ban_requested:
                try:
                    await guild.ban(member, reason=f"차단 조치: {reason}", delete_message_days=0)
                    msg.append("⛔ 서버 밴 처리 완료")
                except (discord.Forbidden, discord.HTTPException):
                    msg.append("⚠️ 서버 밴 처리 실패(권한 확인 필요)")
            if cleaned_channels or cleaned_messages:
                msg.append(
                    f"🧹 메시지 삭제: {cleaned_channels}개 채널에서 {cleaned_messages}개 메시지 삭제"
                )

            if kick_success:
                msg.append(f"🚪 {member.mention} 서버에서 추방 완료")

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

        await ctx.followup.send("\n".join(msg), ephemeral=True)

    @bot.slash_command(
        name="타임아웃",
        description="서버 멤버를 사유별 누적 차수 기준으로 자동 타임아웃/차단 처리합니다",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def timeout_member(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="타임아웃 처리할 서버 멤버"),  # type: ignore
        reason: discord.Option(  # type: ignore
            str,
            description="타임아웃 사유",
            choices=[
                "판매 채널 구매글 작성",
                "거래 채널 구매,판매시 가격 미기재",
                "미인증 계정 거래",
            ],
        ),
    ):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있는 명령입니다.", ephemeral=True)
            return

        policy = timeout_policy.get(reason)
        if not policy:
            await ctx.followup.send("❌ 유효하지 않은 타임아웃 사유입니다.", ephemeral=True)
            return

        prior_count = get_timeout_reason_count(ctx.guild_id, member.id, reason)
        current_count = prior_count + 1

        # 차단 기준 도달 시 타임아웃 대신 차단
        if current_count >= policy["block_at"]:
            block_reason = f"[{reason}] 누적 {current_count}회차(기준 도달)"
            new_blocks, already_blocked = block_user(ctx.guild_id, member, block_reason, ctx.user.id)

            msg = [f"🚫 {member.mention} 자동 차단 처리 결과 (사유: {reason})"]
            msg.append(f"- 누적 차수: `{current_count}회`")

            if new_blocks:
                msg.append("✅ 새로 차단된 정보:")
                for dtype, val in new_blocks:
                    msg.append(f"- {dtype}: `{val}`")
            if already_blocked:
                msg.append("⚠️ 이미 차단된 정보:")
                for dtype, val in already_blocked:
                    msg.append(f"- {dtype}: `{val}`")

            if new_blocks:
                for key in ("main_auth_role", "sub_auth_role"):
                    role_id = get_setting_cached(ctx.guild_id, key)
                    if role_id:
                        role = guild.get_role(int(role_id))
                        if role:
                            try:
                                await member.remove_roles(role)
                            except discord.Forbidden:
                                pass

                await broadcast_block_log(
                    bot,
                    blocked_gid=ctx.guild_id,
                    target_user=member,
                    raw_user_id=member.id,
                    new_blocks=new_blocks,
                    reason=block_reason,
                    blocked_by=ctx.user.id,
                )

            await ctx.followup.send("\n".join(msg), ephemeral=True)
            return

        timeout_days = policy["timeout_1_2"] if current_count <= 2 else policy["timeout_3_4"]
        if not timeout_days:
            await ctx.followup.send("❌ 타임아웃 기간 정책을 찾지 못했습니다.", ephemeral=True)
            return

        main_role_id = get_setting_cached(ctx.guild_id, "main_auth_role")
        if not main_role_id:
            await ctx.followup.send("❌ 본계정 인증 역할(main_auth_role)이 설정되지 않았습니다.", ephemeral=True)
            return

        main_member_no = get_main_account_memberno(ctx.guild_id, member.id)
        main_nick = get_main_account_nickname(ctx.guild_id, member.id)
        start_at, end_at = add_timeout_record(
            guild_id=ctx.guild_id,
            discord_id=member.id,
            stove_member_no=main_member_no,
            nickname=main_nick or member.display_name,
            reason=reason,
            timeout_days=timeout_days,
            created_by=ctx.user.id,
        )

        main_role = guild.get_role(int(main_role_id)) if str(main_role_id).isdigit() else None
        if main_role:
            try:
                await member.remove_roles(main_role, reason=f"타임아웃 처리: {reason}")
            except discord.Forbidden:
                pass

        end_text = end_at.strftime("%Y-%m-%d %H:%M(KST)")
        timeout_channel_id = get_setting_cached(ctx.guild_id, "timeout_channel")
        channel_mention = (
            f"<#{timeout_channel_id}>"
            if timeout_channel_id and str(timeout_channel_id).isdigit()
            else "타임아웃 채널"
        )

        try:
            await member.send(
                "📢 서버 규칙 위반으로 타임아웃이 적용되었습니다.\n"
                f"- 사유: {reason}\n"
                f"- 현재 차수: {current_count}회차\n"
                f"- 제재 기간: {timeout_days}일\n"
                f"- 해제 가능 시각: {end_text}\n\n"
                f"제재 기간이 지난 뒤 {channel_mention} 에서 `타임아웃 해제하기` 버튼을 눌러주세요."
            )
        except discord.Forbidden:
            pass

        await ctx.followup.send(
            "\n".join(
                [
                    f"⏳ {member.mention} 타임아웃 처리 완료",
                    f"- 사유: `{reason}`",
                    f"- 누적 차수: `{current_count}회`",
                    f"- 제재 기간: `{timeout_days}일`",
                    f"- 시작 시각: `{start_at.strftime('%Y-%m-%d %H:%M(KST)')}`",
                    f"- 해제 가능 시각: `{end_text}`",
                ]
            ),
            ephemeral=True,
        )

    @bot.slash_command(
        name="차단닉네임",
        description="로스트아크 닉네임을 기준으로 차단합니다",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_nickname(
        ctx: discord.ApplicationContext,
        nickname: discord.Option(str, description="차단할 로스트아크 닉네임"),
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)"),
    ):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있는 명령입니다.", ephemeral=True)
            return

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT discord_user_id FROM auth_accounts_{ctx.guild_id}
                WHERE nickname = %s
                UNION
                SELECT DISTINCT discord_user_id FROM auth_sub_accounts_{ctx.guild_id}
                WHERE nickname = %s
                """,
                (nickname, nickname),
            )
            discord_ids = [row[0] for row in cur.fetchall() if row[0]]

        if not discord_ids:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM blocked_users
                    WHERE guild_id = %s AND data_type = 'nickname' AND value = %s
                    AND unblocked_at IS NULL
                    """,
                    (ctx.guild_id, nickname),
                )
                already_blocked = cur.fetchone() is not None

                if already_blocked:
                    await ctx.followup.send(
                        f"⚠️ 닉네임 `{nickname}` 은(는) 이미 차단되어 있습니다.",
                        ephemeral=True,
                    )
                    return

                cur.execute(
                    """
                    INSERT INTO blocked_users
                        (guild_id, data_type, value, reason, created_at, blocked_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (ctx.guild_id, "nickname", nickname, reason, datetime.utcnow(), ctx.user.id),
                )
                conn.commit()

            await broadcast_block_log(
                bot,
                blocked_gid=ctx.guild_id,
                target_user=None,
                raw_user_id=None,
                new_blocks=[("nickname", nickname)],
                reason=reason,
                blocked_by=ctx.user.id,
            )
            await ctx.followup.send(
                f"✅ 닉네임 `{nickname}` 을(를) 차단했습니다.",
                ephemeral=True,
            )
            return

        msg = [f"🚫 닉네임 `{nickname}` 에 연결된 계정 처리 결과:"]

        for discord_id in discord_ids:
            new_blocks, already_blocked = block_user(ctx.guild_id, discord_id, reason, ctx.user.id)

            msg.append(f"- <@{discord_id}>")
            if new_blocks:
                msg.append("  ✅ 새로 차단된 정보:")
                for dtype, val in new_blocks:
                    msg.append(f"  - {dtype}: `{val}`")
            if already_blocked:
                msg.append("  ⚠️ 이미 차단된 정보:")
                for dtype, val in already_blocked:
                    msg.append(f"  - {dtype}: `{val}`")

            if new_blocks:
                member = guild.get_member(discord_id)
                main_nick, sub_list = delete_main_account(ctx.guild_id, discord_id)
                kick_success = False

                if member:
                    for key in ("main_auth_role", "sub_auth_role"):
                        role_id = get_setting_cached(ctx.guild_id, key)
                        if role_id:
                            role = guild.get_role(int(role_id))
                            if role:
                                try:
                                    await member.remove_roles(role)
                                except discord.Forbidden:
                                    pass

                    try:
                        await member.edit(nick=None)
                    except discord.Forbidden:
                        pass

                    cleaned_channels, cleaned_messages = await purge_user_messages(guild, member.id)

                    try:
                        await member.kick(reason=f"차단 조치: {reason}")
                        kick_success = True
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                else:
                    cleaned_channels, cleaned_messages = (0, 0)

                if cleaned_channels or cleaned_messages:
                    msg.append(
                        f"  🧹 메시지 삭제: {cleaned_channels}개 채널에서 {cleaned_messages}개 메시지 삭제"
                    )

                if kick_success:
                    msg.append(f"  🚪 <@{discord_id}> 서버에서 추방 완료")

                await broadcast_block_log(
                    bot,
                    blocked_gid=ctx.guild_id,
                    target_user=member,
                    raw_user_id=discord_id,
                    new_blocks=new_blocks,
                    reason=reason,
                    blocked_by=ctx.user.id,
                )

                await send_main_delete_log(
                    ctx.bot,
                    ctx.guild_id,
                    member or discord_id,
                    main_nick,
                    sub_list,
                )

        await ctx.followup.send("\n".join(msg), ephemeral=True)



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
    bot_user_id = bot.user.id if bot.user else None
    if bot_user_id and blocked_by == bot_user_id:
        blocked_by_display = "[봇]"
    elif blocked_by:
        blocked_by_display = f"<@{blocked_by}>"
    else:
        blocked_by_display = "알 수 없음"
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
    embed.add_field(name="차단자", value=f"[{server_name}] {blocked_by_display}", inline=False)

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
