import time
from typing import Dict
from pathlib import Path

from nonebot import on_command, get_plugin_config, get_bot
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageSegment,
    MessageEvent,
    GroupMessageEvent,
    PrivateMessageEvent,
)
from nonebot.params import CommandArg
from nonebot.log import logger
from nonebot.exception import FinishedException, MatcherException

from jmcomic import (
    MissingAlbumPhotoException,
    RequestRetryAllFailException,
    JmcomicException,
)

from .config import Config
from .service import service
from .utils import (
    extract_album_id,
    format_album_card,
    build_forward_nodes,
    send_forward_msg_safe,
)

__plugin_meta__ = PluginMetadata(
    name="JMComic PDF 漫画助手",
    description="基于 JMComic-Crawler-Python 的禁漫天堂助手，支持车号直出全本高清 PDF 与站内搜索",
    usage=(
        "📖 JMComic 指令说明：\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "• jm <车号> 或 车牌 <车号>：下载并输出该本子的完整 PDF 文档\n"
        "• jmcard <车号>：查看本子详情卡片与封面（不下载）\n"
        "• jmsearch <关键词> [页码]：站内搜索本子列表\n"
        "• jmpreview <车号> [第几话] [张数]：预览指定章节图片（默认第1话前5张）\n"
        "• jmdownload <车号>：下载本子并上传发送 ZIP 压缩包\n"
        "• jmrank [日/周/月]：查看禁漫当前排行榜\n"
        "• jmhelp：查看本帮助信息"
    ),
    type="application",
    homepage="https://github.com/chenmodeshiguang/nonebot-plugin-jmcomic",
    supported_adapters={"~onebot.v11"},
    config=Config,
)

def _get_config() -> Config:
    try:
        return get_plugin_config(Config)
    except Exception:
        return Config()

config = _get_config()

# 频率冷却管理: {user_id: last_timestamp}
_user_cd_map: Dict[str, float] = {}


def check_permission_and_cd(event: MessageEvent, is_download: bool = False) -> bool:
    """检查群权限、管理员限制以及冷却时间"""
    user_id = str(event.user_id)

    # 1. 检查是否允许群聊使用
    if isinstance(event, GroupMessageEvent) and not config.jm_allow_group:
        return False

    # 获取 NoneBot 超级用户集合
    try:
        from nonebot import get_driver
        superusers = set(get_driver().config.superusers)
    except Exception:
        superusers = set()

    is_superuser = user_id in superusers
    is_group_admin = False
    if isinstance(event, GroupMessageEvent):
        role = getattr(event.sender, "role", "")
        is_group_admin = role in ("admin", "owner")

    # 2. 检查下载权限
    if is_download and config.jm_admin_only_download:
        if not (is_superuser or is_group_admin):
            return False

    # 3. 冷却时间检查（超级管理员免 CD）
    if not is_superuser and config.jm_cd > 0:
        now = time.time()
        last_time = _user_cd_map.get(user_id, 0.0)
        if now - last_time < config.jm_cd:
            return False
        _user_cd_map[user_id] = now

    return True


# ===================== 指令注册 =====================

