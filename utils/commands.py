from utils.function import (
    get_main_account_memberno,
    get_sub_accounts_membernos,
    fetch_character_list,
    fetch_character_list_by_nickname,
    get_sub_accounts,
    delete_main_account,
    get_setting_cached,
)
from auth.auth_logger import send_main_delete_log
from ticket.ticket_create import archive_ticket_channel
import discord, re

def setup(bot: discord.Bot):
    
    @bot.slash_command(
    name="계정확인",
    description="유저의 계정이 입력한 닉네임과 같은 계정인지 확인합니다."
    )
    async def 계정확인(
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="대상 디스코드 유저"),  # type: ignore
        nickname: discord.Option(str, description="확인할 로스트아크 닉네임"),   # type: ignore
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
                    ephemeral=True
                )
                return

        # ✅ 2. 부계정 memberNo 확인
        sub_membernos = get_sub_accounts_membernos(guild_id, member.id)
        for sub_no in sub_membernos:
            characters = await fetch_character_list(sub_no, guild_id)
            if characters and any(c["CharacterName"] == nickname for c in characters):
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 해당 유저의 **부계정** 캐릭터 목록에 존재합니다.",
                    ephemeral=True
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
                    ephemeral=True
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
                    ephemeral=True
                )
                return

        # ✅ 5. 불일치
        await ctx.followup.send(
            f"❌ `{nickname}` 은(는) 해당 유저의 계정에 등록되어 있지 않습니다.\n한 번 더 확인해주세요.",
            ephemeral=True
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
