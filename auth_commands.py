import re

import discord

from auth.auth_logger import send_main_delete_log
from utils.function import (
    delete_main_account,
    fetch_character_list,
    fetch_character_list_by_nickname,
    get_auth_discord_ids,
    get_conn,
    get_main_account_memberno,
    get_setting_cached,
    get_sub_accounts,
    get_sub_accounts_membernos,
)


def setup(bot: discord.Bot):
    @bot.slash_command(
        name="계정확인",
        description="유저의 계정이 입력한 닉네임과 같은 계정인지 확인합니다.",
    )
    async def 계정확인(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="대상 디스코드 유저"),  # type: ignore
        nickname: discord.Option(str, description="확인할 로스트아크 닉네임"),  # type: ignore
    ):
        await ctx.defer(ephemeral=True)
        guild_id = ctx.guild_id

        # ✅ 1. 본계정 memberNo 확인
        main_member_no = get_main_account_memberno(guild_id, member.id)
        if main_member_no:
            characters = await fetch_character_list(main_member_no, guild_id)
            if characters and any(c["CharacterName"] == nickname for c in characters):
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 해당 유저의 **본계정** 캐릭터 목록에 존재합니다.",
                    ephemeral=True,
                )
                return

        # ✅ 2. 부계정 memberNo 확인
        sub_membernos = get_sub_accounts_membernos(guild_id, member.id)
        for sub_no in sub_membernos:
            characters = await fetch_character_list(sub_no, guild_id)
            if characters and any(c["CharacterName"] == nickname for c in characters):
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 해당 유저의 **부계정** 캐릭터 목록에 존재합니다.",
                    ephemeral=True,
                )
                return

        # ✅ 3. 부계정 중 memberNo 없는 경우 → 닉네임 기반
        sub_accounts = get_sub_accounts(guild_id, member.id)  # [(sub_number, nickname), ...]
        for _, sub_nick in sub_accounts:
            if not sub_nick:
                continue
            characters = await fetch_character_list_by_nickname(sub_nick)
            if characters and any(c["CharacterName"] == nickname for c in characters):
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 해당 유저의 **부계정(닉네임 기반)** 캐릭터 목록에 존재합니다.",
                    ephemeral=True,
                )
                return

        # ✅ 4. 그래도 없으면 → 디스코드 닉네임 기반
        profile_nick = member.nick or member.global_name or member.name
        if profile_nick:
            # 끝의 " | 부계정O" 제거
            profile_nick = re.sub(r"\s*\|\s*부계정O\s*$", "", profile_nick)
            characters = await fetch_character_list_by_nickname(profile_nick)
            if characters and any(c["CharacterName"] == nickname for c in characters):
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 디스코드 닉네임(`{profile_nick}`) 기반 조회 결과 존재합니다.",
                    ephemeral=True,
                )
                return

        # ✅ 5. 불일치
        await ctx.followup.send(
            f"❌ `{nickname}` 은(는) 해당 유저의 계정에 등록되어 있지 않습니다.\n한 번 더 확인해주세요.",
            ephemeral=True,
        )

    @bot.slash_command(
        name="인증해제",
        description="대상 멤버의 인증 정보를 강제로 삭제합니다.",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def force_unverify(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="인증을 해제할 멤버"),  # type: ignore
    ):
        await ctx.defer(ephemeral=True)

        main_nick, sub_list = delete_main_account(ctx.guild_id, member.id)
        if not main_nick and not sub_list:
            await ctx.followup.send("⚠️ 인증 내역을 찾을 수 없습니다.", ephemeral=True)
            return

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

        await send_main_delete_log(ctx.bot, ctx.guild_id, member, main_nick, sub_list)

        lines = ["✅ 인증 정보를 강제로 삭제했습니다."]
        if main_nick:
            lines.append(f"- 본계정 `{main_nick}` 삭제")
        if sub_list:
            sub_summary = ", ".join(
                f"#{sub_num} `{nick or '닉네임 없음'}`" for sub_num, nick in sub_list
            )
            lines.append(f"- 부계정 삭제: {sub_summary}")

        await ctx.followup.send("\n".join(lines), ephemeral=True)

    @bot.slash_command(
        name="인증정리",
        description="서버에 없는 인증 기록을 정리합니다.",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def cleanup_auth_records(ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있습니다.", ephemeral=True)
            return

        discord_ids = get_auth_discord_ids(ctx.guild_id)
        if not discord_ids:
            await ctx.followup.send("✅ 정리할 인증 기록이 없습니다.", ephemeral=True)
            return

        removed_ids: list[int] = []
        kept_ids: list[int] = []

        for discord_id in discord_ids:
            member = ctx.guild.get_member(discord_id)
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(discord_id)
                except discord.NotFound:
                    member = None
                except discord.Forbidden:
                    member = None

            if member is None:
                main_nick, sub_list = delete_main_account(ctx.guild_id, discord_id)
                if main_nick or sub_list:
                    removed_ids.append(discord_id)
            else:
                kept_ids.append(discord_id)

        await ctx.followup.send(
            "\n".join(
                [
                    "✅ 인증 정리가 완료되었습니다.",
                    f"- 대상: {len(discord_ids)}명",
                    f"- 삭제 처리: {len(removed_ids)}명",
                    f"- 유지: {len(kept_ids)}명",
                ]
            ),
            ephemeral=True,
        )

    @bot.slash_command(
        name="인증검색",
        description="discord_id, nickname, stove_member_no로 인증 정보를 검색합니다.",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def search_auth_records(
        ctx: discord.ApplicationContext,
        search_type: discord.Option(
            str,
            description="검색 기준을 선택하세요",
            choices=["discord_id", "nickname", "stove_member_no"],
        ),  # type: ignore
        value: discord.Option(str, description="검색 값 입력"),  # type: ignore
    ):
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.followup.send("⚠️ 길드에서만 사용할 수 있습니다.", ephemeral=True)
            return

        guild_id = ctx.guild_id
        lookup_value = value.strip()
        if not lookup_value:
            await ctx.followup.send("⚠️ 검색 값을 입력해주세요.", ephemeral=True)
            return

        discord_ids: set[int] = set()
        rows_by_table: dict[str, list[tuple]] = {
            "auth_accounts": [],
            "auth_sub_accounts": [],
            "deleted_auth_accounts": [],
            "deleted_auth_sub_accounts": [],
        }

        def fetch_rows(cur, table_name: str, column: str, val: str):
            cur.execute(
                f"SELECT * FROM {table_name} WHERE {column} = %s",
                (val,),
            )
            return cur.fetchall()

        with get_conn() as conn, conn.cursor() as cur:
            table_map = [
                ("auth_accounts", f"auth_accounts_{guild_id}"),
                ("auth_sub_accounts", f"auth_sub_accounts_{guild_id}"),
                ("deleted_auth_accounts", f"deleted_auth_accounts_{guild_id}"),
                ("deleted_auth_sub_accounts", f"deleted_auth_sub_accounts_{guild_id}"),
            ]

            if search_type == "discord_id":
                try:
                    discord_id = int(lookup_value)
                except ValueError:
                    await ctx.followup.send("⚠️ discord_id는 숫자여야 합니다.", ephemeral=True)
                    return
                discord_ids.add(discord_id)
            else:
                column = "nickname" if search_type == "nickname" else "stove_member_no"
                for key, table in table_map:
                    rows = fetch_rows(cur, table, column, lookup_value)
                    if rows:
                        rows_by_table[key].extend(rows)
                    for row in rows:
                        discord_id = row[1]
                        if discord_id:
                            discord_ids.add(int(discord_id))

            if discord_ids:
                for table_key, table_name in table_map:
                    cur.execute(
                        f"SELECT * FROM {table_name} WHERE discord_user_id = ANY(%s)",
                        (list(discord_ids),),
                    )
                    rows_by_table[table_key] = cur.fetchall()

        def format_rows(table_key: str, rows: list[tuple]) -> list[str]:
            lines: list[str] = []
            for row in rows:
                if table_key == "auth_accounts":
                    (rid, discord_id, member_no, nickname, is_verified, created_at, verified_at, expired_at) = row
                    lines.append(
                        f"[본계정] id={rid} discord_id={discord_id} memberNo={member_no} "
                        f"nickname={nickname} verified={is_verified} created_at={created_at} "
                        f"verified_at={verified_at} expired_at={expired_at}"
                    )
                elif table_key == "auth_sub_accounts":
                    (rid, discord_id, sub_number, member_no, nickname, created_at, deleted_at) = row
                    lines.append(
                        f"[부계정] id={rid} discord_id={discord_id} sub_number={sub_number} "
                        f"memberNo={member_no} nickname={nickname} created_at={created_at} deleted_at={deleted_at}"
                    )
                elif table_key == "deleted_auth_accounts":
                    (
                        rid,
                        discord_id,
                        member_no,
                        nickname,
                        is_verified,
                        created_at,
                        verified_at,
                        deleted_at,
                        retain_until,
                    ) = row
                    lines.append(
                        f"[삭제 본계정] id={rid} discord_id={discord_id} memberNo={member_no} "
                        f"nickname={nickname} verified={is_verified} created_at={created_at} "
                        f"verified_at={verified_at} deleted_at={deleted_at} retain_until={retain_until}"
                    )
                elif table_key == "deleted_auth_sub_accounts":
                    (
                        rid,
                        discord_id,
                        sub_number,
                        member_no,
                        nickname,
                        created_at,
                        deleted_at,
                        retain_until,
                    ) = row
                    lines.append(
                        f"[삭제 부계정] id={rid} discord_id={discord_id} sub_number={sub_number} "
                        f"memberNo={member_no} nickname={nickname} created_at={created_at} "
                        f"deleted_at={deleted_at} retain_until={retain_until}"
                    )
            return lines

        output_lines: list[str] = []
        for key, rows in rows_by_table.items():
            output_lines.extend(format_rows(key, rows))

        if not output_lines:
            await ctx.followup.send("✅ 해당 조건으로 조회된 인증 기록이 없습니다.", ephemeral=True)
            return

        header = [
            "✅ 인증 검색 결과",
            f"- 검색 기준: {search_type}",
            f"- 검색 값: {lookup_value}",
            f"- discord_id 매칭: {', '.join(str(i) for i in sorted(discord_ids)) or '없음'}",
            "",
        ]

        message = "\n".join(header + output_lines)
        await ctx.followup.send(message[:1900], ephemeral=True)
