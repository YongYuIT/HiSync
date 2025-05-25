from telethon import TelegramClient, functions, types
import asyncio
import pandas as pd
import configparser

from telethon.tl.types import Channel, Chat

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')

api_id = int(config['telegram']['api_id'])
api_hash = config['telegram']['api_hash']
phone_number = config['telegram']['phone_number']

# 初始化 Telegram 客户端
client = TelegramClient('session_name', api_id, api_hash)


async def get_chats():
    # 启动客户端并登录
    await client.start(phone=phone_number)
    print("正在获取你加入的群组和频道...")

    # 存储聊天信息
    chats = []

    # 获取所有对话（群组、频道、私聊等）
    async for dialog in client.iter_dialogs():
        # 只处理群组和频道
        if dialog.is_group or dialog.is_channel:
            chat = await client.get_entity(dialog.id)

            entity = dialog.entity  # 更推荐使用 dialog 自带的 entity
            if isinstance(entity, Channel):
                chat_type = "超级群组" if entity.megagroup else "频道"
            elif isinstance(entity, Chat):
                chat_type = "普通群组"
            else:
                chat_type = "未知"

            # 收集聊天信息
            chat_info = {
                '类型': chat_type,
                '标题': dialog.title,
                'ID': dialog.id,
                '用户名': getattr(chat, 'username', '无'),
                '创建时间': str(getattr(chat, 'date', '未知'))
            }

            # 获取更多详细信息
            try:
                if dialog.is_channel or chat.megagroup:  # 频道或超级群组
                    full_chat = await client(functions.channels.GetFullChannelRequest(channel=chat))
                    chat_info['成员数'] = full_chat.full_chat.participants_count or "未知"
                    chat_info['描述'] = full_chat.full_chat.about or "无描述"
                else:  # 普通群组
                    full_chat = await client(functions.messages.GetFullChatRequest(chat_id=chat.id))
                    chat_info['成员数'] = full_chat.full_chat.participants_count or "未知"
                    chat_info['描述'] = full_chat.full_chat.about or "无描述"
            except Exception as e:
                chat_info['成员数'] = "未知"
                chat_info['描述'] = f"获取失败: {e}"

            chats.append(chat_info)

            # 打印信息
            print(f"\n类型: {chat_info['类型']}")
            print(f"标题: {chat_info['标题']}")
            print(f"ID: {chat_info['ID']}")
            print(f"成员数: {chat_info['成员数']}")
            print(f"描述: {chat_info['描述']}")
            print(f"用户名: {chat_info['用户名']}")
            print(f"创建时间: {chat_info['创建时间']}")

    # 保存到 CSV
    df = pd.DataFrame(chats)
    df.to_csv('telegram_chats.csv', index=False, encoding='utf-8')
    print("\n已保存到 telegram_chats.csv")

    # 断开连接
    await client.disconnect()


# 运行脚本
if __name__ == '__main__':
    asyncio.run(get_chats())
