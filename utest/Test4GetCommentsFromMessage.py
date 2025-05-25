from telethon import TelegramClient, types
from telethon.errors import FloodWaitError
import asyncio
import logging
import configparser

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')

api_id = int(config['telegram']['api_id'])
api_hash = config['telegram']['api_hash']
phone_number = config['telegram']['phone_number']

chat_id = -1002519369479

# 设置日志（强制 DEBUG）
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# 初始化 Telegram 客户端
client = TelegramClient('session_name', api_id, api_hash)


async def get_comments(chat_id, comment_chat_id, message_id, limit=100, from_oldest=False):
    # 启动客户端并登录
    await client.start(phone=phone_number)
    direction = "从最早到最新" if from_oldest else "从最新到最早"
    logger.info(f"正在获取消息 {message_id} 的前 {limit} 条评论（{direction}）...")

    try:
        # 获取聊天信息
        chat = await client.get_entity(chat_id)
        chat_type = "超级群组" if getattr(chat, 'megagroup', False) else "频道"
        logger.info(f"聊天类型: {chat_type}, 标题: {chat.title}")
        print(f"聊天类型: {chat_type}, 标题: {chat.title}")

        try:
            comment_chat = await client.get_entity(comment_chat_id)
            logger.debug(f"评论频道访问成功: {comment_chat.title}")
        except Exception as e:
            logger.error(f"无法访问评论频道 {comment_chat_id}: {e}")
            print(f"请加入 t.me/c/2021393035 或提供邀请链接")
            return

        # 检查主消息是否存在并获取评论数
        main_msg = await client.get_messages(chat_id, ids=message_id)
        if not main_msg:
            print(f"消息 ID {message_id} 不存在")
            logger.error(f"消息 ID {message_id} 不存在")
            return
        comment_count = main_msg.replies.replies if main_msg.replies else 0
        print(f"消息 {message_id} 有 {comment_count} 条评论")
        logger.info(f"消息 {message_id} 有 {comment_count} 条评论")

        # 获取评论
        comment_iterator = client.iter_messages(chat_id, limit=limit, reply_to=message_id, reverse=from_oldest)
        comment_processed = 0
        processed_grouped_ids = set()  # 跟踪已处理的相册

        async for comment in comment_iterator:
            # 如果评论属于已处理的相册，跳过
            if comment.grouped_id and comment.grouped_id in processed_grouped_ids:
                continue

            print(f"开始处理评论：---------------------------------- {comment.id}")

            # 打印特定评论的 JSON 数据（例如 ID 25109）
            if comment.id == 25109:
                logger.info(f"评论 JSON 数据 (ID: {comment.id}): {comment.to_dict()}")

            # 获取发送者信息
            sender_name = "未知"
            sender_id = comment.sender_id or 0
            if comment.sender_id:
                try:
                    sender = await client.get_entity(comment.sender_id)
                    if hasattr(sender, 'first_name'):  # 用户类型
                        sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or "匿名"
                    else:  # 频道类型
                        sender_name = sender.title or sender.username or "频道匿名"
                except Exception as e:
                    sender_name = f"获取失败: {e}"
                    logger.warning(f"获取发送者信息失败 (评论 ID: {comment.id}): {e}")

            # 初始化评论内容和媒体列表
            content = comment.text or "无文本"
            media_list = []
            send_time = comment.date
            main_comment = comment

            # 处理相册（一组媒体）
            if comment.grouped_id and comment.grouped_id not in processed_grouped_ids:
                processed_grouped_ids.add(comment.grouped_id)
                logger.info(f"处理评论相册 (Grouped ID: {comment.grouped_id})")
                # 搜索相册评论（扩大范围）
                min_id = max(1, comment.id - 500)
                max_id = comment.id + 500
                try:
                    grouped_comments = await client.get_messages(comment_chat_id, min_id=min_id, max_id=max_id,
                                                                 limit=1000)
                except FloodWaitError as e:
                    logger.warning(f"防洪限制，等待 {e.seconds} 秒")
                    await asyncio.sleep(e.seconds)
                    grouped_comments = await client.get_messages(comment_chat_id, min_id=min_id, max_id=max_id,
                                                                 limit=1000)
                logger.debug(f"获取到 {len(grouped_comments)} 条相册评论，ID 范围: {min_id}-{max_id}")
                logger.debug(
                    f"相册评论 ID 列表: {[c.id for c in grouped_comments if c.grouped_id == comment.grouped_id]}")
                # 优先选择有文本的评论作为主评论
                for grouped_comment in grouped_comments:
                    if grouped_comment.grouped_id == comment.grouped_id:
                        if grouped_comment.text:
                            main_comment = grouped_comment
                            content = main_comment.text or "无文本"
                            send_time = main_comment.date
                            break
                logger.info(f"选择主评论 ID: {main_comment.id}, 文本: {main_comment.text or '无'}")
                # 处理相册评论的媒体（包括当前评论）
                for grouped_comment in grouped_comments:
                    if grouped_comment.grouped_id == comment.grouped_id:
                        logger.debug(
                            f"检查评论 ID: {grouped_comment.id}, Grouped ID: {grouped_comment.grouped_id}, 文本: {grouped_comment.text or '无'}, 媒体: {grouped_comment.media}")
                        logger.info(f"相册子评论 JSON 数据 (ID: {grouped_comment.id}): {grouped_comment.to_dict()}")
                        if grouped_comment.media:
                            media_type = "未知"
                            if isinstance(grouped_comment.media, types.MessageMediaPhoto):
                                media_type = "图片"
                            elif isinstance(grouped_comment.media, types.MessageMediaDocument):
                                mime_type = getattr(grouped_comment.media.document, 'mime_type', '')
                                if mime_type.startswith('video/'):
                                    media_type = "视频"
                                elif mime_type == 'image/gif':
                                    media_type = "GIF"
                                else:
                                    media_type = f"其他文件 (MIME: {mime_type})"
                            else:
                                media_type = "其他媒体"
                            media_url = f"https://t.me/c/{str(comment_chat_id)[4:]}/{grouped_comment.id}"
                            media_list.append({
                                'type': media_type,
                                'url': media_url
                            })
                            logger.debug(f"添加媒体: ID {grouped_comment.id}, URL: {media_url}")
                            logger.info(f"相册评论媒体: {media_type}, URL: {media_url}")

            # 处理单条评论的媒体
            elif comment.media and not comment.grouped_id:
                logger.info(f"单条评论 JSON 数据 (ID: {comment.id}): {comment.to_dict()}")
                media_type = "未知"
                if isinstance(comment.media, types.MessageMediaPhoto):
                    media_type = "图片"
                elif isinstance(comment.media, types.MessageMediaDocument):
                    mime_type = getattr(comment.media.document, 'mime_type', '')
                    if mime_type.startswith('video/'):
                        media_type = "视频"
                    elif mime_type == 'image/gif':
                        media_type = "GIF"
                    else:
                        media_type = f"其他文件 (MIME: {mime_type})"
                else:
                    media_type = "其他媒体"
                media_url = f"https://t.me/c/{str(comment_chat_id)[4:]}/{comment.id}"
                media_list.append({
                    'type': media_type,
                    'url': media_url
                })
                logger.debug(f"添加媒体: ID {comment.id}, URL: {media_url}")
                logger.info(f"单条评论媒体: {media_type}, URL: {media_url}")

            # 打印媒体列表
            logger.debug(f"媒体列表: {len(media_list)} 条, URLs: {[m['url'] for m in media_list]}")

            # 打印评论信息
            print(f"\n评论 ID: {comment.id}")
            print(f"发送者: {sender_name} (ID: {sender_id})")
            print(f"内容: {content}")
            if media_list:
                print("媒体资源:")
                for media in media_list:
                    print(f"  - 类型: {media['type']}, URL: {media['url']}")
            else:
                print("媒体资源: 无")
            print(f"发送时间: {send_time}")

            comment_processed += 1
            print(f"结束处理评论：---------------------------------- {comment.id}")

        print(f"\n共获取 {comment_processed} 条评论")
        logger.info(f"共获取 {comment_processed} 条评论")

    except Exception as e:
        print(f"获取评论失败: {e}")
        logger.error(f"获取评论失败: {e}")

    # 断开客户端连接
    await client.disconnect()


# 运行脚本
if __name__ == '__main__':
    asyncio.run(get_comments(chat_id, message_id=65, comment_chat_id=-1002500001193, limit=100, from_oldest=False))
