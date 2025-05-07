from nonebot import on_keyword, on_shell_command, on_message, on_command
from nonebot.rule import to_me, ArgumentParser
from nonebot.permission import SUPERUSER
from sqlalchemy import select
from .rules import (
    is_customer,
    is_engineer,
)
from .model import Ticket, Status

# 定义命令
Types_Ticket = {
    "活动的": lambda id: select(Ticket).filter(Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "未接的": lambda id: select(Ticket).filter(Ticket.status != Status.CLOSED, Ticket.status != Status.SCHEDULED, Ticket.status != Status.PROCESSING).order_by(Ticket.begin_at.desc()),
    "预约的": lambda id: select(Ticket).filter(Ticket.status == Status.SCHEDULED).order_by(Ticket.begin_at.desc()),
    "我的": lambda engineer_id: select(Ticket).filter(Ticket.engineer_id == engineer_id,
                                                    Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),

}
Export_Types_Ticket = {
    **Types_Ticket,
    "完成的": lambda id: select(Ticket).filter(Ticket.status == Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "所有的": lambda id: select(Ticket).order_by(Ticket.begin_at.desc()),
    "所有我的": lambda engineer_id: select(Ticket).filter(Ticket.engineer_id == engineer_id).order_by(Ticket.begin_at.desc())
}

list_parser = ArgumentParser(prog="list")
list_parser.add_argument("type", help=f"工单种类:{' '.join(
    [key for key in Types_Ticket])}", type=str)
list_parser.add_argument("-a", help="用消息转发显示机主描述", action='store_true')

export_parser = ArgumentParser(prog="export")
export_parser.add_argument("type",help=f"工单种类:{' '.join(
    [key for key in Export_Types_Ticket])}", type=str)
export_parser.add_argument("-a", help="包含机主描述", action='store_true')

# engineer_parser = ArgumentParser(prog="engineers", description="工程师名单操作")
# engineer_parser_sub = engineer_parser.add_subparsers(
#     dest="sub", help='subcommand help')

# engineer_parser_add = engineer_parser_sub.add_parser("add", help="添加工程师")
# engineer_parser_add.add_argument("-a", help="加入通知群聊的所有人", action='store_true')
# engineer_parser_add.add_argument(
#     "--ids", action="extend", nargs="+", type=str, help="列出id")

# engineer_parser_del = engineer_parser_sub.add_parser("del", help="删除工程师")
# engineer_parser_del.add_argument(
#     "ids", action="extend", nargs="+", type=str, help="列出id")

# engineer_parser_list = engineer_parser_sub.add_parser("list", help="列出全部工程师")

# 定义响应器
customer_message = on_message(rule=is_customer & to_me(), priority=100)
engineer_message = on_message(rule=is_engineer & to_me(), priority=100)
help_matcher = on_command("help", rule=is_engineer & to_me(), aliases={
                          "帮助"}, priority=10, block=True)
list_ticket_matcher = on_shell_command("list", parser=list_parser, rule=is_engineer & to_me(), aliases={"列出"},
                                       priority=10, block=True)
search_qq_matcher = on_command("qq", rule=is_engineer & to_me(), aliases={
                               "搜索"}, priority=10, block=True)
get_ticket_matcher = on_command("get", rule=is_engineer & to_me(), aliases={
                                "获取"}, priority=10, block=True)
take_ticket_matcher = on_command("take", rule=is_engineer & to_me(), aliases={
                                 "接单"}, priority=10, block=True)
untake_ticket_matcher = on_command(
    "untake", rule=is_engineer & to_me(), aliases={"放单"}, priority=10, block=True)
close_ticket_matcher = on_command("close", rule=is_engineer & to_me(), aliases={
                                  "关单"}, priority=10, block=True)
qid_close_ticket_matcher = on_command(
    "qclose", rule=is_engineer & to_me(), aliases={"qq关单"}, priority=10, block=True)
force_close_ticket_mathcer = on_command("fclose", rule=is_engineer & to_me(), aliases={"强制关单"}, priority=10,
                                        block=True)
scheduled_ticket_matcher = on_command("scheduled", rule=is_engineer & to_me(), aliases={"预约"}, priority=10,
                                      block=True)
set_schedule_matcher = on_command(
    "set_schedule", rule=is_engineer & to_me(), aliases={"设置默认预约"}, priority=10, block=True)
send_ticket_matcher = on_command("send", rule=is_engineer & to_me(), aliases={
                                 "留言"}, priority=10, block=True)
report_matcher = on_command(
    "report", aliases={"报告", "统计"}, rule=is_engineer & to_me(), priority=10, block=True)
# op_engineer_matcher = on_shell_command("engineers", parser=engineer_parser, rule=to_me() & is_backend,
#                                        permission=SUPERUSER, priority=10, block=True)
who_asked_matcher = on_keyword(
    {"我恨你", "I hate you"}, rule=is_engineer, priority=11)

i_understand_matcher = on_keyword(
    {"谁懂", "Who understand"}, rule=is_engineer, priority=11)
