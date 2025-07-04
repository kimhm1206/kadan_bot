import discord
from function import insert_sub_account,update_foreign_request_status, get_server_main_nick, get_user_sub_count, get_max_subs, send_log_embed

OPERATING_GUILD_ID = 743375510003777618  # 상단 import 영역에 위치

class ApprovalView(discord.ui.View):
    def __init__(self, requester_id: int, sub_nick: str):
        super().__init__(timeout=600)
        self.requester_id = requester_id
        self.sub_nick = sub_nick

    @discord.ui.button(label="✅ 허용", style=discord.ButtonStyle.success)
    async def approve(self, button: discord.ui.Button, interaction: discord.Interaction):
        
        perm_bool = False
        main_nick = get_server_main_nick(interaction.client, self.requester_id)
        sub_num = get_user_sub_count(self.requester_id) + 1
        max_subs = get_max_subs()
        requester = await interaction.client.fetch_user(self.requester_id)
        if sub_num > max_subs:
            await interaction.response.edit_message(
                    embed=discord.Embed(
                    title="등록 불가능",
                    description="⚠️ 요청자가 이미 최대 부계정 수를 초과했습니다.",
                    color=discord.Color.red()
                ),
                view=None
            )
            update_foreign_request_status(self.requester_id, interaction.user.id, self.sub_nick,'승인 불가')
            try:
                await requester.send(
                    embed=discord.Embed(
                        title="❌ 부계정 등록 불가능",
                        description=(
                            f"당신이 요청한 `{self.sub_nick}` 부계정 등록이\n"
                            f"계정의 문제로 (최대 등록 가능 수 초과 등)등록이 되지 않았습니다.\n관리자에게 문의 바랍니다."
                        ),
                        color=discord.Color.red()
                    ))
            except:
                return
            return

        success = insert_sub_account(self.requester_id, main_nick, self.sub_nick, sub_num)

        if success:
            await interaction.response.edit_message(
                    embed=discord.Embed(
                    title="✅ 요청을 승인했습니다.",
                    description="부계정이 등록되었습니다.",
                    color=discord.Color.red()
                ),
                view=None
            )
            # ✅ 요청자에게도 DM 전송
            try:
                update_foreign_request_status(self.requester_id, interaction.user.id, self.sub_nick,'승인')
                guild = interaction.client.get_guild(OPERATING_GUILD_ID)
                member = guild.get_member(self.requester_id) if guild else None

                if member:
                    current_nick = member.nick or member.global_name
                    if "/ 부계정O" not in current_nick:
                        new_nick = f"{current_nick} / 부계정O"
                        try:
                            await send_log_embed(
                                bot=interaction.client,
                                user=member,
                                main_nick=self.sub_nick
                            )
                            await member.edit(nick=new_nick, reason="조건부 부계정 인증 완료 후 자동 닉네임 갱신")
                        except discord.Forbidden:
                            print("❌ 닉네임 변경 권한 부족")
                            perm_bool = True
                        except Exception as e:
                            print(f"❌ 닉네임 변경 오류: {e}")
                if perm_bool:       
                    await requester.send(
                        embed=discord.Embed(
                            title="✅ 부계정 등록 승인 완료",
                            description=(
                                f"당신이 요청한 `{self.sub_nick}` 부계정 등록이\n"
                                f"`{interaction.user.display_name}`님의 승인으로 완료되었습니다만\n봇 권한 부족으로 닉네임 변경은 실패했습니다."
                            ),
                            color=discord.Color.green()
                        )
                    )
                else:
                    await requester.send(
                        embed=discord.Embed(
                            title="✅ 부계정 등록 승인 완료",
                            description=(
                                f"당신이 요청한 `{self.sub_nick}` 부계정 등록이\n"
                                f"`{interaction.user.display_name}`님의 승인으로 완료되었습니다!"
                            ),
                            color=discord.Color.green()
                        )
                    )
            except Exception as e:
                print(f"[❌ 요청자 DM 실패] {type(e).__name__}: {e}")

        else:
            update_foreign_request_status(self.requester_id, interaction.user.id, self.sub_nick,'승인 불가')
            await interaction.response.edit_message(
                    embed=discord.Embed(
                    title="❌ 등록 실패",
                    description="이미 등록된 부계정일 수 있습니다.",
                    color=discord.Color.red()
                ),
                view=None
            )
            try:
                await requester.send(
                    embed=discord.Embed(
                        title="❌ 부계정 등록 불가능",
                        description=(
                            f"당신이 요청한 `{self.sub_nick}` 부계정 등록이\n"
                            f"계정의 문제로 (최대 등록 가능 수 초과 등)등록이 되지 않았습니다.\n관리자에게 문의 바랍니다."
                        ),
                        color=discord.Color.red()
                    ))
            except:
                return

        

    @discord.ui.button(label="❌ 거절", style=discord.ButtonStyle.danger)
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        update_foreign_request_status(self.requester_id, interaction.user.id, self.sub_nick,'거절')

        await interaction.response.edit_message(
                    embed=discord.Embed(
                    title="🚫 요청을 거절했습니다.",
                    description="상대는 이 계정을 부계정으로 등록할 수 없습니다.",
                    color=discord.Color.red()
                ),
                view=None
            )

        # ✅ 요청자에게 거절 DM 전송
        try:
            requester = await interaction.client.fetch_user(self.requester_id)
            await requester.send(
                embed=discord.Embed(
                    title="❌ 부계정 등록 요청 거절됨",
                    description=(
                        f"당신이 요청한 `{self.sub_nick}` 부계정 등록이\n"
                        f"`{interaction.user.display_name}`님의 거절로 처리되지 않았습니다."
                    ),
                    color=discord.Color.red()
                )
            )
        except Exception as e:
            print(f"[❌ 요청자 DM 실패 - 거절] {type(e).__name__}: {e}")
