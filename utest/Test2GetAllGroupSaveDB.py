from telethon import TelegramClient, functions, types
import asyncio
import sqlite3
import logging
import re
import configparser

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')

api_id = int(config['telegram']['api_id'])
api_hash = config['telegram']['api_hash']
phone_number = config['telegram']['phone_number']

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化 Telegram 客户端
client = TelegramClient('session_name', api_id, api_hash)


# 初始化 SQLite 数据库
def init_db():
    conn = sqlite3.connect('telegram_chats.db')
    cursor = conn.cursor()
    # 创建 chats 表，包含 link 和 invite_link 字段
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS chats
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       type
                       TEXT,
                       title
                       TEXT,
                       chat_id
                       INTEGER
                       UNIQUE,
                       members_count
                       TEXT,
                       description
                       TEXT,
                       username
                       TEXT,
                       link
                       TEXT,
                       invite_link
                       TEXT,
                       comm_title
                       TEXT,
                       comm_chat_id
                       INTEGER,
                       created_at
                       TEXT
                   )
                   ''')
    conn.commit()
    return conn, cursor


# 检查 chat_id 是否存在
def check_chat_exists(cursor, chat_id):
    cursor.execute('SELECT chat_id FROM chats WHERE chat_id = ?', (chat_id,))
    return cursor.fetchone() is not None


# 更新现有记录
def update_chat(cursor, chat_info):
    cursor.execute('''
                   UPDATE chats
                   SET type          = ?,
                       title         = ?,
                       members_count = ?,
                       description   = ?,
                       username      = ?,
                       link          = ?,
                       invite_link   = ?,
                       comm_title    = ?,
                       comm_chat_id  = ?,
                       created_at    = ?
                   WHERE chat_id = ?
                   ''', (
                       chat_info['类型'],
                       chat_info['标题'],
                       chat_info['成员数'],
                       chat_info['描述'],
                       chat_info['用户名'],
                       chat_info['链接'],
                       chat_info['邀请链接'],
                       chat_info['评论群标题'],
                       chat_info['评论群ID'],
                       chat_info['创建时间'],
                       chat_info['ID']
                   ))


# 插入新记录
def insert_chat(cursor, chat_info):
    cursor.execute('''
                   INSERT INTO chats (type, title, chat_id, members_count, description, username, link, invite_link,
                                      comm_title, comm_chat_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ''', (
                       chat_info['类型'],
                       chat_info['标题'],
                       chat_info['ID'],
                       chat_info['成员数'],
                       chat_info['描述'],
                       chat_info['用户名'],
                       chat_info['链接'],
                       chat_info['邀请链接'],
                       chat_info['评论群标题'],
                       chat_info['评论群ID'],
                       chat_info['创建时间']
                   ))


# 从描述或固定消息中提取邀请链接
async def extract_invite_link(chat, chat_id):
    try:
        # 获取群组/频道描述
        full_chat = await client(functions.channels.GetFullChannelRequest(channel=chat))
        description = full_chat.full_chat.about or ""
        # 查找 t.me/+<hash> 或 t.me/joinchat/<hash>
        invite_pattern = r'(t\.me/\+[a-zA-Z0-9_-]+|t\.me/joinchat/[a-zA-Z0-9_-]+)'
        matches = re.findall(invite_pattern, description)
        if matches:
            logger.info(f"从描述中提取到邀请链接: {matches[0]}")
            return matches[0]

        # 检查固定消息
        async for message in client.iter_messages(chat_id, limit=1, filter=types.InputMessagesFilterPinned):
            if message.text:
                matches = re.findall(invite_pattern, message.text)
                if matches:
                    logger.info(f"从固定消息中提取到邀请链接: {matches[0]}")
                    return matches[0]
        return None
    except Exception as e:
        logger.error(f"提取 {chat_id} 的邀请链接失败: {e}")
        return None


async def get_chats():
    # 初始化数据库
    conn, cursor = init_db()

    # 启动客户端并登录
    await client.start(phone=phone_number)
    logger.info("正在获取你加入的群组和频道...")

    # 获取所有对话（群组、频道、私聊等）
    async for dialog in client.iter_dialogs():
        # 只处理群组和频道
        if dialog.is_group or dialog.is_channel:
            try:
                chat = await client.get_entity(dialog.id)
                chat_type = "超级群组" if getattr(chat, 'megagroup', False) else "普通群组" if dialog.is_group else "频道"

                # 生成公开链接
                username = getattr(chat, 'username', None)
                if username:
                    link = f"t.me/{username.lstrip('@')}"
                else:
                    link = f"t.me/c/{str(dialog.id)[4:]}" if dialog.id < 0 else "私密"

                # 获取邀请链接
                invite_link = "无"
                try:
                    invite = await client(functions.messages.ExportChatInviteRequest(peer=chat))
                    invite_link = invite.link
                    logger.info(f"成功获取 {dialog.title} (ID: {dialog.id}) 的邀请链接: {invite_link}")
                except Exception as e:
                    if "ChatAdminRequiredError" in str(e):
                        invite_link = "获取失败: 需要管理员权限"
                        logger.warning(f"无法获取 {dialog.title} (ID: {dialog.id}) 的邀请链接：需要管理员权限")
                        # 尝试从描述或固定消息中提取
                        extracted_link = await extract_invite_link(chat, dialog.id)
                        if extracted_link:
                            invite_link = extracted_link
                    else:
                        invite_link = f"获取失败: {e}"
                        logger.error(f"获取 {dialog.title} (ID: {dialog.id}) 邀请链接失败: {e}")

                # 收集聊天信息
                chat_info = {
                    '类型': chat_type,
                    '标题': dialog.title,
                    'ID': dialog.id,
                    '用户名': username or '无',
                    '链接': link,
                    '邀请链接': invite_link,
                    '创建时间': str(getattr(chat, 'date', '未知'))
                }

                # 获取更多详细信息
                try:
                    if dialog.is_channel or getattr(chat, 'megagroup', False):  # 频道或超级群组
                        full_chat = await client(functions.channels.GetFullChannelRequest(channel=chat))
                        chat_info['成员数'] = full_chat.full_chat.participants_count or "未知"
                        chat_info['描述'] = full_chat.full_chat.about or "无描述"
                    else:  # 普通群组
                        full_chat = await client(functions.messages.GetFullChatRequest(chat_id=chat.id))
                        chat_info['成员数'] = full_chat.full_chat.participants_count or "未知"
                        chat_info['描述'] = full_chat.full_chat.about or "无描述"
                    # 检查是否有 discussion_group 绑定
                    if full_chat.full_chat.linked_chat_id:
                        linked_chat_id = full_chat.full_chat.linked_chat_id
                        linked_chat = await client.get_entity(linked_chat_id)
                        chat_info['评论群标题'] = linked_chat.title or "无描述"
                        chat_info['评论群ID'] = int(f"-100{linked_chat_id}") or "无描述"

                    else:
                        chat_info['评论群标题'] = "无描述"
                        chat_info['评论群ID'] = "无描述"
                except Exception as e:
                    chat_info['成员数'] = "未知"
                    chat_info['描述'] = f"获取失败: {e}"
                    logger.error(f"获取 {dialog.title} (ID: {dialog.id}) 详细信息失败: {e}")

                # 检查 chat_id 是否存在
                if check_chat_exists(cursor, chat_info['ID']):
                    # 更新现有记录
                    update_chat(cursor, chat_info)
                    logger.info(f"已更新记录: {chat_info['标题']} (ID: {chat_info['ID']})")
                else:
                    # 插入新记录
                    insert_chat(cursor, chat_info)
                    logger.info(f"已插入新记录: {chat_info['标题']} (ID: {chat_info['ID']})")

                # 打印信息
                print(f"\n类型: {chat_info['类型']}")
                print(f"标题: {chat_info['标题']}")
                print(f"ID: {chat_info['ID']}")
                print(f"成员数: {chat_info['成员数']}")
                print(f"描述: {chat_info['描述']}")
                print(f"用户名: {chat_info['用户名']}")
                print(f"链接: {chat_info['链接']}")
                print(f"邀请链接: {chat_info['邀请链接']}")
                print(f"创建时间: {chat_info['创建时间']}")
                print(f"评论群标题: {chat_info['评论群标题']}")
                print(f"评论群ID: {chat_info['评论群ID']}")

            except Exception as e:
                logger.error(f"处理对话 {dialog.title} (ID: {dialog.id}) 失败: {e}")
                print(f"处理对话 {dialog.title} (ID: {dialog.id}) 失败: {e}")

    # 提交数据库更改并关闭
    conn.commit()
    conn.close()
    logger.info("已保存到 telegram_chats.db")

    # 断开 Telegram 客户端连接
    await client.disconnect()


# 运行脚本
if __name__ == '__main__':
    asyncio.run(get_chats())
