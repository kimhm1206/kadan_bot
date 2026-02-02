from utils.function import get_setting_cached
from ticket.ticket_create import archive_ticket_channel
import discord

def setup(bot: discord.Bot):
    @bot.slash_command(
        name="문의삭제",
        description="현재 문의 채널을 로그에 남기고 삭제합니다.",
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def delete_ticket_channel(ctx: discord.ApplicationContext):
        channel = ctx.channel

        if not ctx.guild or channel is None or not isinstance(channel, discord.TextChannel):
            await ctx.respond("⚠️ 길드 텍스트 채널에서만 사용할 수 있습니다.", ephemeral=True)
            return

        if not ctx.author.guild_permissions.administrator:
            await ctx.respond("⚠️ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return

        category_id = get_setting_cached(ctx.guild_id, "ticket_category")
        if not category_id or not str(category_id).isdigit():
            await ctx.respond("⚠️ 문의 카테고리가 설정되어 있지 않습니다.", ephemeral=True)
            return

        if not channel.category or channel.category.id != int(category_id):
            await ctx.respond("⚠️ 문의 카테고리 내부에서만 사용할 수 있는 명령어입니다.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        log_channel = None
        log_channel_id = get_setting_cached(ctx.guild_id, "ticket_log_channel")
        if log_channel_id and str(log_channel_id).isdigit():
            fetched = ctx.guild.get_channel(int(log_channel_id))
            if isinstance(fetched, discord.TextChannel):
                log_channel = fetched

        name_parts = channel.name.split("-")
        ticket_type = name_parts[1] if len(name_parts) >= 2 else "문의"

        try:
            await archive_ticket_channel(
                channel=channel,
                deleter=ctx.author,
                log_channel=log_channel,
                ticket_type=ticket_type,
                owner_label="알 수 없음",
            )
        except discord.Forbidden:
            await ctx.followup.send("⚠️ 채널 삭제 권한이 부족합니다.", ephemeral=True)
            return
        except Exception as exc:
            await ctx.followup.send(
                f"⚠️ 채널 삭제 중 오류가 발생했습니다: {exc}",
                ephemeral=True,
            )
            return

        await ctx.followup.send("🗑️ 문의 채널을 삭제했습니다.", ephemeral=True)
