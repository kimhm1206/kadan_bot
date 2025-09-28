import discord
from ticket.ticket_create import create_ticket

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 패널은 영구 유지

    # 🟢 문의 버튼
    @discord.ui.button(label="문의", style=discord.ButtonStyle.success, emoji="📩")
    async def inquiry_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await create_ticket(interaction.user, "문의")
        await interaction.response.send_message("✅ 문의 티켓이 생성되었습니다.", ephemeral=True, delete_after=10)

    # 🔴 신고 버튼
    @discord.ui.button(label="신고", style=discord.ButtonStyle.danger, emoji="🚨")
    async def report_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await create_ticket(interaction.user, "신고")
        await interaction.response.send_message("🚨 신고 티켓이 생성되었습니다.", ephemeral=True, delete_after=10)


    # 🔵 인증 버튼
    @discord.ui.button(label="인증", style=discord.ButtonStyle.primary, emoji="🔑")
    async def auth_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await create_ticket(interaction.user, "인증")
        await interaction.response.send_message("🔑 인증 티켓이 생성되었습니다.", ephemeral=True, delete_after=10)

