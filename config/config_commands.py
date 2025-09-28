import discord
from discord.ext import commands
from utils.function import add_guild, set_setting, get_setting_value, is_approved, LOSTARK_SERVERS
from config.admin_view import ServerApprovalView
from config.edit_modal import ChannelSettingEditModal

ADMIN_ID = 238978205078388747

def setup(bot: discord.Bot):

    @bot.slash_command(
        name="서버등록",
        description="서버를 등록 요청합니다 (관리자 전용)",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def register_server(
        ctx: discord.ApplicationContext,
        server: discord.Option(str, "로스트아크 서버 선택", choices=LOSTARK_SERVERS)  # type: ignore
    ):
        guild = ctx.guild
        user = ctx.user
        guild_id = guild.id
        guild_name = guild.name

        # ✅ DB에 등록 요청 기록 (서버 포함)
        add_guild(guild_id, user.id, server)

        # ✅ 승인자(너)한테 DM 전송
        admin = await bot.fetch_user(ADMIN_ID)
        if admin:
            view = ServerApprovalView(
                bot=bot,
                guild_id=guild_id,
                requester=user.id,
                name=guild_name,
                server=server  # ✅ 여기서 바로 전달
            )
            try:
                await admin.send(
                    f"📌 서버 등록 요청이 들어왔습니다!\n"
                    f"디스코드 서버: **{guild_name}** (`{guild_id}`)\n"
                    f"로스트아크 서버: **{server}**\n"
                    f"요청자: {user.mention}",
                    view=view
                )
                await ctx.respond("✅ 서버 등록 요청이 전송되었습니다. 관리자의 승인을 기다려주세요.", ephemeral=True)
            except discord.Forbidden:
                await ctx.respond("❌ 관리자에게 DM을 보낼 수 없습니다. 관리자에게 수동 연락이 필요합니다.", ephemeral=True)
        else:
            await ctx.respond("❌ 관리자를 찾을 수 없습니다.", ephemeral=True)
    
    @bot.slash_command(
    name="관리자채널",
    description="관리자 채널을 설정합니다 (관리자 전용)",
    default_member_permissions=discord.Permissions(administrator=True)
)
    async def set_admin_channel(
        ctx: discord.ApplicationContext,
        channel: discord.Option(discord.TextChannel, "관리자 채널 선택")  # type: ignore
    ):
        # ✅ 길드 등록 여부 확인
        if not is_approved(ctx.guild_id):
            await ctx.respond("❌ 이 서버는 아직 등록되지 않았습니다. 먼저 `/서버등록`을 진행해주세요.", ephemeral=True)
            return

        old_value = get_setting_value(ctx.guild_id, "admin_channel")

        if old_value is None:
            # 신규 등록 → DB 저장 + 관리자 패널 메시지 전송
            set_setting(ctx.guild_id, "admin_channel", str(channel.id), ctx.user.id, reason="create")

            from config.admin_view import AdminConfigMainView, build_admin_embed
            embed = build_admin_embed(ctx.guild_id)
            view = AdminConfigMainView(bot, ctx.guild_id)
            await channel.send(embed=embed, view=view)

            await ctx.respond(f"✅ 관리자 채널이 {channel.mention}(으)로 설정되었습니다. (신규 등록)", ephemeral=True)

        else:
            # 기존 값 있음 → 모달 띄우기 (❌ defer 금지!)
            modal = ChannelSettingEditModal(ctx.guild_id, channel, ctx.user.id, "admin_channel")
            await ctx.interaction.response.send_modal(modal)
        