from nonebot import require
from nonebot.plugin import PluginMetadata
from .config import Config
from . import handle
# from . import record
from . import scheduler

require("nonebot_plugin_chatrecorder")

__plugin_meta__ = PluginMetadata(
    name="CSTS",
    description="客服工单系统",
    usage="",
    config=Config,
)
