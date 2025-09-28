import discord
from utils.function import (
    get_main_account_nickname,
    get_sub_accounts,
    delete_main_account,
    delete_sub_account,
    get_setting_cached,
)
from auth.auth_logger import send_main_delete_log, send_sub_delete_log


class AccountManageView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.user_id = user_id
        self.selected_type: str | None = None  # "main" or "sub-{n}"

        # ✅ 옵션 준비
        options = []

        # 본계정 옵션
        main_nick = get_main_account_nickname(guild_id, user_id)
        if main_nick:
            options.append(discord.SelectOption(
                label=f"닉네임 - 본계정 ({main_nick})",
                value="main"
            ))

        # 부계정 옵션
        subs = get_sub_accounts(guild_id, user_id)  # [(sub_number, nickname)]
        for sub_number, nick in subs:
            options.append(discord.SelectOption(
                label=f"닉네임 - {sub_number}번 부계정 ({nick})",
                value=f"sub-{sub_number}"
            ))

        if not options:
            # 계정이 하나도 없으면 뷰 생성 불필요
            self.disabled = True
            return

        self.select = discord.ui.Select(
            placeholder="삭제할 계정을 선택하세요",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        self.selected_type = self.select.values[0]

        if self.selected_type == "main":
            main_nick = get_main_account_nickname(self.guild_id, self.user_id)
            desc = (
                "⚠️ **본 계정**을 삭제하시면 **부계정을 포함한 모든 인증 정보가 삭제됩니다.**\n\n"
                f"🗑️ 대상 계정: **본계정 ({main_nick or '닉네임 없음'})**"
            )
            color = 0xe74c3c
        else:
            sub_number = int(self.selected_type.split("-")[1])
            subs = get_sub_accounts(self.guild_id, self.user_id)
            nick = next((n for num, n in subs if num == sub_number), "닉네임 없음")

            desc = (
                "⚠️ 정말 이 **부계정 인증**을 취소하시겠습니까?\n\n"
                f"🗑️ 대상 계정: **{sub_number}번 부계정 ({nick})**"
            )
            color = 0xf1c40f

        embed = discord.Embed(
            title="🗑️ 인증 계정 삭제",
            description=desc,
            color=color
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="삭제", style=discord.ButtonStyle.danger, row=2)
    async def delete_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_type:
            await interaction.response.send_message("❌ 먼저 계정을 선택해주세요.", ephemeral=True)
            return

        member = interaction.guild.get_member(self.user_id)
        await interaction.response.defer(ephemeral=True)
        
        if self.selected_type == "main":
            # 🔹 본계정 + 부계정 삭제
            main_nick, sub_list = delete_main_account(self.guild_id, self.user_id)

            # 역할 제거
            for key in ("main_auth_role", "sub_auth_role"):
                role_id = get_setting_cached(self.guild_id, key)
                if role_id and member:
                    role = interaction.guild.get_role(int(role_id))
                    if role:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

            # 닉네임 초기화
            if member:
                try:
                    await member.edit(nick=None)
                except discord.Forbidden:
                    pass

            # 로그 전송
            await send_main_delete_log(interaction.client, self.guild_id, interaction.user, main_nick, sub_list)

            # ✅ 후속 응답 (임베드)
            embed = discord.Embed(
                title="🚫 본계정 삭제 완료",
                description=f"{interaction.user.mention} 님의 본계정 인증이 삭제되었습니다.",
                color=0xe74c3c
            )

            if main_nick:
                embed.add_field(name="본계정 닉네임", value=main_nick, inline=False)

            if sub_list:
                sub_text = "\n".join([f"{num}번 → {nick}" for num, nick in sub_list])
                embed.add_field(name="삭제된 부계정", value=sub_text, inline=False)

            await interaction.edit_original_response(embed=embed, view=None)
            self.stop()

        else:
            # 🔹 특정 부계정 삭제
            sub_number = int(self.selected_type.split("-")[1])
            deleted_nick = delete_sub_account(self.guild_id, self.user_id, sub_number)

            if not deleted_nick:
                await interaction.response.send_message("❌ 부계정 삭제 실패 (대상 없음).", ephemeral=True)
                return

            # 남은 부계정 확인
            subs = get_sub_accounts(self.guild_id, self.user_id)
            if not subs:  # 남은 게 없으면 → 역할/닉네임 정리
                role_id = get_setting_cached(self.guild_id, "sub_auth_role")
                if role_id and member:
                    role = interaction.guild.get_role(int(role_id))
                    if role:
                        try:
                            await member.remove_roles(role)
                        except discord.Forbidden:
                            pass

                # 닉네임에서 "| 부계정O" 제거
                if member and member.nick and " | 부계정O" in member.nick:
                    try:
                        await member.edit(nick=member.nick.replace(" | 부계정O", ""))
                    except discord.Forbidden:
                        pass

            # 로그 전송
            await send_sub_delete_log(interaction.client, self.guild_id, interaction.user, sub_number, deleted_nick)
            
            # ✅ 후속 응답 → 임베드 편집
            embed = discord.Embed(
                title="✅ 부계정 삭제 완료",
                description=f"{interaction.user.mention} 님의 {sub_number}번 부계정 인증이 삭제되었습니다.",
                color=0xf1c40f
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            self.stop()

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary, row=2)
    async def cancel_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚫 취소됨",
            description="인증 계정 삭제가 취소되었습니다.",
            color=0x95a5a6
        )
        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()