matcher_info = on_command(
    "jm",
    aliases={"车牌", "禁漫", "jmpdf"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_card = on_command(
    "jmcard",
    aliases={"jm详情", "jminfo", "jm卡片"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_search = on_command(
    "jmsearch",
    aliases={"搜本子", "搜车牌", "jm搜索"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_preview = on_command(
    "jmpreview",
    aliases={"jm预览", "看本子", "本子预览"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_download = on_command(
    "jmdownload",
    aliases={"jm下载", "下载本子"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_rank = on_command(
    "jmrank",
    aliases={"jm排行", "禁漫排行", "本子排行"},
    priority=config.jm_command_priority,
    block=True,
)

matcher_help = on_command(
    "jmhelp",
    aliases={"jm帮助", "禁漫帮助"},
    priority=config.jm_command_priority,
    block=True,
)


# ===================== 1. 车号查询并输出 PDF 文档 =====================
@matcher_info.handle()
async def handle_info(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not check_permission_and_cd(event):
        await matcher_info.finish(f"⚠️ 指令冷却中（CD: {config.jm_cd}s），请勿频繁请求~")

    raw_text = args.extract_plain_text().strip()
    album_id = extract_album_id(raw_text)
    if not album_id:
        await matcher_info.finish("⚠️ 请输入有效的本子车号，例如：jm 427413")

    try:
        pdf_path, file_size, album_name, page_count = await service.download_and_pdf(album_id)
    except MissingAlbumPhotoException:
        await matcher_info.finish(f"❌ 未找到车号为 [JM{album_id}] 的本子，可能已被下架或车号有误。")
    except RequestRetryAllFailException as e:
        await matcher_info.finish(f"❌ 网络请求超时或重试耗尽，请检查网络/代理设置。\n错误详情: {e}")
    except JmcomicException as e:
        await matcher_info.finish(f"❌ 获取并生成 PDF 失败: {e}")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 生成 PDF 异常: {e}")
        await matcher_info.finish(f"❌ 处理发生未预期错误: {e}")

    # 直接通过 OneBot V11 文件上传接口发送 PDF，不发送额外文本
    upload_status = "success"
    err_detail = ""
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.upload_group_file(
                group_id=event.group_id,
                file=str(pdf_path.resolve()),
                name=pdf_path.name,
                _timeout=300.0,
            )
        else:
            await bot.upload_private_file(
                user_id=event.user_id,
                file=str(pdf_path.resolve()),
                name=pdf_path.name,
                _timeout=300.0,
            )
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower():
            logger.info(f"[JMComic] PDF 文件上传响应超时（协议端后台正在推送中）: {e}")
            upload_status = "timeout"
        else:
            logger.warning(f"[JMComic] PDF 文件上传接口调用失败: {e}")
            upload_status = "failed"
            err_detail = err_str

    # 成功或正在后台推送时直接静默完成，不往群内发送任何冗余文本
    if upload_status in ("success", "timeout"):
        return

    # 仅当协议端彻底不支持文件上传时，才在群内提示文件本地路径
    await matcher_info.finish(
        f"⚠️ PDF 已生成完成，但 QQ 远程文件上传失败 ({err_detail})，文件保存在服务器本地：\n"
        f"📂 {pdf_path}"
    )


# ===================== 2. 本子图文卡片查询 (纯预览) =====================
@matcher_card.handle()
async def handle_card(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not check_permission_and_cd(event):
        await matcher_card.finish(f"⚠️ 指令冷却中（CD: {config.jm_cd}s），请勿频繁请求~")

    raw_text = args.extract_plain_text().strip()
    album_id = extract_album_id(raw_text)
    if not album_id:
        await matcher_card.finish("⚠️ 请输入有效的本子车号，例如：jmcard 427413")

    await matcher_card.send(f"🔍 正在查询禁漫车号 [JM{album_id}] 的详情，请稍候...")

    try:
        album, cover_file = await service.get_album_detail(album_id)
        card_text = format_album_card(album)

        msg = Message()
        if cover_file and cover_file.exists():
            msg.append(MessageSegment.image(file=cover_file))
        msg.append(MessageSegment.text(card_text))

        await matcher_card.finish(msg)

    except MissingAlbumPhotoException:
        await matcher_card.finish(f"❌ 未找到车号为 [JM{album_id}] 的本子，可能已被下架或车号有误。")
    except RequestRetryAllFailException as e:
        await matcher_card.finish(f"❌ 网络请求超时或重试耗尽，请检查网络/代理设置。\n错误详情: {e}")
    except JmcomicException as e:
        await matcher_card.finish(f"❌ 获取本子信息失败: {e}")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 查询本子卡片异常: {e}")
        await matcher_card.finish(f"❌ 查询发生未预期错误: {e}")


# ===================== 2. 站内搜索 =====================
@matcher_search.handle()
async def handle_search(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not check_permission_and_cd(event):
        await matcher_search.finish(f"⚠️ 指令冷却中（CD: {config.jm_cd}s），请稍后再试~")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await matcher_search.finish("⚠️ 请提供搜索关键词，例如：jmsearch 纯爱 1")

    parts = raw_text.split()
    keyword = parts[0]
    page = 1
    if len(parts) > 1 and parts[1].isdigit():
        page = max(1, int(parts[1]))

    await matcher_search.send(f"🔍 正在检索关键词「{keyword}」(第 {page} 页)...")

    try:
        total, page_count, results = await service.search_albums(keyword, page)
        if not results:
            await matcher_search.finish(f"🤔 未找到与「{keyword}」相关的本子。")

        lines = [
            f"📚 搜索「{keyword}」结果",
            f"📄 第 {page}/{page_count} 页 | 共 {total} 条结果",
            "──────────────────",
        ]
        for aid, title, tags in results[:10]:
            tag_str = f" [{','.join(tags[:3])}]" if tags else ""
            lines.append(f"• [JM{aid}] {title}{tag_str}")

        lines.append("──────────────────")
        lines.append("💡 发送「jm <车号>」下载全本 PDF，发送「jmpreview <车号>」预览")
        if page < page_count:
            lines.append(f"💡 发送「jmsearch {keyword} {page + 1}」查看下一页")

        await matcher_search.finish("\n".join(lines))

    except RequestRetryAllFailException as e:
        await matcher_search.finish(f"❌ 搜索网络请求失败: {e}")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 搜索异常: {e}")
        await matcher_search.finish(f"❌ 搜索失败: {e}")


# ===================== 3. 章节图片预览 =====================
@matcher_preview.handle()
async def handle_preview(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not check_permission_and_cd(event):
        await matcher_preview.finish(f"⚠️ 指令冷却中（CD: {config.jm_cd}s），请稍后再试~")

    parts = args.extract_plain_text().strip().split()
    if not parts:
        await matcher_preview.finish("⚠️ 请输入本子车号，例如：jmpreview 427413 [第几话] [张数]")

    album_id = extract_album_id(parts[0])
    if not album_id:
        await matcher_preview.finish("⚠️ 未能识别有效车号，请检查输入。")

    photo_idx = 1
    if len(parts) > 1 and parts[1].isdigit():
        photo_idx = max(1, int(parts[1]))

    max_count = config.jm_max_preview_pages
    if len(parts) > 2 and parts[2].isdigit():
        max_count = min(int(parts[2]), 10)  # 最多允许 10 张

    await matcher_preview.send(f"⏳ 正在下载并解密 [JM{album_id}] 第 {photo_idx} 话前 {max_count} 张预览图...")

    try:
        ch_title, image_paths = await service.preview_album(album_id, photo_idx, max_count)
        if not image_paths:
            await matcher_preview.finish("❌ 未能获取到预览图片。")

        # 组装合并转发消息
        nodes_msgs = [
            f"📖 【JM{album_id}】{ch_title}\n✨ 预览前 {len(image_paths)} 张图片（已解码）："
        ]
        for img_path in image_paths:
            if img_path.exists():
                nodes_msgs.append(MessageSegment.image(file=img_path))

        forward_nodes = build_forward_nodes(bot, nodes_msgs, nickname="禁漫预览助手")
        await send_forward_msg_safe(bot, event, forward_nodes)

    except MissingAlbumPhotoException:
        await matcher_preview.finish(f"❌ 未找到车号为 [JM{album_id}] 的本子或章节。")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 预览异常: {e}")
        await matcher_preview.finish(f"❌ 获取预览失败: {e}")


# ===================== 4. 整本下载与打包 =====================
@matcher_download.handle()
async def handle_download(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    # 权限检查：下载需满足 admin / superuser（若开启限制）
    if not check_permission_and_cd(event, is_download=True):
        await matcher_download.finish("⛔ 抱歉，本子下载与打包功能仅限管理员或超级用户使用！")

    raw_text = args.extract_plain_text().strip()
    album_id = extract_album_id(raw_text)
    if not album_id:
        await matcher_download.finish("⚠️ 请输入要下载的本子车号，例如：jmdownload 427413")

    await matcher_download.send(f"⏳ 正在开始下载并打包 [JM{album_id}]，由于包含完整解密与压缩，过程需要一些时间，请耐心等待...")

    try:
        zip_path, file_size, album_name = await service.download_and_zip(album_id)
    except MissingAlbumPhotoException:
        await matcher_download.finish(f"❌ 车号 [JM{album_id}] 不存在或已被禁漫下架。")
    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 下载打包异常: {e}")
        await matcher_download.finish(f"❌ 下载本子失败: {e}")

    size_mb = file_size / (1024 * 1024)

    # 尝试通过 OneBot V11 文件接口上传（设置 300 秒超时）
    upload_status = "success"
    err_detail = ""
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.upload_group_file(
                group_id=event.group_id,
                file=str(zip_path.resolve()),
                name=zip_path.name,
                _timeout=300.0,
            )
        else:
            await bot.upload_private_file(
                user_id=event.user_id,
                file=str(zip_path.resolve()),
                name=zip_path.name,
                _timeout=300.0,
            )
    except Exception as e:
        err_str = str(e)
        if "timeout" in err_str.lower():
            logger.info(f"[JMComic] ZIP 文件上传响应超时（协议端后台正在推送中）: {e}")
            upload_status = "timeout"
        else:
            logger.warning(f"[JMComic] ZIP 文件上传接口调用失败: {e}")
            upload_status = "failed"
            err_detail = err_str

    if upload_status == "success":
        await matcher_download.finish(
            f"✅ [JM{album_id}] 《{album_name}》打包完成并已成功上传！\n📦 压缩包大小: {size_mb:.2f} MB"
        )
    elif upload_status == "timeout":
        await matcher_download.finish(
            f"✅ [JM{album_id}] 《{album_name}》打包完成并已提交上传！\n📦 压缩包大小: {size_mb:.2f} MB\n"
            f"⏳ 文件正在后台传输推送中，请稍候查看群文件或聊天窗口~"
        )
    else:
        await matcher_download.finish(
            f"✅ [JM{album_id}] 《{album_name}》下载打包完成！\n📦 大小: {size_mb:.2f} MB\n"
            f"⚠️ 注意：由于当前连接的 QQ 客户端不支持远程文件推送接口 ({err_detail})，文件已保存在服务器本地：\n"
            f"📂 {zip_path}"
        )


# ===================== 5. 热门排行榜 =====================
@matcher_rank.handle()
async def handle_rank(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not check_permission_and_cd(event):
        await matcher_rank.finish(f"⚠️ 指令冷却中（CD: {config.jm_cd}s），请稍后再试~")

    rank_arg = args.extract_plain_text().strip().lower() or "day"
    if rank_arg in ("周", "周榜", "week"):
        rank_type = "week"
    elif rank_arg in ("月", "月榜", "month"):
        rank_type = "month"
    else:
        rank_type = "day"

    await matcher_rank.send(f"📊 正在获取禁漫 {rank_type} 榜数据...")

    try:
        rank_title, results = await service.get_ranking(rank_type=rank_type, page=1)
        if not results:
            await matcher_rank.finish("🤔 未获取到排行榜数据。")

        lines = [f"🏆 {rank_title}", "──────────────────"]
        for idx, (aid, title) in enumerate(results[:10], start=1):
            lines.append(f"{idx}. [JM{aid}] {title}")

        lines.append("──────────────────")
        lines.append("💡 发送「jm <车号>」下载全本 PDF，发送「jmpreview <车号>」预览")
        await matcher_rank.finish("\n".join(lines))

    except (FinishedException, MatcherException):
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"[JMComic] 排行榜获取失败: {e}")
        await matcher_rank.finish(f"❌ 获取排行榜失败: {e}")


# ===================== 6. 帮助菜单 =====================
@matcher_help.handle()
async def handle_help():
    await matcher_help.finish(__plugin_meta__.usage)
