from argparse import ArgumentParser
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from .model import Engineer,Ticket,Status
from .config import plugin_config
from nonebot import get_bot,get_bots
from nonebot.adapters.onebot.v11 import MessageEvent,GroupMessageEvent,PrivateMessageEvent

# 定义规则

def is_front(event: MessageEvent) -> bool:
    # 没有配置前端一律视作前端
    if not plugin_config.front_bot:
        return True
    if event.self_id == int(plugin_config.front_bot):
        return True
    return False


def is_backend(event: MessageEvent) -> bool:
    if not plugin_config.backend_bot:
        return True
    if event.self_id == int(plugin_config.backend_bot):
        return True
    return False


async def is_engineer(event: MessageEvent) -> bool:
    # 从后端工程师发来的消息
    if is_backend(event):
        if isinstance(event, GroupMessageEvent):
            return event.group_id == plugin_config.notify_group
        session = get_session()
        async with session.begin():
            return bool((await session.execute(
                select(Engineer).filter(Engineer.engineer_id == event.get_user_id()))).scalar_one_or_none())
    else:
        return False


async def is_customer(event: PrivateMessageEvent) -> bool:
    # 自己不会是机主
    if event.get_user_id() in get_bots():
        return False
    # 只要是前端发来的一律视作机主(方便整活了属于是)
    return is_front(event)


