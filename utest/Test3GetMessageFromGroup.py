from telethon import TelegramClient, functions, types
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

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化 Telegram 客户端
client = TelegramClient('session_name', api_id, api_hash)


async def get_messages(chat_id, limit=30, from_oldest=False):
    # 启动客户端并登录
    await client.start(phone=phone_number)
    direction = "从最早到最新" if from_oldest else "从最新到最早"
    logger.info(f"正在获取群组/频道 {chat_id} 的前 {limit} 条消息（{direction}）...")

    try:
        # 获取聊天信息
        chat = await client.get_entity(chat_id)
        chat_type = "超级群组" if getattr(chat, 'megagroup', False) else "频道"
        logger.info(f"聊天类型: {chat_type}, 标题: {chat.title}")
        print(f"聊天类型: {chat_type}, 标题: {chat.title}")

        # 获取消息
        message_count = 0
        processed_grouped_ids = set()  # 跟踪已处理的相册
        async for message in client.iter_messages(chat_id, limit=limit, reverse=from_oldest):
            # 如果消息属于已处理的相册，跳过
            if message.grouped_id and message.grouped_id in processed_grouped_ids:
                continue

            print(f"开始处理消息：---------------------------------- {message.id}")

            # 打印特定消息的 JSON 数据（例如 ID 567）
            if message.id == 567:
                logger.info(f"主消息 JSON 数据 (ID: {message.id}): {message.to_dict()}")

            # 获取发送者信息
            sender_name = "未知"
            sender_id = message.sender_id or 0
            if message.sender_id:
                try:
                    sender = await client.get_entity(message.sender_id)
                    if hasattr(sender, 'first_name'):  # 用户类型
                        sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or "匿名"
                    else:  # 频道类型
                        sender_name = sender.title or sender.username or "频道匿名"
                except Exception as e:
                    sender_name = f"获取失败: {e}"
                    logger.warning(f"获取发送者信息失败 (消息 ID: {message.id}): {e}")

            # 初始化消息内容和媒体列表
            content = message.text or "无文本"
            media_list = []
            send_time = message.date
            main_message = message
            query_comment_id = message.id

            # 处理相册（一组媒体）
            if message.grouped_id and message.grouped_id not in processed_grouped_ids:
                processed_grouped_ids.add(message.grouped_id)
                logger.info(f"处理相册 (Grouped ID: {message.grouped_id})")
                # 搜索相册消息（围绕主消息 ID）
                min_id = max(1, message.id - 50)  # 向前搜索 50 条
                max_id = message.id + 50  # 向后搜索 50 条
                grouped_messages = await client.get_messages(chat_id, min_id=min_id, max_id=max_id, limit=100)
                # 优先选择有 replies 或文本的消息作为主消息
                for grouped_message in grouped_messages:
                    if grouped_message.grouped_id == message.grouped_id:
                        if grouped_message.replies or grouped_message.text:
                            main_message = grouped_message
                            content = main_message.text or "无文本"
                            send_time = main_message.date
                            break
                for grouped_message in grouped_messages:
                    if grouped_message.grouped_id == message.grouped_id:
                        # 打印相册子消息的 JSON 数据
                        logger.info(f"相册子消息 JSON 数据 (ID: {grouped_message.id}): {grouped_message.to_dict()}")
                        # 处理媒体
                        if grouped_message.media:
                            media_type = "未知"
                            if isinstance(grouped_message.media, types.MessageMediaPhoto):
                                media_type = "图片"
                            elif isinstance(grouped_message.media, types.MessageMediaDocument):
                                mime_type = getattr(grouped_message.media.document, 'mime_type', '')
                                if mime_type.startswith('video/'):
                                    media_type = "视频"
                                elif mime_type == 'image/gif':
                                    media_type = "GIF"
                                else:
                                    media_type = f"其他文件 (MIME: {mime_type})"
                            else:
                                media_type = "其他媒体"
                            media_list.append({
                                'type': media_type,
                                'url': f"https://t.me/c/{str(chat_id)[4:]}/{grouped_message.id}"
                            })
                            logger.info(
                                f"相册媒体: {media_type}, URL: https://t.me/c/{str(chat_id)[4:]}/{grouped_message.id}")

            # 处理单条消息的媒体
            elif message.media and not message.grouped_id:
                logger.info(f"单条消息 JSON 数据 (ID: {message.id}): {message.to_dict()}")
                media_type = "未知"
                if isinstance(message.media, types.MessageMediaPhoto):
                    media_type = "图片"
                elif isinstance(message.media, types.MessageMediaDocument):
                    mime_type = getattr(message.media.document, 'mime_type', '')
                    if mime_type.startswith('video/'):
                        media_type = "视频"
                    elif mime_type == 'image/gif':
                        media_type = "GIF"
                    else:
                        media_type = f"其他文件 (MIME: {mime_type})"
                else:
                    media_type = "其他媒体"
                media_list.append({
                    'type': media_type,
                    'url': f"https://t.me/c/{str(chat_id)[4:]}/{message.id}"
                })
                logger.info(f"单条消息媒体: {media_type}, URL: https://t.me/c/{str(chat_id)[4:]}/{message.id}")

            # 获取评论数和查询评论 ID
            msg = await client.get_messages(chat_id, ids=main_message.id)
            comment_count = msg.replies.replies if msg and msg.replies else 0
            query_comment_id = main_message.id
            if main_message.replies:
                comment_chat_id = int(f"-100{main_message.replies.channel_id}")
            else:
                comment_chat_id = -1
            logger.debug(f"消息 {main_message.id} replies: {msg.replies}")

            # 打印消息信息（仅为主消息或单条消息）
            print(f"\n消息 ID: {message.id}")
            print(f"发送者: {sender_name} (ID: {sender_id})")
            print(f"内容: {content}")
            if media_list:
                print("媒体资源:")
                for media in media_list:
                    print(f"  - 类型: {media['type']}, URL: {media['url']}")
            else:
                print("媒体资源: 无")
            print(f"发送时间: {send_time}")
            print(f"评论数: {comment_count}")
            print(f"用于查询评论的 ID: {query_comment_id}")
            print(f"评频道ID: {comment_chat_id}")

            message_count += 1
            print(f"结束处理消息：---------------------------------- {message.id}")

        print(f"\n共获取 {message_count} 条消息")
        logger.info(f"共获取 {message_count} 条消息")

    except Exception as e:
        print(f"获取消息失败: {e}")
        logger.error(f"获取消息失败: {e}")

    # 断开客户端连接
    await client.disconnect()


# 运行脚本
if __name__ == '__main__':
    asyncio.run(get_messages(chat_id, limit=30, from_oldest=False))  # 默认从最新到最早
