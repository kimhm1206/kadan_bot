import discord
from utils.function import approve_guild, reject_guild
from config.admin_embed import build_admin_commands_embed, build_admin_embed

class ServerApprovalView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guild_id: int, requester: int, name: str, server: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.requester = requester
        self.name = name
        self.server = server   # ✅ 등록된 로아 서버명도 같이 들고 있음

    async def notify_requester(self, approved: bool):
        user = await self.bot.fetch_user(self.requester)
        if not user:
            return

        try:
            if approved:
                await user.send(f"✅ 당신의 서버(`{self.name}` / **{self.server}**) 등록 요청이 승인되었습니다!")
            else:
                await user.send(f"❌ 당신의 서버(`{self.name}` / **{self.server}**) 등록 요청이 거부되었습니다.")
        except discord.Forbidden:
            pass  # DM 차단이면 무시

    @discord.ui.button(label="허용", style=discord.ButtonStyle.green)
    async def approve_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        approve_guild(self.guild_id, interaction.user.id)
        # ✅ DB → 캐시 초기화 (settings + server 값까지)
        from utils.function import get_all_settings
        from utils.cache import settings_cache
        settings_cache.clear()
        settings_cache.update(get_all_settings())
        
        await self.notify_requester(True)
        await interaction.response.edit_message(content="✅ 서버 등록이 승인되었습니다.", view=None)

    @discord.ui.button(label="거부", style=discord.ButtonStyle.red)
    async def reject_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        reject_guild(self.guild_id, interaction.user.id)
        await self.notify_requester(False)
        await interaction.response.edit_message(content="❌ 서버 등록이 거부되었습니다.", view=None)
        
        
class AdminConfigMainView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.button(label="⚙️ 설정하기", style=discord.ButtonStyle.primary)
    async def open_settings(self, button, interaction: discord.Interaction):
        """설정 버튼 눌렀을 때 → 항목 선택 뷰로 교체"""
        from config.admin_select_view import AdminConfigSelectView  # 순환 import 방지

        embed = build_admin_embed(
            self.guild_id,
            extra_text="아래 셀렉트바에서 수정할 항목을 골라주세요."
        )
        await interaction.response.edit_message(embed=embed, view=AdminConfigSelectView(self.bot, self.guild_id))

    @discord.ui.button(label="📖 명령어 설명", style=discord.ButtonStyle.secondary)
    async def command_help(self, button, interaction: discord.Interaction):
        embed = build_admin_commands_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
