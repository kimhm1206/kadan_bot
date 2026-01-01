import asyncio
from datetime import datetime
from typing import Optional

import discord

from auth.auth_logger import send_main_delete_log
from utils.function import (
    block_user,
    delete_main_account,
    fetch_character_list_by_nickname,
    get_setting_cached,
    get_conn,
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
        
        
        
        
        
        
        
        
        
    # 3) /차단닉네임
    @bot.slash_command(
        name="차단닉네임",
        description="로스트아크 닉네임을 기준으로 차단합니다",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def block_by_nickname(
        ctx: discord.ApplicationContext,
        nickname: discord.Option(str, description="차단할 로스트아크 닉네임"),
        reason: discord.Option(str, description="차단 사유 & 차단자 ex:(카단,주우자악8)"),
        ban_member: discord.Option(
            str,
            description="서버에서 추방까지 수행할지 선택 (기본: X)",
            required=False,
            choices=["O", "X"],
            default="X",
        ),
    ):
        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있는 명령입니다.", ephemeral=True)
            return

        characters = await fetch_character_list_by_nickname(nickname)
        if not characters:
            await ctx.followup.send("⚠️ 해당 닉네임으로 캐릭터 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        nickname_set = {c.get("CharacterName") for c in characters if c.get("CharacterName")}
        extra_values = [("nickname", n) for n in nickname_set if n and n != nickname]

        # 🔎 닉네임으로 조회된 모든 캐릭터의 memberNo를 역추적하여 연결된 디스코드/부계정까지 차단 대상에 포함
        member_nos: set[str] = set()
        for char in characters:
            member_no = char.get("MemberNo") or char.get("memberNo")
            if member_no:
                member_nos.add(str(member_no))

        # memberNo 기준으로 본/부계정 테이블에서 연결된 discord_id와 stove_member_no, nickname을 수집
        with get_conn() as conn, conn.cursor() as cur:
            for member_no in member_nos:
                extra_values.append(("memberNo", member_no))

                for table in (
                    f"auth_accounts_{ctx.guild_id}",
                    f"deleted_auth_accounts_{ctx.guild_id}",
                    f"auth_sub_accounts_{ctx.guild_id}",
                    f"deleted_auth_sub_accounts_{ctx.guild_id}",
                ):
                    cur.execute(
                        f"SELECT discord_user_id, stove_member_no, nickname FROM {table} WHERE stove_member_no = %s",
                        (member_no,),
                    )
                    for did, stove_no, nick in cur.fetchall():
                        if did:
                            extra_values.append(("discord_id", str(did)))
                        if stove_no:
                            extra_values.append(("memberNo", stove_no))
                        if nick:
                            extra_values.append(("nickname", nick))

        new_blocks, already_blocked = block_user(
            ctx.guild_id,
            nickname,
            reason,
            ctx.user.id,
            extra_values=extra_values,
        )

        ban_requested = ban_member == "O"
        msg = [f"🚫 닉네임 `{nickname}` 처리 결과:"]
        if new_blocks:
            msg.append("✅ 새로 차단된 정보:")
            for dtype, val in new_blocks:
                msg.append(f"- {dtype}: `{val}`")
        if already_blocked:
            msg.append("⚠️ 이미 차단된 정보:")
            for dtype, val in already_blocked:
                msg.append(f"- {dtype}: `{val}`")

        cleaned_report: list[str] = []
        processed_users: set[int] = set()

        for dtype, val in new_blocks:
            if dtype == "discord_id":
                try:
                    processed_users.add(int(val))
                except ValueError:
                    continue

        for user_id in processed_users:
            member = guild.get_member(user_id)
            main_nick, sub_list = delete_main_account(ctx.guild_id, user_id)
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
                cleaned_report.append(
                    f"🧹 <@{user_id}>: {cleaned_channels}개 채널에서 {cleaned_messages}개 메시지 삭제"
                )

            if kick_success:
                cleaned_report.append(f"🚪 <@{user_id}> 서버에서 추방 완료")

            if ban_requested:
                try:
                    await guild.ban(member or discord.Object(id=user_id), reason=f"차단 조치: {reason}", delete_message_days=0)
                    cleaned_report.append("⛔ 서버 밴 처리 완료")
                except (discord.Forbidden, discord.HTTPException):
                    cleaned_report.append("⚠️ 서버 밴 처리 실패(권한 확인 필요)")

            await send_main_delete_log(
                ctx.bot,
                ctx.guild_id,
                member or user_id,
                main_nick,
                sub_list,
            )

        if cleaned_report:
            msg.extend(cleaned_report)

        if new_blocks:
            if processed_users:
                for discord_id in processed_users:
                    target_member = guild.get_member(discord_id)
                    filtered_blocks = []
                    for item in new_blocks:
                        dtype, value = item
                        if dtype != "discord_id":
                            filtered_blocks.append(item)
                            continue
                        try:
                            if int(value) == discord_id:
                                filtered_blocks.append(item)
                        except ValueError:
                            filtered_blocks.append(item)
                    await broadcast_block_log(
                        bot,
                        blocked_gid=ctx.guild_id,
                        target_user=target_member,
                        raw_user_id=discord_id,
                        new_blocks=filtered_blocks or new_blocks,
                        reason=reason,
                        blocked_by=ctx.user.id,
                    )
            else:
                await broadcast_block_log(
                    bot,
                    blocked_gid=ctx.guild_id,
                    target_user=None,
                    raw_user_id=None,
                    new_blocks=new_blocks,
                    reason=reason,
                    blocked_by=ctx.user.id,
                )

        await ctx.followup.send("\n".join(msg), ephemeral=True)
