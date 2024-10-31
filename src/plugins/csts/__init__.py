from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_chatrecorder")

from .config import Config
from .scheduler import *
from .handle import *
from .record import *


__plugin_meta__ = PluginMetadata(
    name="CSTS",
    description="客服工单系统",
    usage="",
    config=Config,
)
