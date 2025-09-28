import discord
from utils.function import unblock_user  # ✅ DB 업데이트 함수는 utils에 구현

class BlockTicketView(discord.ui.View):
    def __init__(self, blocked_entries: list[dict]):
        """
        blocked_entries: get_user_blocked() 결과 리스트
        """
        super().__init__(timeout=None)
        self.blocked_entries = blocked_entries

    @discord.ui.button(label="🚫 차단 해제", style=discord.ButtonStyle.danger, custom_id="block_unblock")
    async def unblock_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ✅ 관리자 권한 확인
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ 관리자만 이 버튼을 사용할 수 있습니다.", ephemeral=True)
            return

        # ✅ 차단 해제 처리
        count = unblock_user(self.blocked_entries, interaction.user.id)

        await interaction.response.edit_message(
            content=f"✅ {count}개의 차단 항목이 해제되었습니다.",
            view=None
        )