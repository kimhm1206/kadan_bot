import discord

from utils.function import (
    get_main_account_nickname,
    get_setting_cached,
    get_timeout_state,
    get_user_timeout_summary,
    mark_timeout_released,
)

REASON_CHOICES = [
    "판매 채널 구매글 작성",
    "거래 채널 구매,판매시 가격 미기재",
    "미인증 계정 거래",
]


def build_timeout_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⏳ 타임아웃 안내",
        description=(
            "아래 버튼으로 본인 제재 상태를 확인하거나 해제를 시도할 수 있습니다.\n"
            "해제 가능 시간이 지나면 `타임아웃 해제하기` 버튼이 동작합니다."
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="버튼 안내",
        value=(
            "- `타임아웃 해제하기`: 제재 기간 만료 시 본계정 인증 역할을 다시 받습니다.\n"
            "- `내 제재 현황 확인하기`: 사유별 누적 제재 횟수를 확인합니다."
        ),
        inline=False,
    )
    return embed


class TimeoutPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="⏳ 타임아웃 해제하기", style=discord.ButtonStyle.success, custom_id="timeout_release")
    async def release_timeout(self, button: discord.ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("⚠️ 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return

        state, data = get_timeout_state(guild.id, interaction.user.id)
        if state == "none":
            await interaction.response.send_message(
                "✨ 현재 타임아웃 중이 아닙니다. 제재가 없거나 이미 해제되었습니다.",
                ephemeral=True,
            )
            return

        end_at = data["timeout_end_at"]
        end_text = end_at.strftime("%Y-%m-%d %H:%M(KST)")

        if state == "active":
            await interaction.response.send_message(
                f"🌸 아직 제재 해제 시간이 아니에요.\n해제 가능 시각: `{end_text}`\n조금만 더 기다렸다가 다시 눌러주세요!",
                ephemeral=True,
            )
            return

        role_id = get_setting_cached(guild.id, "main_auth_role")
        role = guild.get_role(int(role_id)) if role_id and role_id.isdigit() else None
        if isinstance(interaction.user, discord.Member):
            member = interaction.user
        else:
            member = guild.get_member(interaction.user.id)

        if role and member:
            try:
                await member.add_roles(role, reason="타임아웃 기간 만료 자동 해제")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "⚠️ 역할 부여 권한이 없어 해제를 완료하지 못했습니다. 관리자에게 문의해주세요.",
                    ephemeral=True,
                )
                return

        # 닉네임 복구 (본계정 인증 닉네임이 있을 때)
        if member:
            restored_nickname = get_main_account_nickname(guild.id, interaction.user.id)
            if restored_nickname:
                try:
                    await member.edit(nick=restored_nickname, reason="타임아웃 해제 닉네임 복구")
                except discord.Forbidden:
                    # 권한 부족 시 닉 복구만 실패하고 나머지는 진행
                    pass

        mark_timeout_released(guild.id, int(data["id"]))

        await interaction.response.send_message(
            "✅ 타임아웃 해제가 완료되었습니다. 본계정 인증 역할이 복구되었습니다.",
            ephemeral=True,
        )

    @discord.ui.button(label="📊 내 제재 현황 확인하기", style=discord.ButtonStyle.secondary, custom_id="timeout_status")
    async def check_timeout_status(self, button: discord.ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("⚠️ 서버에서만 사용할 수 있습니다.", ephemeral=True)
            return

        summary = get_user_timeout_summary(guild.id, interaction.user.id, REASON_CHOICES)
        lines = []
        for reason in REASON_CHOICES:
            count = summary.get(reason, 0)
            lines.append(f"- {reason}: **{count}회**")

        total = sum(summary.values()) if summary else 0
        if total == 0:
            message = "✨ 현재 기록된 제재 이력이 없습니다. 규칙 잘 지켜주셔서 감사합니다!"
        else:
            message = "\n".join(lines)

        await interaction.response.send_message(message, ephemeral=True)
