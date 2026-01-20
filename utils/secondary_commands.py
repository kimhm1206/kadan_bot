import discord
from utils.function import delete_main_account, get_auth_discord_ids, get_conn


def setup(bot: discord.Bot):
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
                    (rid, discord_id, member_no, nickname, is_verified, created_at, verified_at, deleted_at, retain_until) = row
                    lines.append(
                        f"[삭제 본계정] id={rid} discord_id={discord_id} memberNo={member_no} "
                        f"nickname={nickname} verified={is_verified} created_at={created_at} "
                        f"verified_at={verified_at} deleted_at={deleted_at} retain_until={retain_until}"
                    )
                elif table_key == "deleted_auth_sub_accounts":
                    (rid, discord_id, sub_number, member_no, nickname, created_at, deleted_at, retain_until) = row
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
