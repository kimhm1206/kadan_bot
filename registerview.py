import discord
from modal import SubAccountModal,ConfirmAuthView
import aiohttp
import re
import random

class RequestConfirmationView(discord.ui.View):
    def __init__(self, requester: discord.User, target_user: discord.User, sub_nick: str, profile_url: str):
        super().__init__(timeout=180)
        self.requester = requester
        self.target_user = target_user
        self.sub_nick = sub_nick
        self.profile_url = profile_url

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.success)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("❌ 당신은 이 요청을 사용할 수 없습니다.", ephemeral=True)
            return

        # 다시 전투정보실 재요청
        async with aiohttp.ClientSession() as session:
            async with session.get(self.profile_url) as resp:
                if resp.status != 200:
                    await interaction.response.send_message("❌ 전투정보실 요청 실패", ephemeral=True)
                    return
                html = await resp.text()

        # 대표 캐릭터 재확인
        rep_match = re.search(r'<span class="profile-character-info__name" title="(.*?)">', html)
        if not rep_match:
            await interaction.response.send_message("❌ 대표 캐릭터를 찾을 수 없습니다.", ephemeral=True)
            return
        
        # 최신화 확인
        if "최신화된 캐릭터 정보가 존재하지 않습니다." in html:
            await interaction.response.send_message(
                "❌ 최신화된 캐릭터 정보가 존재하지 않습니다.\n게임에 접속하여 캐릭터 정보를 최신화 시켜주세요.",
                ephemeral=True
            )
            return
        
        rep_char = rep_match.group(1)
        char_list = re.findall(r'/Profile/Character/(.*?)"', html)
        char_list = list(set(name.strip("'") for name in char_list))

        if self.sub_nick not in char_list:
            await interaction.response.send_message(f"❌ `{self.sub_nick}` 닉네임은 전투정보실에 존재하지 않습니다.", ephemeral=True)
            return

        candidate = [c for c in char_list if c != self.sub_nick]
        if not candidate:
            await interaction.response.send_message("❌ 대표 캐릭터를 바꿀 수 있는 다른 캐릭터가 없습니다.", ephemeral=True)
            return

        selected = random.choice(candidate)

        # ConfirmAuthView로 이동
        embed = discord.Embed(
            title="대표 캐릭터 인증",
            description=(
                f"현재 대표 캐릭터는 `{rep_char}` 입니다.\n"
                f"`{selected}` 캐릭터로 대표 캐릭터를 변경한 뒤 아래 확인 버튼을 눌러주세요."
            ),
            color=discord.Color.blurple()
        )
        await interaction.response.edit_message(
            embed=embed,
            attachments=[],
            view=ConfirmAuthView(
                user=self.requester,
                sub_nick=self.sub_nick,
                profile_url=self.profile_url,
                expected_main=selected,
                is_conditional=True,
                target_user=self.target_user
            )
        )

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("❌ 당신은 이 요청을 사용할 수 없습니다.", ephemeral=True)
            return

        await interaction.response.edit_message(
            content="⛔ 부계정 등록 요청이 취소되었습니다.",
            embed=None,
            view=None,
            delete_after=5
        )

class RegisterStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="✅ 등록 시작", style=discord.ButtonStyle.success)
    async def start_registration(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 기본 닉네임을 전달하여 모달에 미리 채워넣을 수 있음
        await interaction.response.send_modal(SubAccountModal(interaction))

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger)
    async def cancel_registration(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="⛔ 부계정 등록 요청이 취소되었습니다.",
            embed=None,
            attachments=[],
            view=None,
            delete_after=5
        )