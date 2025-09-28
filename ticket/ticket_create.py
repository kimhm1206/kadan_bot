import discord
from datetime import datetime
from utils.function import get_setting_cached
import os
import aiohttp
from block.block_ticket import BlockTicketView  # ✅ 차단 해제 뷰
import zipfile

ICON_MAP = {
    "문의": "📩",
    "신고": "🚨",
    "인증": "🔑",
    "차단": "📛"
}


async def create_ticket(member: discord.Member, ticket_type: str, block_data: list = None):
    """
    티켓 채널 생성
    :param member: 티켓 개설자
    :param ticket_type: "문의" / "신고" / "인증" / "차단"
    :param block_data: 차단 데이터(details 리스트)
    """
    guild = member.guild
    guild_id = guild.id

    # ✅ 카테고리 & 로그 채널
    category_id = get_setting_cached(guild_id, "ticket_category")
    log_channel_id = get_setting_cached(guild_id, "ticket_log_channel")

    category = guild.get_channel(int(category_id)) if category_id else None
    log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None

    # ✅ 채널 이름
    now = datetime.now().strftime("%y%m%d%H%M")
    icon = ICON_MAP.get(ticket_type, "📌")
    channel_name = f"{icon}-{ticket_type}-{now}-{member.id}"

    # ✅ 권한
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    # ✅ 채널 생성
    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"{ticket_type} 티켓 자동 생성"
    )

    # 🔹 기본 환영 임베드
    embed = discord.Embed(
        title=f"{icon} {ticket_type} 티켓 생성됨",
        description=(
            f"{member.mention} 님, 관련 내용을 아래에 작성해 주세요.\n\n"
            "❌ 문의 사항 종료시 아래 버튼을 눌러 티켓을 종료할 수 있습니다."
        ),
        color=discord.Color.blue()
    )

    # 🔹 닫기/삭제 버튼 뷰
    class TicketControlView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="티켓 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            # 관리자 또는 개설자만 닫기 가능
            if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 이 티켓을 닫을 권한이 없습니다.", ephemeral=True)
                return

            await interaction.response.send_message("⏳ 티켓이 종료되었습니다.", ephemeral=True)
            await channel.edit(name=f"종료된-{channel.name}")
            await channel.set_permissions(member, view_channel=False)

            # 기존 메시지 edit → 삭제 버튼만 남김
            delete_view = TicketDeleteView(member, ticket_type, log_channel)
            await interaction.message.edit(
                embed=discord.Embed(
                    title=f"{icon} {ticket_type} 티켓 종료됨",
                    description="🔒 이 문의는 종료되었습니다.\n\n📌 메모를 남긴 뒤 아래 버튼으로 채널을 삭제할 수 있습니다. \n마지막 20개의 메시지만 로그에 남습니다.",
                    color=discord.Color.red()
                ),
                view=delete_view
            )

    class TicketDeleteView(discord.ui.View):
        def __init__(self, ticket_owner: discord.Member, t_type: str, log_ch: discord.TextChannel):
            super().__init__(timeout=None)
            self.owner = ticket_owner
            self.t_type = t_type
            self.log_ch = log_ch
            
        @discord.ui.button(label="채널 삭제", style=discord.ButtonStyle.danger, emoji="🗑️")
        async def delete_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 관리자만 채널을 삭제할 수 있습니다.", ephemeral=True)
                return

            # ✅ Defer (시간 오래 걸릴 수 있음)
            await interaction.response.defer(ephemeral=True)

            # 전체 메시지 수집
            all_messages = []
            image_attachments = []  # (url, safe_filename)
            async for msg in channel.history(limit=None, oldest_first=True):
                line = f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author.display_name}: {msg.content or ''}"
                if msg.attachments:
                    for att in msg.attachments:
                        ext = att.filename.lower().split(".")[-1]
                        safe_name = f"ticket_img-{channel.id}-{att.id}.{ext}"
                        if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                            image_attachments.append((att.url, safe_name))
                            line += f" (📎 이미지 첨부: {att.filename})"
                        else:
                            line += f" (📎 첨부파일: {att.filename} → {att.url})"
                all_messages.append(line)

            # 로그 embed 기본
            log_embed = discord.Embed(
                title=f"{ICON_MAP.get(self.t_type,'📌')} {self.t_type} 티켓 삭제됨",
                description=(
                    f"채널: {channel.name}\n"
                    f"개설자: {self.owner.mention}\n"
                    f"삭제자: {interaction.user.mention}"
                ),
                color=discord.Color.dark_gray()
            )

            # 최근 메시지 필드
            if len(all_messages) <= 20:
                log_embed.add_field(
                    name="📜 티켓 메시지 로그",
                    value="\n".join(all_messages) or "메시지 없음",
                    inline=False
                )
            else:
                log_embed.add_field(
                    name="📜 최근 20개 메시지",
                    value="\n".join(all_messages[-20:]),
                    inline=False
                )

            files = []      # 디스코드 전송용 File 객체
            tmp_files = []  # 로컬 임시 파일 경로

            # 이미지 다운로드
            async with aiohttp.ClientSession() as session:
                for url, safe_name in image_attachments:
                    try:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                with open(safe_name, "wb") as f:
                                    f.write(await resp.read())
                                tmp_files.append(safe_name)
                    except Exception as e:
                        print(f"⚠️ 이미지 다운로드 실패: {url} ({e})")

            # ========================
            # 분기 처리
            # ========================

            if len(image_attachments) == 0:
                # 이미지 없음
                if len(all_messages) > 20:
                    txt_name = f"ticket_log-{channel.id}.txt"
                    with open(txt_name, "w", encoding="utf-8") as f:
                        f.write("\n".join(all_messages))
                    zip_name = f"ticket_log-{channel.id}.zip"
                    with zipfile.ZipFile(zip_name, "w") as zipf:
                        zipf.write(txt_name)
                    files.append(discord.File(zip_name))
                    tmp_files.extend([txt_name, zip_name])

            elif len(image_attachments) == 1:
                # 이미지 1장
                last_img = tmp_files[-1]
                log_embed.set_image(url=f"attachment://{os.path.basename(last_img)}")
                files.append(discord.File(last_img))
                if len(all_messages) > 20:
                    txt_name = f"ticket_log-{channel.id}.txt"
                    with open(txt_name, "w", encoding="utf-8") as f:
                        f.write("\n".join(all_messages))
                    zip_name = f"ticket_log-{channel.id}.zip"
                    with zipfile.ZipFile(zip_name, "w") as zipf:
                        zipf.write(txt_name)
                    files.append(discord.File(zip_name))
                    tmp_files.extend([txt_name, zip_name])

            else:
                # 이미지 2장 이상 → 무조건 zip 생성
                zip_name = f"ticket_log-{channel.id}.zip"
                with zipfile.ZipFile(zip_name, "w") as zipf:
                    # 메시지가 20개 초과 → txt 포함
                    if len(all_messages) > 20:
                        txt_name = f"ticket_log-{channel.id}.txt"
                        with open(txt_name, "w", encoding="utf-8") as f:
                            f.write("\n".join(all_messages))
                        zipf.write(txt_name)
                        tmp_files.append(txt_name)
                    # 모든 이미지 파일 zip에 추가
                    for img in tmp_files:
                        zipf.write(img)
                files.append(discord.File(zip_name))
                tmp_files.append(zip_name)

                # ✅ 마지막 이미지는 embed에도 표시할 수 있도록 별도 File 추가
                last_img = tmp_files[-2] if len(all_messages) > 20 else tmp_files[-1]
                log_embed.set_image(url=f"attachment://{os.path.basename(last_img)}")
                files.append(discord.File(last_img))

            # 로그 채널 전송
            if self.log_ch:
                await self.log_ch.send(embed=log_embed, files=files)

            # 로컬 파일 삭제
            for f in tmp_files:
                try:
                    os.remove(f)
                except Exception as e:
                    print(f"⚠️ 임시 파일 삭제 실패: {e}")

            # 최종 피드백
            await interaction.followup.send("🗑️ 티켓 채널이 삭제됩니다.", ephemeral=True)
            await channel.delete(reason="티켓 삭제")


    # ✅ 기본 임베드 + 컨트롤 뷰 전송
    await channel.send(content=member.mention, embed=embed, view=TicketControlView())

    # ✅ 차단 타입일 경우 추가 임베드/뷰
    if ticket_type == "차단" and block_data:
        reason_list = []
        for b in block_data:
            gid = int(b["guild_id"])
            server_name = get_setting_cached(gid, "server") or str(gid)

            blocked_by_id = b.get("blocked_by")
            blocked_by = f"<@{blocked_by_id}>" if blocked_by_id else "알 수 없음"

            reason_list.append(
                f"[서버:{server_name}] {b['data_type']}={b['value']} "
                f"(사유:{b['reason']}, 차단자:{blocked_by})"
            )

        msg = "🚫 차단된 사용자로 확인되었습니다.\n\n"
        msg += "**차단 내역:**\n" + "\n".join(reason_list)
        msg += "\n\n관리자와 소통하여 이의 제기를 진행해주세요."

        await channel.send(
            content=member.mention,
            embed=discord.Embed(
                title="🚫 차단된 사용자 인증",
                description=msg,
                color=discord.Color.red()
            ),
            view=BlockTicketView(block_data)  # ✅ 기존 unblock 로직 그대로 사용
        )

    return channel
