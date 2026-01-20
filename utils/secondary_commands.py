import discord
from utils.function import delete_main_account, get_auth_discord_ids


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
