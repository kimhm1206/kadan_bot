import discord
from utils.function import set_setting, get_setting_value
from config.admin_embed import build_admin_embed
from config.admin_view import AdminConfigMainView
from config.edit_modal import ChannelSettingEditModal  # 기존 모달
from config.send_default_message import send_default_message

# 숫자 입력용 모달
class NumberSettingEditModal(discord.ui.Modal):
    def __init__(self, guild_id: int, user_id: int, setting_type: str, label: str, old_value: str = None):
        super().__init__(title=f"{label} 값 설정")
        self.guild_id = guild_id
        self.user_id = user_id
        self.setting_type = setting_type
        self.label = label
        self.old_value = old_value

        self.input = discord.ui.InputText(
            label=f"{label} (숫자 입력)",
            placeholder="예: 1680",
            value=old_value or "",
            style=discord.InputTextStyle.short  # ✅ 한 줄 입력으로 고정
        )
        
        self.add_item(self.input)

    async def callback(self, interaction: discord.Interaction):
        try:
            new_value = str(int(self.input.value.strip()))  # 숫자만 허용
        except ValueError:
            await interaction.response.send_message("❌ 숫자만 입력 가능합니다.", ephemeral=True)
            return

        old_value = get_setting_value(self.guild_id, self.setting_type)

        if old_value is None:
            # 신규 저장
            set_setting(self.guild_id, self.setting_type, new_value, self.user_id, reason="create")

            embed = build_admin_embed(self.guild_id)
            await interaction.response.edit_message(
                embed=embed,
                view=AdminConfigMainView(interaction.client, self.guild_id)
            )
            await interaction.followup.send(
                f"✅ `{self.label}` 설정이 `{new_value}`(으)로 등록되었습니다.",
                ephemeral=True
            )

        else:
            # 기존 값 있음 → 모달에서 모달은 불가능하므로 그냥 바로 저장 or 에러 메시지 처리
            set_setting(self.guild_id, self.setting_type, new_value, self.user_id, reason=f"edit: {self.input.value}")

            embed = build_admin_embed(self.guild_id)
            await interaction.response.edit_message(
                embed=embed,
                view=AdminConfigMainView(interaction.client, self.guild_id)
            )
            await interaction.followup.send(
                f"✏️ `{self.label}` 설정이 `{new_value}`(으)로 변경되었습니다.",
                ephemeral=True
            )


class AdminConfigValueView(discord.ui.View):
    def __init__(self, bot: discord.Bot, guild_id: int, setting_type: str, target_type: str, label: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.setting_type = setting_type   # ex: "verify_channel"
        self.target_type = target_type     # "channel" | "role" | "number"
        self.label = label

        guild = bot.get_guild(guild_id)

        if target_type == "channel":
            options = [
                discord.SelectOption(label=ch.name, value=str(ch.id))
                for ch in guild.text_channels
            ]
        elif target_type == "category":
            options = [
                discord.SelectOption(label=cat.name, value=str(cat.id))
                for cat in guild.categories
            ]
        elif target_type == "role":
            options = [
                discord.SelectOption(label=r.name, value=str(r.id))
                for r in guild.roles if not r.is_default()
            ]
        else:
            options = []

        if options:
            self.select = discord.ui.Select(
                placeholder=f"{label} 선택",
                options=options[:25]
            )

            async def on_select(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)

            self.select.callback = on_select
            self.add_item(self.select)

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, button, interaction: discord.Interaction):
        if self.target_type == "number":
            # 숫자 입력 모달 실행
            old_value = get_setting_value(self.guild_id, self.setting_type)
            modal = NumberSettingEditModal(
                guild_id=self.guild_id,
                user_id=interaction.user.id,
                setting_type=self.setting_type,
                label=self.label,
                old_value=old_value
            )
            await interaction.response.send_modal(modal)
            return

        if not self.select.values:
            await interaction.response.send_message("❌ 값을 먼저 선택하세요.", ephemeral=True)
            return

        new_value = self.select.values[0]
        old_value = get_setting_value(self.guild_id, self.setting_type)

        if self.target_type == "channel":
            target = interaction.guild.get_channel(int(new_value))
        elif self.target_type == "category":
            target = interaction.guild.get_channel(int(new_value))  # 카테고리도 get_channel 으로 가져옴
        else:  # role
            target = interaction.guild.get_role(int(new_value))

        if old_value is None:
            set_setting(self.guild_id, self.setting_type, str(target.id), interaction.user.id, reason="create")

            # ✅ 기본 메시지 전송은 인증/티켓 채널만
            if self.setting_type in ["verify_channel", "ticket_channel"]:
                new_channel = interaction.guild.get_channel(target.id)
                await send_default_message(
                    self.bot,
                    guild_id=self.guild_id,
                    old_channel=None,
                    new_channel=new_channel,
                    type=self.setting_type
                )

            # ✅ 관리자 패널 갱신
            embed = build_admin_embed(self.guild_id)
            await interaction.response.edit_message(
                embed=embed,
                view=AdminConfigMainView(self.bot, self.guild_id)
            )
            await interaction.followup.send(
                f"✅ `{self.label}` 설정이 {self._format_value(str(target.id))}(으)로 등록되었습니다.",
                ephemeral=True
            )
        else:
            modal = ChannelSettingEditModal(
                guild_id=self.guild_id,
                target=target,
                user_id=interaction.user.id,
                setting_type=self.setting_type
            )
            await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, button, interaction: discord.Interaction):
        embed = build_admin_embed(self.guild_id)
        await interaction.response.edit_message(
            content="❌ 설정이 취소되었습니다.",
            embed=embed,
            view=AdminConfigMainView(self.bot, self.guild_id)
        )

    def _format_value(self, value: str) -> str:
        if self.target_type == "channel":
            return f"<#{value}>"
        elif self.target_type == "role":
            return f"<@&{value}>"
        return value
