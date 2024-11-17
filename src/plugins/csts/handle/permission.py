from ..matcher import (
    close_ticket_matcher,
    force_close_ticket_mathcer,
    untake_ticket_matcher,
    get_ticket_matcher,
    take_ticket_matcher,
    scheduled_ticket_matcher,
    send_ticket_matcher,
    qid_close_ticket_matcher,
    help_matcher,
    search_qq_matcher,
    set_schedule_matcher,
    report_matcher
)
from ..config import plugin_config

from nonebot.adapters.onebot.v11 import Event
from nonebot.matcher import Matcher
from nonebot.permission import Permission, User


@close_ticket_matcher.permission_updater
@force_close_ticket_mathcer.permission_updater
@untake_ticket_matcher.permission_updater
@get_ticket_matcher.permission_updater
@take_ticket_matcher.permission_updater
@scheduled_ticket_matcher.permission_updater
@send_ticket_matcher.permission_updater
@qid_close_ticket_matcher.permission_updater
@help_matcher.permission_updater
@search_qq_matcher.permission_updater
@set_schedule_matcher.permission_updater
@report_matcher.permission_updater
# 群内确认响应者是后端
async def _(event: Event, matcher: Matcher) -> Permission:
    return Permission(User.from_event(event=event, perm=Permission(limit_mathcer_backend_bot)))


async def limit_mathcer_backend_bot(event: Event):
    if plugin_config.backend_bot:
        if event.self_id == int(plugin_config.backend_bot):
            return True
        else:
            return False
    else:
        return True
