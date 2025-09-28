import discord
from config.admin_embed import build_admin_embed
from config.admin_view import AdminConfigMainView

class AdminConfigSelectView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

        self.select = discord.ui.Select(
            placeholder="변경할 항목을 선택하세요",
            options=[
                discord.SelectOption(label="인증 채널", value="verify_channel"),
                discord.SelectOption(label="인증 로그 채널", value="verify_log_channel"),
                discord.SelectOption(label="본계정 인증 역할", value="main_auth_role"),
                discord.SelectOption(label="부계정 인증 역할", value="sub_auth_role"),
                discord.SelectOption(label="문의 채널", value="ticket_channel"),
                discord.SelectOption(label="문의 로그 채널", value="ticket_log_channel"),
                discord.SelectOption(label="문의 채널 카테고리", value="ticket_category"),       # ✅ 추가
                discord.SelectOption(label="차단 로그 채널", value="blocked_channel"),
                discord.SelectOption(label="본계정 인증 제한 레벨", value="main_auth_min_level"), # ✅ 추가
            ]
        )

        # 🔹 더미 콜백 추가 → "interaction failed" 방지
        async def on_select(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

        self.select.callback = on_select
        self.add_item(self.select)

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, button, interaction: discord.Interaction):
        """선택된 항목에 따라 값 선택 View로 이동"""
        if not self.select.values:
            await interaction.response.send_message("❌ 항목을 먼저 선택하세요.", ephemeral=True)
            return

        selected = self.select.values[0]
        label = dict(
            verify_channel="인증 채널",
            verify_log_channel="인증 로그 채널",
            main_auth_role="본계정 인증 역할",
            sub_auth_role="부계정 인증 역할",
            ticket_channel="문의 채널",
            ticket_log_channel="문의 로그 채널",
            ticket_category="문의 채널 카테고리",       
            blocked_channel="차단 로그 채널",   
            main_auth_min_level="본계정 인증 제한 레벨",   
        )[selected]

                # ✅ target_type 구분
        if selected in ["main_auth_role", "sub_auth_role"]:
            target_type = "role"
        elif selected == "main_auth_min_level":
            target_type = "number"  # 숫자 입력 모달
        elif selected == "ticket_category":
            target_type = "category"  # ✅ 카테고리 전용
        else:
            target_type = "channel"   # 일반 텍스트채널/로그채널

        from config.admin_value_view import AdminConfigValueView  # 순환 import 방지
        embed = build_admin_embed(self.guild_id, extra_text=f"⚙️ `{label}` 값을 선택하세요.")
        await interaction.response.edit_message(
            embed=embed,
            view=AdminConfigValueView(self.bot, self.guild_id, selected, target_type, label)
        )

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, button, interaction: discord.Interaction):
        """메인 패널로 복귀"""
        embed = build_admin_embed(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=AdminConfigMainView(self.bot, self.guild_id))
