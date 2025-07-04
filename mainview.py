import discord
from authview import handle_auth  # 버튼 클릭 시 인증 처리
from delete import SubAccountCancelView

class VerificationView(discord.ui.View):
    
    @discord.ui.button(label="부계정 인증 시작", style=discord.ButtonStyle.primary)
    async def start_verification(self, button: discord.ui.Button, interaction: discord.Interaction):
        await handle_auth(interaction)
        
    @discord.ui.button(label="부계정 인증 취소", style=discord.ButtonStyle.danger)
    async def cancel_subaccount(self, button: discord.ui.Button, interaction: discord.Interaction):
        from function import get_user_sub_accounts

        subs = get_user_sub_accounts(interaction.user.id)
        if not subs:
            await interaction.response.send_message("❌ 등록된 부계정이 없습니다.", ephemeral=True,delete_after=5)
            return

        await interaction.response.send_message(
            "🔻 삭제할 부계정을 선택해주세요.",
            view=SubAccountCancelView(user=interaction.user, sub_list=subs),
            ephemeral=True
        )