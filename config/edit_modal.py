import discord
from utils.function import set_setting, get_setting_value
from config.admin_embed import build_admin_embed
from config.admin_view import AdminConfigMainView
from config.send_default_message import send_default_message


class ChannelSettingEditModal(discord.ui.Modal):
    def __init__(self, guild_id: int, target, user_id: int, setting_type: str):
        """
        :param target: discord.Role | discord.TextChannel | int(str) (숫자 설정도 지원)
        """
        super().__init__(title="설정 변경 사유 입력")
        self.setting_type = setting_type
        self.guild_id = guild_id
        self.target = target
        self.user_id = user_id

        self.reason_input = discord.ui.InputText(
            label="변경 사유",
            placeholder="예: 구조 변경 때문에 수정",
            required=True,
            style=discord.InputTextStyle.long
        )
        self.add_item(self.reason_input)

    async def callback(self, interaction: discord.Interaction):
        # ✅ DB 업데이트 전에 기존 값 가져오기
        old_channel_id = None
        if self.setting_type.endswith("_channel"):
            old_channel_id = get_setting_value(self.guild_id, self.setting_type)

        # 새 값 정리 (채널/역할은 id, 숫자는 그대로)
        if hasattr(self.target, "id"):
            new_value = str(self.target.id)
        else:
            new_value = str(self.target)  # 숫자나 기타 값

        reason = f"edit: {self.reason_input.value}"
        set_setting(
            self.guild_id,
            self.setting_type,
            new_value,
            self.user_id,
            reason
        )

        if self.setting_type == "admin_channel":
            # ✅ 관리자 채널 변경 → 기존 관리자 패널 삭제 + 새 채널 전송
            old_channel = None
            if old_channel_id and old_channel_id.isdigit():
                try:
                    old_channel = interaction.guild.get_channel(int(old_channel_id))
                except Exception:
                    old_channel = None

            if old_channel:
                try:
                    async for msg in old_channel.history(limit=50):
                        if msg.author == interaction.client.user:
                            await msg.delete()
                except Exception as e:
                    print(f"⚠️ 기존 관리자 패널 삭제 실패 (채널 없음/삭제됨): {e}")

            embed = build_admin_embed(self.guild_id)
            view = AdminConfigMainView(interaction.client, self.guild_id)
            if hasattr(self.target, "id"):  # 채널 객체만 전송 가능
                new_channel = interaction.guild.get_channel(self.target.id)
                if new_channel:
                    await new_channel.send(embed=embed, view=view)

        else:
            # ✅ 인증/티켓 등 다른 채널 설정 변경
            if self.setting_type in ["verify_channel", "ticket_channel"]:
                old_channel = None
                if old_channel_id and old_channel_id.isdigit():
                    try:
                        old_channel = interaction.guild.get_channel(int(old_channel_id))
                    except Exception:
                        old_channel = None

                new_channel = None
                if hasattr(self.target, "id"):
                    new_channel = interaction.guild.get_channel(self.target.id)

                await send_default_message(
                    interaction.client,
                    guild_id=self.guild_id,
                    old_channel=old_channel,
                    new_channel=new_channel,
                    type=self.setting_type
                )

            # ✅ 관리자 패널 메시지는 무조건 갱신
            embed = build_admin_embed(self.guild_id)
            view = AdminConfigMainView(interaction.client, self.guild_id)
            try:
                await interaction.message.edit(embed=embed, view=view)
            except Exception as e:
                print(f"⚠️ 관리자 패널 갱신 실패: {e}")

        # ✅ 에페메랄 피드백
        await interaction.response.send_message(
            f"✏️ `{self.setting_type}` 설정이 {self._mention_target()}(으)로 변경되었습니다.\n"
            f"사유: `{self.reason_input.value}`",
            ephemeral=True
        )

    def _mention_target(self):
        if isinstance(self.target, discord.Role):
            return f"<@&{self.target.id}>"
        elif isinstance(self.target, discord.TextChannel):
            return f"<#{self.target.id}>"
        return str(self.target)  # 숫자나 기타 값
