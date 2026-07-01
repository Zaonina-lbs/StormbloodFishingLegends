import os
import shlex

from quart import request

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

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
    get_distinct_baits,
    get_all_fish_names,
    get_distinct_weathers,
    compensate,
    compensate_lure,
    my_info,
    set_weather_command,
    # Admin API
    admin_get_all_fish,
    admin_add_or_update_fish,
    admin_delete_fish,
    admin_get_all_lures,
    admin_add_or_update_lure,
    admin_delete_lure,
    admin_get_weather,
    admin_save_weather_types,
    admin_set_weather,
    admin_get_shop,
)

PLUGIN_NAME = "astrbot_plugin_StormbloodFishingLegends"


def parse_args(message_str: str):
    s = message_str.strip()
    if s.startswith("/"):
        s = s[1:]
    try:
        parts = shlex.split(s)
    except ValueError:
        parts = s.split()
    return parts


async def _rq_json():
    """Safely parse JSON request body."""
    import json

    try:
        raw = await request.get_data()
        if not raw:
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _json_resp(data, status=200):
    """Build a JSON dict response (Quart-compatible tuple)."""
    import json

    return (
        json.dumps(data, ensure_ascii=False),
        status,
        {"Content-Type": "application/json"},
    )


@register(
    "stormblood_fishing_legends",
    "Zaonina",
    "红莲垂钓异闻 - FF14群聊钓鱼小游戏",
    "v1.0.0",
)
class FishingPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._register_admin_apis(context)

    async def initialize(self):
        plugin_data_root = get_astrbot_plugin_data_path()
        self_data_dir = os.path.join(plugin_data_root, "stormblood_fishing_legends")
        os.makedirs(self_data_dir, exist_ok=True)
        init_engine(data_dir=self_data_dir, config=self.config)
        logger.info(f"红莲垂钓异闻 插件已加载，数据目录: {self_data_dir}")

    # ============ Admin API registration ============

    def _register_admin_apis(self, context: Context):
        P = PLUGIN_NAME
        # Fish
        context.register_web_api(
            f"/{P}/admin/fish/list", self._api_fish_list, ["GET"], "获取所有鱼"
        )
        context.register_web_api(
            f"/{P}/admin/fish/add", self._api_fish_add, ["POST"], "新增鱼类"
        )
        context.register_web_api(
            f"/{P}/admin/fish/update", self._api_fish_update, ["POST"], "更新鱼类"
        )
        context.register_web_api(
            f"/{P}/admin/fish/delete", self._api_fish_delete, ["POST"], "删除鱼类"
        )
        # Lure
        context.register_web_api(
            f"/{P}/admin/lure/list", self._api_lure_list, ["GET"], "获取所有鱼饵"
        )
        context.register_web_api(
            f"/{P}/admin/lure/add", self._api_lure_add, ["POST"], "新增鱼饵"
        )
        context.register_web_api(
            f"/{P}/admin/lure/update", self._api_lure_update, ["POST"], "更新鱼饵"
        )
        context.register_web_api(
            f"/{P}/admin/lure/delete", self._api_lure_delete, ["POST"], "删除鱼饵"
        )
        # Weather
        context.register_web_api(
            f"/{P}/admin/weather/list", self._api_weather_list, ["GET"], "获取天气"
        )
        context.register_web_api(
            f"/{P}/admin/weather/save-types",
            self._api_weather_save_types,
            ["POST"],
            "保存天气类型",
        )
        context.register_web_api(
            f"/{P}/admin/weather/set", self._api_weather_set, ["POST"], "设置天气"
        )
        # Shop
        context.register_web_api(
            f"/{P}/admin/shop/list", self._api_shop_list, ["GET"], "获取商店商品"
        )

    # ============ Admin API Handlers ============

    async def _api_fish_list(self):
        fish = admin_get_all_fish()
        return _json_resp({"fish": fish})

    async def _api_fish_add(self):
        data = await _rq_json()
        if not data.get("name"):
            return _json_resp({"message": "鱼名不能为空"}, 400)
        admin_add_or_update_fish(data)
        return _json_resp({"message": "添加成功"})

    async def _api_fish_update(self):
        data = await _rq_json()
        if not data.get("name"):
            return _json_resp({"message": "鱼名不能为空"}, 400)
        admin_add_or_update_fish(data)
        return _json_resp({"message": "更新成功"})

    async def _api_fish_delete(self):
        data = await _rq_json()
        name = data.get("name")
        if not name:
            return _json_resp({"message": "鱼名不能为空"}, 400)
        admin_delete_fish(name)
        return _json_resp({"message": f"已删除 {name}"})

    async def _api_lure_list(self):
        lures = admin_get_all_lures()
        return _json_resp({"lures": lures})

    async def _api_lure_add(self):
        data = await _rq_json()
        if not data.get("name"):
            return _json_resp({"message": "鱼饵名不能为空"}, 400)
        admin_add_or_update_lure(data)
        return _json_resp({"message": "添加成功"})

    async def _api_lure_update(self):
        data = await _rq_json()
        if not data.get("name"):
            return _json_resp({"message": "鱼饵名不能为空"}, 400)
        admin_add_or_update_lure(data)
        return _json_resp({"message": "更新成功"})

    async def _api_lure_delete(self):
        data = await _rq_json()
        name = data.get("name")
        if not name:
            return _json_resp({"message": "鱼饵名不能为空"}, 400)
        admin_delete_lure(name)
        return _json_resp({"message": f"已删除 {name}"})

    async def _api_weather_list(self):
        result = admin_get_weather()
        return _json_resp(result)

    async def _api_weather_save_types(self):
        data = await _rq_json()
        types = data.get("weather_types", [])
        if not types:
            return _json_resp({"message": "天气类型不能为空"}, 400)
        admin_save_weather_types(types)
        return _json_resp({"message": "天气类型已保存"})

    async def _api_weather_set(self):
        data = await _rq_json()
        wdate = data.get("date")
        slot = data.get("slot")
        weather = data.get("weather")
        if not all([wdate, slot is not None, weather]):
            return _json_resp({"message": "参数不完整"}, 400)
        ok = admin_set_weather(wdate, int(slot), weather)
        if not ok:
            return _json_resp({"message": "无效的天气类型"}, 400)
        return _json_resp({"message": f"已设置 {wdate} 天气为 {weather}"})

    async def _api_shop_list(self):
        items = admin_get_shop()
        return _json_resp({"items": items})

    # ============ 账号系统 ============

    @filter.command("钓鱼注册")
    async def cmd_register(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(register_user(user_id, group_id))

    @filter.command("签到")
    async def cmd_signin(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(sign_in(user_id, group_id))

    @filter.command("查看金币")
    async def cmd_check_gold(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(check_gold(user_id, group_id))

    @filter.command("钓鱼帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        yield event.plain_result(get_fish_help())

    @filter.command("鱼池版本")
    async def cmd_version(self, event: AstrMessageEvent):
        yield event.plain_result(get_fish_version())

    # ============ 钓鱼核心 ============

    @filter.command("使用鱼饵")
    async def cmd_set_bait(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        bait_name = args[1] if len(args) >= 2 else None
        yield event.plain_result(set_bait(user_id, group_id, bait_name))

    @filter.command("钓鱼")
    async def cmd_fishing(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        bait = args[1] if len(args) >= 2 else None
        fishing_ground = args[2] if len(args) >= 3 else None
        count = args[3] if len(args) >= 4 else None
        yield event.plain_result(
            go_fishing(
                user_id,
                group_id,
                bait_param=bait,
                fishing_ground=fishing_ground,
                count=count,
            )
        )

    @filter.command("查看天气")
    async def cmd_weather(self, event: AstrMessageEvent):
        yield event.plain_result(view_weather())

    # ============ 背包与鱼塘 ============

    @filter.command("查看背包")
    async def cmd_inventory(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(view_inventory(user_id, group_id))

    @filter.command("查看鱼塘")
    async def cmd_fish_pond(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        page = args[1] if len(args) >= 2 else 1
        yield event.plain_result(view_fish_pond(user_id, group_id, page=page))

    @filter.command("查看当前鱼饵")
    async def cmd_current_bait(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(get_current_bait(user_id, group_id))

    @filter.command("不使用鱼饵")
    async def cmd_clear_bait(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(clear_bait(user_id, group_id))

    @filter.command("当前鱼池")
    async def cmd_fish_pool(self, event: AstrMessageEvent):
        args = parse_args(event.message_str)
        bait_name = args[1] if len(args) >= 2 else None
        yield event.plain_result(view_fish_pool(bait_name=bait_name))

    @filter.command("锁定")
    async def cmd_lock(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        fish_id = args[1] if len(args) >= 2 else None
        yield event.plain_result(lock_fish(user_id, group_id, fish_id))

    @filter.command("解锁")
    async def cmd_unlock(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        fish_id = args[1] if len(args) >= 2 else None
        yield event.plain_result(unlock_fish(user_id, group_id, fish_id))

    # ============ 交易与出售 ============

    @filter.command("出售")
    async def cmd_sell(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        msg = event.message_str.strip()
        remain = msg
        if remain.startswith("/"):
            remain = remain[1:]
        parts = remain.split(maxsplit=1)
        arg = parts[1] if len(parts) >= 2 else ""
        if arg.lower().startswith("id"):
            result = sell_fish_by_id(user_id, group_id, arg[2:].strip())
        elif arg.isdigit():
            result = sell_fish_by_id(user_id, group_id, arg)
        else:
            result = sell_fish_by_name(user_id, group_id, arg)
        yield event.plain_result(result)

    @filter.command("全部出售")
    async def cmd_sell_all(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(sell_all_fish(user_id, group_id))

    # ============ 商店 ============

    @filter.command("商城")
    async def cmd_shop(self, event: AstrMessageEvent):
        yield event.plain_result(view_shop())

    @filter.command("购买道具")
    async def cmd_buy(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        item_id = args[1] if len(args) >= 2 else None
        amount = args[2] if len(args) >= 3 else 1
        yield event.plain_result(buy_item(user_id, group_id, item_id, amount))

    # ============ 氪金（管理员） ============

    @filter.command("氪金")
    async def cmd_krypton(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        gold = args[1] if len(args) >= 2 else None
        yield event.plain_result(krypton(user_id, group_id, gold))

    @filter.command("查看账单")
    async def cmd_krypton_log(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        yield event.plain_result(view_krypton_log(user_id, group_id))

    # ============ 管理员 ============

    @filter.command("补偿")
    async def cmd_compensate(self, event: AstrMessageEvent):
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        target_user_id = args[1] if len(args) >= 2 else None
        gold = args[2] if len(args) >= 3 else None
        yield event.plain_result(
            compensate(operator_id, group_id, target_user_id, gold)
        )

    @filter.command("我的信息")
    async def cmd_my_info(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        yield event.plain_result(my_info(user_id))

    # ============ 图鉴与排行榜 ============

    @filter.command("鱼群图鉴")
    async def cmd_handbook(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        param1 = args[1] if len(args) >= 2 else None
        param2 = args[2] if len(args) >= 3 else None
        regions = get_distinct_regions()
        grounds = get_distinct_grounds()
        baits = get_distinct_baits()
        fish_names = get_all_fish_names()
        fish_types = ["普通鱼", "鱼王", "鱼皇"]
        weathers = get_distinct_weathers()
        region = None
        fishing_ground = None
        fish_name = None
        bait = None
        fish_type = None
        weather = None
        page = 1
        force_fish = False
        force_bait = False

        # 检查前缀标记: "鱼：X" 或 "鱼饵：X"（支持半角:）
        for param in (param1, param2):
            if param is None:
                continue
            if param.startswith("鱼：") or param.startswith("鱼:"):
                force_fish = True
                stripped = param[2:].strip() if len(param) > 2 else ""
                if param1 == param:
                    param1 = stripped or None
                else:
                    param2 = stripped or None
            elif param.startswith("鱼饵：") or param.startswith("鱼饵:") or param.startswith("鱼饵："):
                force_bait = True
                if param[2:3] in ("：", ":"):
                    stripped = param[3:].strip() if len(param) > 3 else ""
                else:
                    stripped = param[2:].strip() if len(param) > 2 else ""
                if param1 == param:
                    param1 = stripped or None
                else:
                    param2 = stripped or None

        # 优先使用前缀标记，没有标记时按原有逻辑
        if param1 is None:
            pass
        elif param2 is not None:
            # 两个参数：优先识别为 [查询条件] [页码]
            if force_fish and param1:
                fish_name = param1
            elif force_bait and param1:
                bait = param1
            elif param1 in fish_names:
                fish_name = param1
            elif param1 in baits:
                bait = param1
            elif param1 in fish_types:
                fish_type = param1
            elif param1 in weathers:
                weather = param1
            elif param1 in regions:
                region = param1
            elif param1 in grounds:
                fishing_ground = param1
            try:
                page = int(param2)
            except (ValueError, TypeError):
                page = 1
        else:
            # 单个参数
            if force_fish and param1:
                fish_name = param1
            elif force_bait and param1:
                bait = param1
            else:
                try:
                    page = int(param1)
                except (ValueError, TypeError):
                    if param1 in fish_names:
                        fish_name = param1
                    elif param1 in baits:
                        bait = param1
                    elif param1 in fish_types:
                        fish_type = param1
                    elif param1 in weathers:
                        weather = param1
                    elif param1 in regions:
                        region = param1
                    elif param1 in grounds:
                        fishing_ground = param1
                    else:
                        # 不匹配任何已知类别，默认作为鱼名查询
                        fish_name = param1
                    page = 1
        if page < 1:
            page = 1
        yield event.plain_result(
            fish_handbook(
                user_id,
                group_id,
                page=page,
                region=region,
                fishing_ground=fishing_ground,
                fish_name=fish_name,
                bait=bait,
                fish_type=fish_type,
                weather=weather,
            )
        )

    @filter.command("钓鱼记录")
    async def cmd_fishing_log(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        page = args[1] if len(args) >= 2 else 1
        yield event.plain_result(fishing_log(user_id, group_id, page=page))

    @filter.command("排行榜")
    async def cmd_leaderboard(self, event: AstrMessageEvent):
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
        yield event.plain_result(
            leaderboard(
                group_id,
                fish_name=fish_name,
                size_order=size_order,
                fish_type=fish_type,
                page=page,
            )
        )

    # ============ 管理 ============

    @filter.command("补偿鱼饵")
    async def cmd_compensate_lure(self, event: AstrMessageEvent):
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        target_user_id = args[1] if len(args) >= 2 else None
        lure_name = args[2] if len(args) >= 3 else None
        quantity = args[3] if len(args) >= 4 else 1
        yield event.plain_result(
            compensate_lure(operator_id, group_id, target_user_id, lure_name, quantity)
        )

    @filter.command("修改天气")
    async def cmd_set_weather(self, event: AstrMessageEvent):
        if not event.is_admin():
            yield event.plain_result("❌ 仅管理员可使用此命令")
            return
        operator_id = event.get_sender_id()
        group_id = event.get_group_id()
        args = parse_args(event.message_str)
        weather_type = args[1] if len(args) >= 2 else None
        yield event.plain_result(
            set_weather_command(operator_id, group_id, weather_type)
        )

    async def terminate(self):
        logger.info("红莲垂钓异闻 插件已卸载")
