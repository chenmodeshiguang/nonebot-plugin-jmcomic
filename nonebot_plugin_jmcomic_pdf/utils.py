import re
from typing import Optional, List, Union
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment, MessageEvent, GroupMessageEvent
from nonebot.log import logger


def extract_album_id(text: str) -> Optional[str]:
    """
    从输入文本中提取禁漫车号 ID
    支持纯数字、带 JM/jm 前缀、网页 URL 或混排文本
    例如：
      - "427413" -> "427413"
      - "JM427413" -> "427413"
      - "https://18comic.vip/album/427413" -> "427413"
      - "快看这本 427413 贼顶" -> "427413"
    """
    if not text:
        return None
    text = text.strip()

    # 1. 尝试匹配 URL 中的 album/xxxx 或 photo/xxxx
    url_match = re.search(r'/(?:album|photo)/(\d+)', text, re.IGNORECASE)
    if url_match:
        return url_match.group(1)

    # 2. 尝试匹配 JMxxxxx 格式
    jm_match = re.search(r'\bjm(\d+)\b', text, re.IGNORECASE)
    if jm_match:
        return jm_match.group(1)

    # 3. 尝试匹配 4~8 位数字
    digits_match = re.search(r'\b(\d{4,8})\b', text)
    if digits_match:
        return digits_match.group(1)

    # 兜底：从字符串中提取最长连续数字串
    all_digits = re.findall(r'\d+', text)
    if all_digits:
        # 取长度在 4 到 8 位之间的第一个
        for d in all_digits:
            if 4 <= len(d) <= 8:
                return d
        return max(all_digits, key=len)

    return None


def format_album_card(album) -> str:
    """格式化本子详情卡片文本"""
    # 提取作者
    authors = album.authors if hasattr(album, "authors") and album.authors else []
    author_str = ", ".join(authors) if authors else (album.author if hasattr(album, "author") else "未知")

    # 提取标签（限制前 10 个以防过长刷屏）
    tags = album.tags if hasattr(album, "tags") and album.tags else []
    tag_str = ", ".join(tags[:10]) if tags else "无标签"
    if len(tags) > 10:
        tag_str += f" 等 {len(tags)} 个标签"

    # 章节列表摘要
    episodes = album.episode_list if hasattr(album, "episode_list") and album.episode_list else []
    ep_count = len(episodes)
    ep_summary = ""
    if ep_count > 1:
        ep_summary = f"\n📑 章节列表 (共 {ep_count} 话):"
        for i, ep in enumerate(episodes[:5]):
            # ep 格式为 (photo_id, photo_index, photo_title, ...)
            title = ep[2] if len(ep) > 2 else f"第 {i+1} 话"
            ep_summary += f"\n  [{i+1}] {title} (ID: {ep[0]})"
        if ep_count > 5:
            ep_summary += f"\n  ... 其余 {ep_count - 5} 话已省略"

    return (
        f"📖 【JM{album.id}】 {album.name}\n"
        f"✍️ 作者: {author_str}\n"
        f"🏷️ 标签: {tag_str}\n"
        f"📊 统计: 👀{getattr(album, 'views', '0')} | ❤️{getattr(album, 'likes', '0')} | 💬{getattr(album, 'comment_count', 0)}\n"
        f"📄 总页数: {getattr(album, 'page_count', 0)} 页\n"
        f"📅 更新: {getattr(album, 'update_date', getattr(album, 'pub_date', '未知'))}\n"
        f"🔗 链接: https://18comic.vip/album/{album.id}"
        f"{ep_summary}"
    )


def build_forward_nodes(
    bot: Bot,
    messages: List[Union[str, Message, MessageSegment]],
    nickname: str = "JMComic 禁漫助手"
) -> List[dict]:
    """构造 OneBot V11 自定义合并转发节点"""
    nodes = []
    user_id = int(bot.self_id)
    for msg in messages:
        content = msg if isinstance(msg, Message) else Message(msg)
        nodes.append(
            MessageSegment.node_custom(
                user_id=user_id,
                nickname=nickname,
                content=content
            )
        )
    return nodes


async def send_forward_msg_safe(
    bot: Bot,
    event: MessageEvent,
    nodes: List[dict],
    fallback_title: str = "预览内容"
) -> None:
    """
    安全发送合并转发消息，若由于平台限制或风控发送失败则尝试退避普通消息发送
    """
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
        else:
            await bot.send_private_forward_msg(user_id=event.user_id, messages=nodes)
    except Exception as e:
        logger.warning(f"合并转发消息发送失败: {e}，正在尝试回退单发模式...")
        # 降级：提取前几段消息直接发送
        for node in nodes[:3]:
            try:
                content = node.data.get("content")
                if content:
                    await bot.send(event, content)
            except Exception as ex:
                logger.error(f"降级发送单条消息亦失败: {ex}")
                break
