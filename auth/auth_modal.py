import discord
from . import auth_flow


class AuthTradeModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="거래소 인증 - 마이페이지 입력", timeout=300)
        self.type = "main"  # 본계정 인증
        self.add_item(
            discord.ui.InputText(
                # value="https://profile.onstove.com/ko/84599446",
                label="마이페이지 링크",
                placeholder="https://profile.onstove.com/ko/84599446"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        link = self.children[0].value.strip()
        # link → memberNo 추출
        member_no = link.split("/")[-1] if link.startswith("https://profile.onstove.com/ko/") else None

        if not member_no or not member_no.isdigit():
            await interaction.response.send_message("❌ 올바른 마이페이지 링크를 입력해주세요.", ephemeral=True)
            return

        # 🔗 흐름 컨트롤러로 넘기기
        await auth_flow.start_auth(self.type, interaction, member_no)
        
        
# ✅ 부계정 인증 모달
class AuthSubModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="부계정 인증 - 마이페이지 입력", timeout=300)
        self.type = "sub"
        self.add_item(
            discord.ui.InputText(
                label="마이페이지 링크",
                placeholder="https://profile.onstove.com/ko/84599446"
            )
        )

    async def callback(self, interaction: discord.Interaction):
        link = self.children[0].value.strip()
        member_no = link.split("/")[-1] if link.startswith("https://profile.onstove.com/ko/") else None

        if not member_no or not member_no.isdigit():
            await interaction.response.send_message("❌ 올바른 마이페이지 링크를 입력해주세요.", ephemeral=True)
            return

        await auth_flow.start_auth(self.type, interaction, member_no)


