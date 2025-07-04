import discord
import aiohttp
import re
import random
from function import insert_sub_account, get_user_sub_count, get_max_subs,is_sub_nick_taken, get_setting, get_all_sub_nicks,save_foreign_sub_request,send_log_embed
from dmsendview import ApprovalView

OPERATING_GUILD_ID = 743375510003777618

class SubAccountModal(discord.ui.Modal):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(title="부계정 등록", timeout=300)
        self.user = interaction.user

        self.add_item(discord.ui.InputText(
            label="부계정 닉네임",
            placeholder="등록할 부계정의 닉네임을 입력하세요",
            max_length=20
        ))

        self.add_item(discord.ui.InputText(
            label="전투정보실 링크",
            placeholder="https://lostark.game.onstove.com/Profile/Member?id=xxx",
            max_length=200
        ))

    async def callback(self, interaction: discord.Interaction):
        sub_nick = self.children[0].value.strip()
        profile_url = self.children[1].value.strip()
        discord_id = self.user.id

        # 닉네임 검증용
        match = re.search(r"[?&]id=([^&]+)", profile_url)
        if not match:
            await interaction.response.send_message("❌ 전투정보실 링크가 올바르지 않습니다.", ephemeral=True)
            return

        # HTML 파싱
        async with aiohttp.ClientSession() as session:
            async with session.get(profile_url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ 전투정보실 페이지를 불러오지 못했습니다.", ephemeral=True)
                    return
                html = await resp.text()
        # 대표 캐릭터 추출
        if "최신화된 캐릭터 정보가 존재하지 않습니다." in html:
            await interaction.response.send_message(
                "❌ 최신화된 캐릭터 정보가 존재하지 않습니다.\n게임에 접속하여 캐릭터 정보를 최신화 시켜주세요.",
                ephemeral=True
            )
            return
        
        rep_match = re.search(r'<span class="profile-character-info__name" title="(.*?)">', html)
        if not rep_match:
            await interaction.response.send_message("❌ 대표 캐릭터를 찾을 수 없습니다.", ephemeral=True)
            return

        rep_char = rep_match.group(1)

        # 캐릭터 목록 추출
        char_list = re.findall(r'/Profile/Character/(.*?)"', html)
        char_list = list(set(name.strip("'") for name in char_list))

        if sub_nick not in char_list:
            await interaction.response.send_message(
                f"❌ `{sub_nick}` 닉네임은 해당 전투정보실에 존재하지 않습니다.", ephemeral=True
            )
            return

        char_set = set(char_list)  # 중복 제거 및 빠른 조회
        
        for char in char_set:
            if is_sub_nick_taken(char):
                await interaction.response.send_message(
                    f"❌ `{char}` 닉네임은 다른 유저의 부계정으로 이미 등록되어 있습니다.",
                    ephemeral=True
                )
                return

        # [2] 운영 정책 확인
        allow_policy = get_setting("allow_foreign_main")

        if allow_policy == "불가능" or allow_policy == "조건부":
            guild = interaction.client.get_guild(OPERATING_GUILD_ID)
            if not guild:
                await interaction.response.send_message("❌ 운영 서버 정보를 불러올 수 없습니다.", ephemeral=True)
                return

            for member in guild.members:
                if member.id == discord_id:
                    continue  # 본인은 제외

                member_nick = member.nick
                if member_nick == None:    
                    member_nick = member.display_name or member.global_name
                    
                clean_nick = member_nick.replace(" / 부계정O", "").strip()
                if clean_nick in char_set:
                    if allow_policy == "불가능":
                        await interaction.response.send_message(
                            f"❌ `{member_nick}` 닉네임은 다른 유저의 계정으로 추정되어 등록할 수 없습니다.",
                            ephemeral=True
                        )
                        return

                    elif allow_policy == "조건부":
                        # ✅ 조건부 승인 View 호출 (아직 구현 안 된 상태)
                        from registerview import RequestConfirmationView
                        await interaction.response.edit_message(
                            embed=discord.Embed(
                                title="📌 조건부 등록 안내",
                                description=(
                                    "이 계정은 카단 서버에 등록된 다른 유저의 본계정으로 추정됩니다.\n\n"
                                    "**등록을 위해 해당 유저의 승인 절차가 필요합니다.**\n\n"
                                    "계속 진행하시겠습니까?"
                                ),
                                color=discord.Color.orange()
                            ),
                            view=RequestConfirmationView(
                                requester=interaction.user,
                                target_user=member,
                                sub_nick=sub_nick,
                                profile_url=profile_url
                            ),
                        )
                        return
                    
        
        # 전환 후보 선택
        candidate = [c for c in char_list if c != sub_nick]
        if not candidate:
            await interaction.response.send_message("❌ 대표 캐릭터를 바꿀 수 있는 다른 캐릭터가 없습니다.", ephemeral=True)
            return

        selected = random.choice(candidate)

        # 대표 캐릭터 변경 안내
        embed = discord.Embed(
            title="대표 캐릭터 인증",
            description=f"현재 대표 캐릭터는 `{rep_char}` 입니다.\n`{selected}` 캐릭터로 대표 캐릭터를 변경한 뒤 아래 확인 버튼을 눌러주세요.",
            color=discord.Color.blurple()
        )
        await interaction.response.edit_message(
            embed=embed,attachments=[],
            view=ConfirmAuthView(user=self.user, sub_nick=sub_nick, profile_url=profile_url, expected_main=selected)
        )


class ConfirmAuthView(discord.ui.View):
    def __init__(self, user, sub_nick, profile_url, expected_main, is_conditional=False, target_user=None):
        super().__init__(timeout=300)
        self.user = user
        self.sub_nick = sub_nick
        self.profile_url = profile_url
        self.expected_main = expected_main
        self.is_conditional = is_conditional
        self.target_user = target_user  # 조건부 승인 시 대상 유저

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.success)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 대표 캐릭터 재확인
        perm_error = False
        async with aiohttp.ClientSession() as session:
            async with session.get(self.profile_url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ 전투정보실 재조회 실패", ephemeral=True)
                    return
                html = await resp.text()

        if "최신화된 캐릭터 정보가 존재하지 않습니다." in html:
            await interaction.response.send_message(
                "❌ 최신화된 캐릭터 정보가 존재하지 않습니다.\n게임에 접속하여 캐릭터 정보를 최신화 시켜주세요.",
                ephemeral=True
            )
            return

        rep_match = re.search(r'<span class="profile-character-info__name" title="(.*?)">', html)
        if not rep_match:
            await interaction.response.send_message("❌ 대표 캐릭터 추출 실패", ephemeral=True)
            return

        current_main = rep_match.group(1)
        if current_main != self.expected_main:
            await interaction.response.send_message(
                f"❌ 대표 캐릭터가 `{self.expected_main}`로 변경되지 않았습니다.",
                ephemeral=True
            )
            return

        # ✅ 인증 완료
        discord_id = self.user.id
        sub_nick = self.sub_nick
        sub_num = get_user_sub_count(discord_id) + 1
        max_subs = get_max_subs()

        if sub_num > max_subs:
            await interaction.response.send_message(
                f"⚠️ 최대 부계정 수({max_subs})를 초과하여 등록할 수 없습니다.",
                ephemeral=True
            )
            return

        # ✅ 조건부 등록 → 요청만 저장 + DM 전송
        if self.is_conditional:
            saved = save_foreign_sub_request(discord_id, self.target_user.id, sub_nick)
            if saved:
                try:
                    dm_embed = discord.Embed(
                        title="📩 부계정 등록 요청",
                        description=(
                            f"`{interaction.user.display_name}` 님이\n"
                            f"당신의 본계정 `{current_main}` 을(를)\n"
                            f"부계정으로 등록하려고 합니다.\n\n"
                            f"허용하시겠습니까?"
                        ),
                        color=discord.Color.orange()
                    )
                    await self.target_user.send(
                        embed=dm_embed,
                        view=ApprovalView(
                            requester_id=discord_id,
                            sub_nick=sub_nick
                        )
                    )
                except Exception as e:
                    print(f"[❌ DM 전송 실패] {type(e).__name__}: {e}")

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="⏳ 등록 요청 전송됨",
                    description="해당 유저에게 등록 요청을 보냈습니다. 응답에 따라 등록이 처리됩니다. \n결과는 DM으로 발송됩니다.",
                    color=discord.Color.blue()
                ),
                view=None
            )
            return

        # ✅ 일반 등록
        main_nick = self.user.nick or self.user.global_name
        success = insert_sub_account(discord_id, main_nick, sub_nick, sub_num)

        if success:
            # ✅ 닉네임 강제 변경
            member = interaction.guild.get_member(discord_id)
            current_nick = member.nick or member.global_name

            if "/ 부계정O" not in current_nick:
                new_nick = f"{current_nick} / 부계정O"
                try:
                    await member.edit(nick=new_nick, reason="부계정 인증 성공 후 자동 닉네임 갱신")
                    await send_log_embed(
                                bot=interaction.client,
                                user=member,
                                main_nick=sub_nick
                            )
                except discord.Forbidden:
                    print("❌ 닉네임 변경 권한 부족")
                    perm_error = True
                except Exception as e:
                    print(f"❌ 닉네임 변경 오류: {e}")

            embed = discord.Embed(
                title="✅ 부계정 등록 완료",
                description=f"본캐: `{main_nick}`\n부계정 {sub_num}: `{sub_nick}` 이 등록되었습니다.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ 등록 실패",
                description="이미 같은 부계정이 등록되어 있거나 오류가 발생했습니다.",
                color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None, delete_after=5)
        if perm_error:
            try:
                # 이미 respond() 한 경우 → followup
                await interaction.followup.send(
                    "⚠️ 닉네임 변경 권한이 부족하여 닉네임을 변경하지 못했습니다.",
                    ephemeral=True
                )
            except discord.InteractionResponded:
                # 아직 respond() 하지 않았다면
                await interaction.response.send_message(
                    "⚠️ 닉네임 변경 권한이 부족하여 닉네임을 변경하지 못했습니다.",
                    ephemeral=True
                )
            
    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content="⛔ 부계정 등록이 취소되었습니다.",delete_after=5,view=None,embed=None,)

