from .customer import *
from .permission import *
from .engineer import *


# 处理好友添加请求
async def _friend_request(bot: Bot, event: Event, state: T_State) -> bool:
    return isinstance(event, FriendRequestEvent)

friend_request = on_notice(_friend_request, priority=1, block=True)


@friend_request.handle()
async def _(bot: Bot, event: FriendRequestEvent):
    await event.approve(bot)
