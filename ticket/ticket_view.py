import asyncio

import discord

from ticket.ticket_create import create_ticket, ICON_MAP


class TicketConfirmView(discord.ui.View):
    def __init__(self, member: discord.Member, ticket_type: str):
        super().__init__(timeout=60)
        self.member = member
        self.ticket_type = ticket_type

    async def _ensure_requester(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ 요청자만 사용할 수 있습니다.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="생성", style=discord.ButtonStyle.primary, emoji="✅")
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not await self._ensure_requester(interaction):
            return

        await interaction.response.defer()
        channel = await create_ticket(self.member, self.ticket_type)

        icon = ICON_MAP.get(self.ticket_type, "📌")
        embed = discord.Embed(
            title=f"{icon} {self.ticket_type} 티켓이 생성되었습니다.",
            description=f"{channel.mention} 채널에서 문의를 이어가 주세요.",
            color=discord.Color.green(),
        )

        await interaction.edit_original_response(embed=embed, view=None)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not await self._ensure_requester(interaction):
            return

        embed = discord.Embed(
            title="❌ 티켓 생성이 취소되었습니다.",
            description="필요 시 다시 패널에서 버튼을 눌러주세요.",
            color=discord.Color.red(),
        )

        await interaction.response.edit_message(embed=embed, view=None)

        async def _cleanup():
            await asyncio.sleep(10)
            try:
                await interaction.delete_original_response()
            except (discord.NotFound, discord.HTTPException):
                pass

        asyncio.create_task(_cleanup())

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 패널은 영구 유지

    # 🟢 문의 버튼
    @discord.ui.button(label="문의", style=discord.ButtonStyle.success, emoji="📩")
    async def inquiry_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        icon = ICON_MAP.get("문의", "📩")
        embed = discord.Embed(
            title=f"{icon} 문의 티켓 생성 확인",
            description="정말 문의 티켓을 생성하시겠습니까?",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketConfirmView(interaction.user, "문의"), ephemeral=True)
        
    # 🔵 인증 버튼
    @discord.ui.button(label="인증", style=discord.ButtonStyle.primary, emoji="🔑")
    async def auth_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        icon = ICON_MAP.get("인증", "🔑")
        embed = discord.Embed(
            title=f"{icon} 인증 티켓 생성 확인",
            description="정말 인증 티켓을 생성하시겠습니까?",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketConfirmView(interaction.user, "인증"), ephemeral=True)

    # 🔴 신고 버튼
    @discord.ui.button(label="신고", style=discord.ButtonStyle.danger, emoji="🚨")
    async def report_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        icon = ICON_MAP.get("신고", "🚨")
        embed = discord.Embed(
            title=f"{icon} 신고 티켓 생성 확인",
            description="정말 신고 티켓을 생성하시겠습니까?",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketConfirmView(interaction.user, "신고"), ephemeral=True)




