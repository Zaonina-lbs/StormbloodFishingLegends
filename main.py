import os
import shlex

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入游戏引擎模块（所有游戏逻辑均为纯函数，无需异步包装）
from .game_engine import (
    init_engine,
    register_user,
    sign_in,
    check_gold,
    get_fish_help,
    get_fish_version,
    set_bait,
    go_fishing,
    view_weather,
    view_inventory,
    view_fish_pond,
    get_current_bait,
    clear_bait,
    view_fish_pool,
    lock_fish,
    unlock_fish,
    sell_fish_by_name,
    sell_fish_by_id,
    sell_all_fish,
    view_shop,
    buy_item,
    krypton,
    view_krypton_log,
    fish_handbook,
    fishing_log,
    leaderboard,
    get_distinct_regions,
    get_distinct_grounds,
    compensate,
    compensate_lure,
    my_info,
    set_weather_command,
)

# AstrBot 路径工具
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path


def parse_args(message_str: str):
    """安全地解析消息字符串中的参数，支持引号括起来的参数"""
    # 去掉首部可能存在的 /
    s = message_str.strip()
    if s.startswith("/"):
        s = s[1:]
    try:
        parts = shlex.split(s)
    except ValueError:
        parts = s.split()
    return parts


@register(
    "stormblood_fishing_legends",
    "Zaonina",
    "红莲垂钓异闻 - FF14群聊钓鱼小游戏",
    "v1.0.0",
)
class FishingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化——在 AstrBot 数据目录下创建插件专用目录并初始化游戏引擎"""
        # 获取 AstrBot 插件数据根目录: <root>/data/plugin_data
        plugin_data_root = get_astrbot_plugin_data_path()
        # 为本插件创建独立子目录，避免与其他插件冲突
        self_data_dir = os.path.join(plugin_data_root, "stormblood_fishing_legends")
        os.makedirs(self_data_dir, exist_ok=True)

        # 初始化游戏引擎数据库，数据库文件将存放在 data_dir 下
        init_engine(data_dir=self_data_dir)

        logger.info(f"红莲垂钓异闻 插件已加载，数据目录: {self_data_dir}")

    # ==================== 账号系统 ====================

    @filter.command("钓鱼注册")
    async def cmd_register(self, event: AstrMessageEvent):
        """注册钓鱼账号"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = register_user(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("签到")
    async def cmd_signin(self, event: AstrMessageEvent):
        """每日签到，获取金币或鱼饵奖励"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = sign_in(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("查看金币")
    async def cmd_check_gold(self, event: AstrMessageEvent):
        """查看当前金币数量"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = check_gold(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("钓鱼帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示钓鱼游戏帮助信息"""
        yield event.plain_result(get_fish_help())

    @filter.command("鱼池版本")
    async def cmd_version(self, event: AstrMessageEvent):
        """查看鱼池版本"""
        yield event.plain_result(get_fish_version())

    # ==================== 钓鱼核心 ====================

    @filter.command("使用鱼饵")
    async def cmd_set_bait(self, event: AstrMessageEvent):
        """设置默认鱼饵"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        bait_name = args[1] if len(args) >= 2 else None
        result = set_bait(user_id, group_id, bait_name)
        yield event.plain_result(result)

    @filter.command("钓鱼")
    async def cmd_fishing(self, event: AstrMessageEvent):
        """执行钓鱼操作：/钓鱼 [鱼饵] [钓场] [次数]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        # args[0] = "钓鱼", 后续参数：bait, fishing_ground, count（均为可选）
        bait = args[1] if len(args) >= 2 else None
        fishing_ground = args[2] if len(args) >= 3 else None
        count = args[3] if len(args) >= 4 else None
        result = go_fishing(
            user_id,
            group_id,
            bait_param=bait,
            fishing_ground=fishing_ground,
            count=count,
        )
        yield event.plain_result(result)

    @filter.command("查看天气")
    async def cmd_weather(self, event: AstrMessageEvent):
        """查看各钓场天气预报"""
        yield event.plain_result(view_weather())

    # ==================== 背包与鱼塘 ====================

    @filter.command("查看背包")
    async def cmd_inventory(self, event: AstrMessageEvent):
        """查看背包中的鱼饵"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = view_inventory(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("查看鱼塘")
    async def cmd_fish_pond(self, event: AstrMessageEvent):
        """查看钓上的鱼塘：/查看鱼塘 [页码]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        page = args[1] if len(args) >= 2 else 1
        result = view_fish_pond(user_id, group_id, page=page)
        yield event.plain_result(result)

    @filter.command("查看当前鱼饵")
    async def cmd_current_bait(self, event: AstrMessageEvent):
        """查看当前默认鱼饵"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = get_current_bait(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("不使用鱼饵")
    async def cmd_clear_bait(self, event: AstrMessageEvent):
        """恢复万能鱼饵"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = clear_bait(user_id, group_id)
        yield event.plain_result(result)

    @filter.command("当前鱼池")
    async def cmd_fish_pool(self, event: AstrMessageEvent):
        """查看当前天气下可钓的鱼：/当前鱼池 [鱼饵]"""
        args = parse_args(event.message_str)
        bait_name = args[1] if len(args) >= 2 else None
        yield event.plain_result(view_fish_pool(bait_name=bait_name))

    @filter.command("锁定")
    async def cmd_lock(self, event: AstrMessageEvent):
        """锁定鱼：/锁定 [id]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        fish_id = args[1] if len(args) >= 2 else None
        result = lock_fish(user_id, group_id, fish_id)
        yield event.plain_result(result)

    @filter.command("解锁")
    async def cmd_unlock(self, event: AstrMessageEvent):
        """解锁鱼：/解锁 [id]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        fish_id = args[1] if len(args) >= 2 else None
        result = unlock_fish(user_id, group_id, fish_id)
        yield event.plain_result(result)

    # ==================== 交易与出售 ====================

    @filter.command("出售")
    async def cmd_sell(self, event: AstrMessageEvent):
        """出售鱼：/出售 [鱼名] 或 /出售 id[N]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        msg = event.message_str.strip()
        # 取 /出售 后面的部分
        remain = msg
        if remain.startswith("/"):
            remain = remain[1:]
        parts = remain.split(maxsplit=1)
        arg = parts[1] if len(parts) >= 2 else ""

        if arg.lower().startswith("id"):
            fish_id_str = arg[2:].strip()
            result = sell_fish_by_id(user_id, group_id, fish_id_str)
        elif arg.isdigit():
            result = sell_fish_by_id(user_id, group_id, arg)
        else:
            result = sell_fish_by_name(user_id, group_id, arg)
        yield event.plain_result(result)

    @filter.command("全部出售")
    async def cmd_sell_all(self, event: AstrMessageEvent):
        """出售所有未锁定的鱼"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = sell_all_fish(user_id, group_id)
        yield event.plain_result(result)

    # ==================== 商店 ====================

    @filter.command("商城")
    async def cmd_shop(self, event: AstrMessageEvent):
        """查看商城"""
        yield event.plain_result(view_shop())

    @filter.command("购买道具")
    async def cmd_buy(self, event: AstrMessageEvent):
        """购买道具：/购买道具 [item_id] [数量]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        item_id = args[1] if len(args) >= 2 else None
        amount = args[2] if len(args) >= 3 else 1
        result = buy_item(user_id, group_id, item_id, amount)
        yield event.plain_result(result)

    # ==================== 氪金（管理员） ====================

    @filter.command("氪金")
    async def cmd_krypton(self, event: AstrMessageEvent):
        """氪金添加金币：/氪金 [金币]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        gold = args[1] if len(args) >= 2 else None
        result = krypton(user_id, group_id, gold)
        yield event.plain_result(result)

    @filter.command("查看账单")
    async def cmd_krypton_log(self, event: AstrMessageEvent):
        """查看氪金账单"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        result = view_krypton_log(user_id, group_id)
        yield event.plain_result(result)

    # ==================== 管理员 ====================

    @filter.command("补偿")
    async def cmd_compensate(self, event: AstrMessageEvent):
        """管理员向目标用户补偿金币：/补偿 [目标user_id] [金币]"""
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        target_user_id = args[1] if len(args) >= 2 else None
        gold = args[2] if len(args) >= 3 else None
        result = compensate(operator_id, group_id, target_user_id, gold)
        yield event.plain_result(result)

    @filter.command("我的信息")
    async def cmd_my_info(self, event: AstrMessageEvent):
        """查看自己的 user_id"""
        user_id = event.get_sender_id()
        result = my_info(user_id)
        yield event.plain_result(result)

    # ==================== 图鉴与排行榜 ====================

    @filter.command("鱼群图鉴")
    async def cmd_handbook(self, event: AstrMessageEvent):
        """查看鱼群图鉴：/鱼群图鉴 [地区|钓场|页码] [页码]
        用法：
          /鱼群图鉴              → 全地区第1页
          /鱼群图鉴 2            → 全地区第2页
          /鱼群图鉴 红玉海       → 红玉海地区第1页
          /鱼群图鉴 红玉海 2     → 红玉海地区第2页
          /鱼群图鉴 白银水路     → 白银水路钓场第1页
          /鱼群图鉴 白银水路 2   → 白银水路钓场第2页
        """
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        # args[0] = "鱼群图鉴"
        param1 = args[1] if len(args) >= 2 else None
        param2 = args[2] if len(args) >= 3 else None

        # 获取所有地区和钓场名称，用于智能匹配
        regions = get_distinct_regions()
        grounds = get_distinct_grounds()

        region = None
        fishing_ground = None
        page = 1

        if param1 is None:
            # /鱼群图鉴 → 全地区第1页
            pass
        elif param2 is not None:
            # 有2个参数: /鱼群图鉴 param1 param2
            # param1 是地区或钓场，param2 是页码
            if param1 in regions:
                region = param1
            elif param1 in grounds:
                fishing_ground = param1
            # param2 始终作为页码处理（如果不是数字会fallback到1）
            try:
                page = int(param2)
            except (ValueError, TypeError):
                page = 1
        else:
            # 只有1个参数: /鱼群图鉴 param1
            # 判断是数字(页码)、地区还是钓场
            try:
                page = int(param1)
                # 纯数字 → 全地区，页码=param1
            except (ValueError, TypeError):
                # 非数字 → 判断是地区还是钓场
                if param1 in regions:
                    region = param1
                elif param1 in grounds:
                    fishing_ground = param1
                page = 1

        if page < 1:
            page = 1

        result = fish_handbook(
            user_id, group_id, page=page, region=region, fishing_ground=fishing_ground
        )
        yield event.plain_result(result)

    @filter.command("钓鱼记录")
    async def cmd_fishing_log(self, event: AstrMessageEvent):
        """查看钓鱼记录：/钓鱼记录 [页码]"""
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        page = args[1] if len(args) >= 2 else 1
        result = fishing_log(user_id, group_id, page=page)
        yield event.plain_result(result)

    @filter.command("排行榜")
    async def cmd_leaderboard(self, event: AstrMessageEvent):
        """查看排行榜：/排行榜 [鱼名] [大/小] [鱼的种类] [页码]
        用法：
          /排行榜                  → 全部鱼类第1页
          /排行榜 2                → 全部鱼类第2页
          /排行榜 冥河灯            → 冥河灯尺寸排行榜
          /排行榜 冥河灯 小         → 冥河灯最小尺寸排行榜
          /排行榜 鱼王              → 所有鱼王的排行榜
          /排行榜 鱼王 小 2         → 所有鱼王最小尺寸排行榜第2页
          /排行榜 冥河灯 大 鱼皇    → 冥河灯(鱼皇)尺寸排行榜
        """
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        fish_name = None
        size_order = None
        fish_type = None
        page = 1
        for arg in args[1:]:
            if arg in ("大", "小"):
                size_order = arg
            elif arg in ("鱼王", "鱼皇", "普通鱼"):
                fish_type = arg
            elif arg.isdigit():
                page = int(arg)
            else:
                fish_name = arg
        result = leaderboard(group_id, fish_name=fish_name, size_order=size_order, fish_type=fish_type, page=page)
        yield event.plain_result(result)

    # ==================== 管理 ====================

    @filter.command("补偿鱼饵")
    async def cmd_compensate_lure(self, event: AstrMessageEvent):
        """管理员向目标用户补偿鱼饵：/补偿鱼饵 [目标user_id] [鱼饵] [数量]"""
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        target_user_id = args[1] if len(args) >= 2 else None
        lure_name = args[2] if len(args) >= 3 else None
        quantity = args[3] if len(args) >= 4 else 1
        result = compensate_lure(
            operator_id, group_id, target_user_id, lure_name, quantity
        )
        yield event.plain_result(result)

    @filter.command("修改天气")
    async def cmd_set_weather(self, event: AstrMessageEvent):
        """管理员修改当前天气：/修改天气 [天气类型]"""
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        weather_type = args[1] if len(args) >= 2 else None
        result = set_weather_command(operator_id, group_id, weather_type)
        yield event.plain_result(result)

    async def terminate(self):
        """插件销毁时的清理操作"""
        logger.info("红莲垂钓异闻 插件已卸载")
