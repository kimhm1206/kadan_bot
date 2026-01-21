import discord
from utils.function import get_all_settings
from utils.cache import settings_cache
from auth.auth_view import AuthMainView
from auth.auth_embed import build_auth_embed
from ticket.ticket_embed import build_ticket_panel_embed
from ticket.ticket_view import TicketPanelView


async def send_default_message(bot: discord.Bot, guild_id: int = None,
                               old_channel: discord.TextChannel = None,
                               new_channel: discord.TextChannel = None,
                               type: str = None):
    """
    기본 메시지(인증/티켓 패널 등) 전송 함수

    - 봇 첫 실행 시: guild_id/old_channel/new_channel/type 모두 None → 모든 길드 전체 재전송
    - 설정 변경 시: guild_id + old_channel/new_channel/type 지정 → 해당 채널만 갱신
    - ⚠️ admin_channel 은 여기서 처리하지 않음 (별도 로직에서 관리)
    """

    # 1️⃣ 봇 첫 실행 시: 모든 길드 전체 처리
    if guild_id is None:
        all_settings = settings_cache or get_all_settings()
        if not settings_cache:
            settings_cache.update(all_settings)

        for g in bot.guilds:
            settings = all_settings.get(g.id, {})

            # 인증 패널
            verify_channel_id = settings.get("verify_channel")
            if verify_channel_id and verify_channel_id.isdigit():
                verify_channel = g.get_channel(int(verify_channel_id))
                if verify_channel:
                    await _replace_message(
                        verify_channel,
                        build_auth_embed(),
                        AuthMainView()
                    )

            # 티켓 패널
            ticket_channel_id = settings.get("ticket_channel")
            if ticket_channel_id and ticket_channel_id.isdigit():
                ticket_channel = g.get_channel(int(ticket_channel_id))
                if ticket_channel:
                    await _replace_message(
                        ticket_channel,
                        build_ticket_panel_embed(g.id),
                        TicketPanelView()
                    )
        return

    # 2️⃣ 설정 변경 시: 특정 타입만 갱신 (admin_channel 제외)
    if type == "verify_channel":
        if old_channel:
            await _delete_bot_messages(old_channel)
        if new_channel:
            await new_channel.send(embed=build_auth_embed(),
                                   view=AuthMainView())

    elif type == "ticket_channel":
        if old_channel:
            await _delete_bot_messages(old_channel)
        if new_channel:
            await new_channel.send(
                embed=build_ticket_panel_embed(new_channel.guild.name),
                view=TicketPanelView()
            )


async def _delete_bot_messages(channel: discord.TextChannel):
    """최근 50개 메시지 중 봇이 보낸 메시지만 삭제"""
    try:
        pinned = []
        try:
            pinned = await channel.pins()
        except Exception:
            pinned = []

        deleted_ids = set()
        for msg in pinned:
            if msg.author.bot and msg.id not in deleted_ids:
                await msg.delete()
                deleted_ids.add(msg.id)

        async for msg in channel.history(limit=50):
            if msg.author.bot and msg.id not in deleted_ids:
                await msg.delete()
                deleted_ids.add(msg.id)
    except Exception as e:
        print(f"⚠️ 메시지 삭제 실패: {e}")


async def _replace_message(channel: discord.TextChannel, embed: discord.Embed = None, view: discord.ui.View = None):
    """기존 메시지 삭제 후 새 메시지 전송"""
    await _delete_bot_messages(channel)
    try:
        if embed or view:
            await channel.send(embed=embed, view=view)
    except Exception as e:
        print(f"⚠️ 메시지 전송 실패: {e}")
