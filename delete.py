import discord

class SubAccountCancelView(discord.ui.View):
    def __init__(self, user: discord.User, sub_list: list[str]):
        super().__init__(timeout=120)
        self.user = user
        self.sub_list = sub_list
        self.selected = sub_list[0]  # 기본값

        self.add_item(self.SubSelect(self))

    class SubSelect(discord.ui.Select):
        def __init__(self, parent_view):
            self.parent = parent_view
            options = [discord.SelectOption(label=sub, value=sub) for sub in parent_view.sub_list]
            super().__init__(placeholder="삭제할 부계정을 선택하세요", options=options, row=0)

        async def callback(self, interaction: discord.Interaction):
            self.parent.selected = self.values[0]  # 선택만 저장
            await interaction.response.defer()

    @discord.ui.button(label="✅ 삭제", style=discord.ButtonStyle.danger, row=1)
    async def delete_sub(self, button: discord.ui.Button, interaction: discord.Interaction):
        from function import delete_sub_account, get_user_sub_accounts,send_log_embed
        perm_error = False
        result = delete_sub_account(self.user.id, self.selected)
        if result:
            # ✅ 삭제 성공 후 닉네임 정리
            guild = interaction.guild
            member = guild.get_member(self.user.id)
            remaining = get_user_sub_accounts(self.user.id)

            if member and not remaining:
                current_nick = member.nick or member.global_name
                if " / 부계정O" in current_nick:
                    
                    try:
                        new_nick = current_nick.replace(" / 부계정O", "").strip()
                        await member.edit(nick=new_nick, reason="부계정 전부 삭제로 인한 닉네임 복구")
                        await send_log_embed(
                                bot=interaction.client,
                                user=member,
                                main_nick=self.selected,
                                title="🗑️ 부계정 삭제 완료"
                            )
                    except discord.Forbidden:
                        print("❌ 닉네임 제거 권한 부족")
                        perm_error = True
                    except Exception as e:
                        print(f"❌ 닉네임 복구 오류: {e}")
                        
            await interaction.response.edit_message(
                content=f"✅ `{self.selected}` 부계정이 성공적으로 삭제되었습니다.",
                embed=None,
                view=None,
                delete_after=5
            )
            if perm_error:
                try:
                    # 이미 respond() 한 경우 → followup
                    await interaction.followup.send(
                        "⚠️ 닉네임 변경 권한이 부족하여 닉네임을 변경하지 못했습니다.",
                        ephemeral=True
                    )
                except discord.InteractionResponded:
                    # 아직 respond() 하지 않았다면
                    await interaction.response.send_message(
                        "⚠️ 닉네임 변경 권한이 부족하여 닉네임을 변경하지 못했습니다.",
                        ephemeral=True
                    )
            
        else:
            await interaction.response.edit_message(
                content=f"❌ `{self.selected}` 부계정 삭제 중 오류가 발생했습니다.",
                embed=None,
                view=None,
                delete_after=5
            )

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="⛔ 인증 취소가 취소되었습니다.",
            embed=None,
            view=None,
            delete_after=5
        )