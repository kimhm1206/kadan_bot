from utils.function import (
    get_main_account_memberno,
    get_sub_accounts_membernos,
    fetch_character_list,
    fetch_character_list_by_nickname,
    get_sub_accounts
)
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