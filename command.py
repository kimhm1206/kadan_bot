import discord
from discord.ext import commands
from discord import option
from function import update_setting
from function import get_user_sub_accounts, get_lostark_account_set
from delete import SubAccountCancelView

def setup(bot: discord.Bot):

    @bot.slash_command(name="인증방식", description="인증 방식을 설정합니다 (관리자 전용)",default_member_permissions=discord.Permissions(administrator=True))
    # @bot.slash_command(name="인증방식", description="인증 방식을 설정합니다 (관리자 전용)")
    async def set_auth_type(
        ctx: discord.ApplicationContext,
        auth: discord.Option(str, "인증 방식 선택", choices=["main", "admin"]) # type: ignore
    ):  
        await ctx.defer(ephemeral=True)
        success = update_setting("auth", auth)
        if success:
            await ctx.followup.send(f"✅ 인증 방식이 `{auth}`(으)로 설정되었습니다.")
        else:
            await ctx.followup.send("❌ 설정 변경에 실패했습니다.")

    @bot.slash_command(name="최대부계정수", description="최대 부계정 수를 설정합니다 (1~3)",default_member_permissions=discord.Permissions(administrator=True))
    # @bot.slash_command(name="최대부계정수", description="최대 부계정 수를 설정합니다 (1~3)")
    async def set_max_subs(
        ctx: discord.ApplicationContext,
        count: discord.Option(int, "최대 부계정 수", choices=[1, 2, 3]) # type: ignore
    ):
        await ctx.defer(ephemeral=True)
        success = update_setting("max_subs", str(count))

        if success:
            await ctx.followup.send(f"✅ 최대 부계정 수가 `{count}`개로 설정되었습니다.", ephemeral=True)
        else:
            await ctx.followup.send("❌ 설정 변경에 실패했습니다.", ephemeral=True)
            
    @bot.slash_command(name="부계정인증관리", description="다른 유저의 부계정 인증을 관리합니다.",default_member_permissions=discord.Permissions(administrator=True))
    # @bot.slash_command(name="부계정인증관리", description="다른 유저의 부계정 인증을 관리합니다.")
    @discord.option("member", description="부계정을 관리할 대상 유저", type=discord.Member)
    async def 부계정인증관리(ctx: discord.ApplicationContext, member: discord.Member):
        subs = get_user_sub_accounts(member.id)
        if not subs:
            await ctx.respond("❌ 해당 유저는 등록된 부계정이 없습니다.", ephemeral=True)
            return

        await ctx.respond(
            f"📋 `{member.display_name}` 님의 부계정 목록입니다.",
            view=SubAccountCancelView(user=member, sub_list=subs),
            ephemeral=True
        )
        
    @bot.slash_command(name="타인본계정인증",description="타인의 본계정을 부계정으로 등록 가능한지 설정합니다 (관리자 전용)",default_member_permissions=discord.Permissions(administrator=True))
    # @bot.slash_command(name="타인본계정인증",description="타인의 본계정을 부계정으로 등록 가능한지 설정합니다.")
    async def set_foreign_main_policy(
        ctx: discord.ApplicationContext,
        policy: discord.Option(
            str,
            "등록 정책 선택",
            choices=["가능", "불가능", "조건부"]
        ) # type: ignore
    ):
        await ctx.defer(ephemeral=True)
        success = update_setting("allow_foreign_main", policy)

        if success:
            await ctx.followup.send(f"✅ 타인 본계정 등록 정책이 `{policy}`(으)로 설정되었습니다.")
        else:
            await ctx.followup.send("❌ 설정 변경에 실패했습니다.")
            
    @bot.slash_command(name="계정확인", description="유저의 계정이 입력한 닉네임과 같은 계정인지 확인합니다.")
    @option("member", description="대상 디스코드 유저", type=discord.Member)
    @option("nickname", description="확인할 로스트아크 닉네임", type=str)
    async def 계정확인(ctx: discord.ApplicationContext, member: discord.Member, nickname: str):
        await ctx.defer(ephemeral=True)

        # ✅ 1. 닉네임 정리
        original_nick = member.nick or member.global_name
        cleaned_nick = original_nick.replace(" / 부계정O", "").strip()

        # ✅ 2. 본캐 닉 API 조회
        base_set = await get_lostark_account_set(cleaned_nick)
        if base_set and nickname in base_set:
            await ctx.followup.send(
                f"✅ `{nickname}` 은(는) 해당 유저의 **본계정** 계정 목록에 존재합니다.",
                ephemeral=True
            )
            return

        # ✅ 3. 부계정 닉 API 조회
        sub_list = get_user_sub_accounts(member.id)
        for sub in sub_list:
            sub_set = await get_lostark_account_set(sub)
            if sub_set and nickname in sub_set:
                await ctx.followup.send(
                    f"✅ `{nickname}` 은(는) 해당 유저의 **부계정** 목록에 존재합니다.",
                    ephemeral=True
                )
                return

        # ✅ 4. 불일치
        await ctx.followup.send(
            f"❌ `{nickname}` 은(는) 해당 유저의 계정에 등록되어 있지 않습니다.\n한 번 더 확인해주세요.",
            ephemeral=True
        )
    

        
        