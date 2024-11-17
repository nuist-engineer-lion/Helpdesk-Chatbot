from argparse import Namespace
from typing import Annotated
from sqlalchemy import select
from nonebot_plugin_orm import async_scoped_session
from nonebot.params import ShellCommandArgs
from nonebot.exception import ParserExit
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message
from ..model import Engineer
from ..config import plugin_config
from ..utils import send_combined_msg, get_backend_bot
from ..matcher import op_engineer_matcher, engineer_parser, engineer_parser_add, engineer_parser_del

@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,
            args: Annotated[ParserExit, ShellCommandArgs()]):
    await op_engineer_matcher.finish(engineer_parser.format_help())


@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,
            args: Annotated[Namespace, ShellCommandArgs()]):
    if args.sub == "add":
        if args.a:
            users = await bot.get_group_member_list(group_id=int(plugin_config.notify_group))
            for user in users:
                if str(user['user_id']) not in [str(plugin_config.backend_bot), str(plugin_config.front_bot)]:
                    engineer = Engineer(engineer_id=str(user['user_id']))
                    session.add(engineer)
        else:
            if not args.ids:
                await op_engineer_matcher.finish(engineer_parser_add.format_help())
            for id in args.ids:
                engineer = Engineer(engineer_id=id)
                session.add(engineer)
        await session.commit()
    elif args.sub == "del":
        if not args.ids:
            await op_engineer_matcher.finish(engineer_parser_del.format_help())
        for id in args.ids:
            engineer = (await session.execute(select(Engineer).where(Engineer.engineer_id == id))).scalar_one_or_none()
            if engineer:
                await session.delete(engineer)
        await session.commit()
    elif args.sub == "list":
        engineers = (await session.execute(select(Engineer))).scalars().all()
        msg = []
        for engineer in engineers:
            msg += Message(engineer.engineer_id)
        await send_combined_msg(get_backend_bot(bot), msgs=msg, event=event)
    else:
        await op_engineer_matcher.finish(engineer_parser.format_usage())
