"""
游戏引擎模块 - 提供纯函数，供 AstrBot 直接调用
所有用户相关操作均需传入 group_id 以区分群聊
"""

import logging
import os
import random
import yaml
from datetime import date, timedelta

try:
    logger = logging.getLogger("astrbot")
except Exception:
    logger = logging.getLogger(__name__)

_config = None
_db = None
_data_dir = None


def _load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _reload_config():
    global _config
    _config = _load_config()


def _init_db():
    global _db
    from .database import get_db

    if _db is None:
        _db = get_db(data_dir=_data_dir)


def init_engine(data_dir=None, config=None):
    """初始化游戏引擎，设置数据目录并创建/导入数据。
    在 AstrBot 插件中调用此函数设置数据库路径。

    Args:
        data_dir: AstrBot 插件数据目录，数据库文件将存放在此目录下
        config: AstrBotConfig 对象（可选），从 AstrBot WebUI 配置传入。
                如果提供，将优先使用其值，未配置的项回退到 config.yaml 默认值
    """
    global _data_dir, _db, _config
    _data_dir = data_dir

    # 加载 config.yaml 作为基础配置（包含 lures、fishes 等数据列表）
    _config = _load_config()

    # 如果传入了 AstrBot 配置，将其值合并到 _config 中
    # AstrBotConfig 继承自 dict，直接用 dict 方式访问
    if config is not None:
        _merge_astrbot_config(config)
    from .database import init_db_with_path

    if data_dir:
        _db = init_db_with_path(None, data_dir=data_dir)
    else:
        from .database import get_db as _get_db

        _db = _get_db()

    # 创建数据库表结构
    _db.init_database()

    # 始终从 fish_data.yaml 同步鱼基础数据（删除重建，保证数据最新）
    fish_data_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fish_data.yaml"
    )
    fish_data = _config.get("fishes", [])
    if os.path.exists(fish_data_path):
        with open(fish_data_path, "r", encoding="utf-8") as f:
            fish_yaml = yaml.safe_load(f)
            if fish_yaml and "fishes" in fish_yaml:
                fish_data = fish_yaml["fishes"]
    if fish_data:
        _db.import_fish_data(fish_data)
        logger.info(f"已同步 {len(fish_data)} 条鱼基础数据到数据库")

    # 导入鱼饵数据（仅在空表时初始化，保护用户修改）
    lures = _config.get("lures", [])
    if lures:
        _db.import_lure_data(lures)
        logger.info(f"已导入 {len(lures)} 条鱼饵数据到数据库")

    # 加载持久化的天气类型配置（优先于 config.yaml）
    persisted_weather = _db.get_config("weather_types")
    if persisted_weather:
        _config["weather_types"] = persisted_weather
        logger.info(f"已加载持久化天气类型: {len(persisted_weather)} 种")

    # 生成天气数据
    from datetime import date as dt

    today = dt.today()
    for i in range(4):
        d = (today + timedelta(days=i)).isoformat()
        for slot in (0, 1):
            _db.generate_weather(d, slot)

    if is_debug():
        _debug(f"引擎初始化完成，数据库路径: {_db.db_path}")
        _debug(f"鱼种数: {len(_db.get_all_fish())}, 鱼饵数: {len(_db.get_all_lures())}")


def _merge_astrbot_config(astrbot_config):
    """将 AstrBot 传入的配置合并到全局 _config 中。
    AstrBotConfig 中的值优先，覆盖 config.yaml 中的对应项。
    lures 和 fishes 数据列表由 YAML 文件管理，不在此处合并。
    """
    global _config
    # 可覆盖的游戏参数键列表
    game_param_keys = [
        "debug",
        "initial_gold",
        "sign_gold_min",
        "sign_gold_max",
        "bait_prob_target",
        "bait_prob_king",
        "bait_prob_emperor",
        "size_prob_normal",
        "size_prob_big",
        "value_float_percent",
        "krypton_max",
        "page_size",
        "leaderboard_size",
        "version_string",
        "value_multiplier",
        "fishing_fail_rate",
        "default_bait_price",
        "fishing_cd",
        "weather_types",
    ]
    for key in game_param_keys:
        if key in astrbot_config:
            _config[key] = astrbot_config[key]


def is_debug():
    return _config.get("debug", False)


def _debug(msg):
    if is_debug():
        print(f"  [DEBUG] {msg}")


# ==================== 账号系统 ====================


def register_user(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    success, msg = _db.create_user(user_id, group_id)
    return f"✅ {msg}" if success else f"❌ {msg}"


def sign_in(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在，请先注册"
    last_sign = _db.get_last_sign_date(user_id, group_id)
    today = date.today().isoformat()
    if last_sign == today:
        return "❌ 今日已签到，请明天再来！"
    roll = random.random()
    gold_min = _config.get("sign_gold_min", 1500)
    gold_max = _config.get("sign_gold_max", 2000)
    if roll < 0.5:
        gold = random.randint(gold_min, gold_max)
        _db.update_user_gold(user_id, group_id, gold)
        _db.update_sign_date(user_id, group_id)
        return f"✅ 签到成功！获得 {gold} 金币"
    else:
        # 鱼饵奖励总价值约为金币奖励的2倍
        # 金币范围 avg ≈ 1500，2x ≈ 3000
        # 从可购买的鱼饵中随机选一个，按数量凑到目标价值附近
        shop_lures = [lure for lure in _db.get_shop_lures() if lure["price"] > 0]
        if not shop_lures:
            # 极端情况：没有可购鱼饵，则给金币
            gold = random.randint(gold_min, gold_max)
            _db.update_user_gold(user_id, group_id, gold)
            _db.update_sign_date(user_id, group_id)
            return f"✅ 签到成功！获得 {gold} 金币"
        # 目标价值：金币奖励范围 × 2
        target_value = random.randint(gold_min * 2, gold_max * 2)
        lure = random.choice(shop_lures)
        qty = max(1, target_value // lure["price"])
        _db.add_lure(user_id, group_id, lure["name"], qty)
        _db.update_sign_date(user_id, group_id)
        total_price = lure["price"] * qty
        return f"✅ 签到成功！获得 {lure['name']} x{qty}（价值 {total_price} G）"


def check_gold(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    return f"💰 {user_id} 的金币：{user['gold']} G"


# ==================== 天气系统 ====================


def view_weather():
    weather_data = _db.get_weather()
    lines = ["🌤️ 天气预报（每12小时变更，下午6点切换）"]
    for w in weather_data:
        lines.append(f"  {w['label']}：{w['weather']}")
    return "\n".join(lines)


def set_weather_command(operator_id, group_id, weather_type):
    """管理员修改当前天气"""
    if not operator_id:
        return "❌ 请提供 operator_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    if not weather_type:
        return "❌ 请提供天气类型"
    valid_weather = _config.get("weather_types", [])
    if weather_type not in valid_weather:
        return f"❌ 无效的天气类型！可选：{'/'.join(valid_weather)}"
    from datetime import date as dt

    today = dt.today().isoformat()
    slot = _db._current_slot()
    _db.set_weather(today, slot, weather_type)
    label = "白天" if slot == 0 else "晚上"
    return (
        f"✅ 管理员 {operator_id} 已将当前天气修改为：{weather_type}（{today} {label}）"
    )


# ==================== 钓鱼核心 ====================


def set_bait(user_id, group_id, bait_name):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    if not bait_name:
        return "❌ 请指定鱼饵名称"
    lure = _db.get_lure_by_name(bait_name)
    if not lure:
        return f"❌ 鱼饵 {bait_name} 不存在"
    if bait_name != "万能鱼饵" and not _db.check_lure(user_id, group_id, bait_name):
        inv = _db.get_inventory(user_id, group_id)
        owned = [i["lure_name"] for i in inv] if inv else []
        return f"❌ 你没有 {bait_name}，当前拥有：{', '.join(owned) if owned else '无'}"
    _db.set_default_bait(user_id, group_id, bait_name)
    return f"✅ 已将默认鱼饵设置为 {bait_name}"


def _get_lure_sellable(bait_name):
    """检查鱼饵是否为不可出售（卖不掉的）鱼饵。不可出售的鱼饵不限制CD
    注意：万能鱼饵虽然是不可出售的，但仍然需要CD限制"""
    if bait_name == "万能鱼饵":
        return True  # 万能鱼饵也需要CD
    lure = _db.get_lure_by_name(bait_name)
    if lure:
        return bool(lure.get("sellable", 0))
    return True  # 未知鱼饵按可出售处理


def _check_fishing_cd(user_id, group_id, count):
    """检查钓鱼CD，返回 (can_fish, message)
    CD 基于上次钓鱼的实际次数计算，而非本次请求次数。
    例如：上次钓鱼10次（30分钟CD），则本次钓鱼必须等30分钟后。
    can_fish: True=可以钓鱼, False=CD中
    message: 提示信息
    """
    cd_config = _config.get("fishing_cd", {})
    if not cd_config.get("enabled", True):
        return True, ""
    last_time_str = _db.get_last_fishing_time(user_id, group_id)
    if not last_time_str:
        return True, ""
    # 获取上次钓鱼的次数，用于计算正确的CD时长
    last_count = _db.get_last_fishing_count(user_id, group_id)
    if last_count is None:
        last_count = 1
    from datetime import datetime

    try:
        last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return True, ""
    cooldown_minutes = cd_config.get("cooldown_minutes", 3)
    total_cd = cooldown_minutes * last_count
    cd_end = last_time + timedelta(minutes=total_cd)
    now = datetime.now()
    if now < cd_end:
        remain_seconds = int((cd_end - now).total_seconds())
        remain_minutes = remain_seconds // 60
        remain_secs = remain_seconds % 60
        if remain_minutes > 0:
            return (
                False,
                f"⏳ 钓鱼CD中！还需等待 {remain_minutes}分{remain_secs}秒（上次钓鱼 {last_count} 次，CD: {cooldown_minutes}分钟 × {last_count} = {total_cd}分钟）",
            )
        else:
            return (
                False,
                f"⏳ 钓鱼CD中！还需等待 {remain_secs}秒（上次钓鱼 {last_count} 次）",
            )
    return True, ""


def go_fishing(user_id, group_id, bait_param=None, fishing_ground=None, count=1):
    """执行钓鱼，支持批量 count 次
    参数顺序: user_id, group_id, bait, fishing_ground, count
    智能识别: 如果 fishing_ground 是数字，自动识别为 count
    """
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在，请先注册"

    # 智能识别: 如果 bait_param 是纯数字，当作 count 处理
    if bait_param is not None:
        try:
            int(bait_param)
            count = bait_param
            bait_param = None
        except (ValueError, TypeError):
            pass

    # 智能识别: 如果 fishing_ground 是数字，当作 count 处理
    if fishing_ground is not None:
        try:
            int(fishing_ground)
            count = fishing_ground
            fishing_ground = None
        except (ValueError, TypeError):
            pass

    try:
        count = int(count) if count else 1
    except (ValueError, TypeError):
        count = 1
    if count < 1:
        count = 1
    if count > 10:
        return "❌ 单次最多钓鱼10次"

    effective_bait = bait_param or user.get("default_bait") or "万能鱼饵"
    # 检查鱼饵/金币是否充足
    if effective_bait == "万能鱼饵":
        bait_price = _config.get("default_bait_price", 100)
        total_cost = bait_price * count
        if user["gold"] < total_cost:
            return f"❌ 金币不足！需要 {total_cost} G，当前 {user['gold']} G"
    else:
        if not _db.check_lure(user_id, group_id, effective_bait):
            return f"❌ 背包中没有 {effective_bait}"
        inv = _db.get_inventory(user_id, group_id)
        owned = sum(i["quantity"] for i in inv if i["lure_name"] == effective_bait)
        if owned < count:
            return f"❌ {effective_bait} 不足！需要 {count} 个，拥有 {owned} 个"

    # 钓鱼CD检查：仅对可出售的鱼饵进行CD限制，不可出售的鱼饵（如红玉虾等）不限制CD
    lure_sellable = _get_lure_sellable(effective_bait)
    if lure_sellable:
        can_fish, cd_msg = _check_fishing_cd(user_id, group_id, count)
        if not can_fish:
            return cd_msg

    lines = [f"🎣 当前使用鱼饵：{effective_bait}"]
    if count > 1:
        lines.append(f"  连续钓鱼 {count} 次")
    results = []
    total_value = 0
    fish_counts = {}

    for i in range(count):
        if count > 1:
            _debug(f"--- 第 {i + 1}/{count} 次 ---")
        result = _do_single_fish(
            user_id, group_id, effective_bait, fishing_ground, i == 0
        )
        if result is None:
            return "❌ 当前条件下没有可钓的鱼"
        if result.startswith("❌"):
            if count == 1:
                return result
            results.append(f"  [{i + 1}] {result}")
            continue
        results.append(f"  [{i + 1}] {result}")
        # 统计
        parts = result.split("|")
        if len(parts) >= 2:
            try:
                val_str = parts[1].strip().split()[0]
                total_value += int(val_str)
            except (ValueError, IndexError):
                pass
        for word in result.split():
            if "鱼王" in word or "鱼皇" in word or "普通鱼" in word:
                # extract fish name
                name = (
                    result.split("]：")[1].split("\n")[0]
                    if "]：" in result
                    else "unknown"
                )
                fish_counts[name] = fish_counts.get(name, 0) + 1

    # 钓鱼完成后更新最后钓鱼时间和次数（仅对可出售鱼饵记录CD）
    if lure_sellable:
        _db.update_fishing_time(user_id, group_id, count)

    if count == 1:
        single_result = (
            results[0][7:]
            if results and results[0].startswith("  [1] ")
            else (results[0] if results else "❌")
        )
        return f"🎣 当前使用鱼饵：{effective_bait}\n{single_result}"

    # 汇总
    lines = [f"🎣 当前使用鱼饵：{effective_bait}"]
    lines.append(f"  连续钓鱼 {count} 次完成！")
    for r in results:
        lines.append(r)
    lines.append(f"\n📊 总计价值：{total_value} G")
    if fish_counts:
        unique_fish = {k: v for k, v in fish_counts.items() if k != "unknown"}
        if unique_fish:
            fish_summary = " | ".join(
                f"{k}x{v}" for k, v in sorted(unique_fish.items())
            )
            lines.append(f"🐟 鱼获：{fish_summary}")
    return "\n".join(lines)


def _do_single_fish(user_id, group_id, effective_bait, fishing_ground, show_debug=True):
    """单次钓鱼核心逻辑，返回格式化的单行结果字符串"""
    weather = _db.get_today_weather()
    weather_type = weather["weather"]
    if show_debug:
        _debug(f"当前天气: {weather_type}")

    # 筛选可钓鱼种
    if effective_bait == "万能鱼饵":
        if fishing_ground:
            candidate_fish = _db.get_fish_by_ground(fishing_ground, weather_type)
            candidate_fish = [f for f in candidate_fish if f["fish_type"] == "普通鱼"]
        else:
            all_fish = _db.get_all_fish()
            candidate_fish = []
            for f in all_fish:
                if f["fish_type"] != "普通鱼":
                    continue
                if f["weather"] == "" or weather_type in f.get("weather", "").split(
                    "/"
                ):
                    candidate_fish.append(f)
            if not candidate_fish:
                candidate_fish = [f for f in all_fish if f["fish_type"] == "普通鱼"]
    else:
        if fishing_ground:
            all_in_ground = _db.get_fish_by_ground(fishing_ground, weather_type)
            candidate_fish = []
            for f in all_in_ground:
                fish_bait = f.get("bait", "")
                if fish_bait == "" or fish_bait == effective_bait:
                    candidate_fish.append(f)
                elif "/" in fish_bait:
                    # 多鱼饵支持：bait 字段可能为 "蓝矶沙蚕/苦尔鳗"
                    bait_parts = fish_bait.split("/")
                    if effective_bait in bait_parts:
                        candidate_fish.append(f)
        else:
            candidate_fish = _db.get_fish_by_bait(effective_bait, weather_type)

    if not candidate_fish:
        return None

    if show_debug:
        _debug(f"鱼池共 {len(candidate_fish)} 条鱼")

    # 先消耗鱼饵（无论是否上钩，鱼饵都已使用）
    if effective_bait == "万能鱼饵":
        _db.update_user_gold(user_id, group_id, -_config.get("default_bait_price", 100))
    else:
        _db.remove_lure(user_id, group_id, effective_bait, 1)

    # 按类型分组
    normal_fish = [f for f in candidate_fish if f["fish_type"] == "普通鱼"]
    king_fish = [f for f in candidate_fish if f["fish_type"] == "鱼王"]
    emperor_fish = [f for f in candidate_fish if f["fish_type"] == "鱼皇"]
    if show_debug:
        _debug(
            f"普通鱼:{len(normal_fish)} 鱼王:{len(king_fish)} 鱼皇:{len(emperor_fish)}"
        )

    # 概率判定
    if effective_bait == "万能鱼饵":
        if not normal_fish:
            return None
        target_pool = normal_fish
    else:
        prob_target = _config.get("bait_prob_target", 25)
        prob_king = _config.get("bait_prob_king", 2)
        prob_emperor = _config.get("bait_prob_emperor", 0.2)
        # 配置中的概率为最终实际概率（已含脱钩），反算为引擎判定基准值
        # 实际概率 = 判定基准 × (1 - 脱钩率)
        fail_rate_config = _config.get("fishing_fail_rate", 0) / 100.0
        if fail_rate_config < 1:
            prob_target = prob_target / (1 - fail_rate_config)
            prob_king = prob_king / (1 - fail_rate_config)
            prob_emperor = prob_emperor / (1 - fail_rate_config)
        # 当鱼皇使用的鱼饵本身就是某种鱼时，根据鱼饵类型提升鱼皇概率
        # 设计目标：无论哪种链式路径，最终期望都是约200杆（CD有效杆）一条鱼皇
        # 鱼王作饵 → 鱼皇概率提升至目标鱼级别（25%），约4条鱼王=1条鱼皇
        # 普通鱼作饵 → 鱼皇概率提升至鱼王级别（2%），约50条普通鱼=1条鱼皇
        prob_emperor_effective = prob_emperor
        emperor_boosted_to_target = False  # 是否已提升至 prob_target 级别
        if emperor_fish:
            bait_fish = _db.get_fish_by_name(effective_bait)
            if bait_fish and bait_fish[0].get("fish_type") == "鱼王":
                prob_emperor_effective = prob_target
                emperor_boosted_to_target = True
                if show_debug:
                    _debug(
                        f"鱼皇饵为鱼王({effective_bait})，鱼皇概率提升至 {prob_emperor_effective}%"
                    )
            elif bait_fish and bait_fish[0].get("fish_type") == "普通鱼":
                prob_emperor_effective = prob_king
                if show_debug:
                    _debug(
                        f"鱼皇饵为普通鱼({effective_bait})，鱼皇概率提升至 {prob_emperor_effective}%"
                    )

        # 当鱼池中没有普通鱼时，将普通鱼的 roll 区间分配给稀有鱼
        # 注意：仅当鱼皇和鱼王同时存在时才进行比例重分配
        # 单独只有鱼王或鱼皇时不再额外分配，保持基础概率，避免稀有鱼泛滥
        if not normal_fish:
            if emperor_fish and king_fish:
                total_rare = prob_emperor_effective + prob_king
                if emperor_boosted_to_target:
                    # 鱼皇已占 prob_target，只需为鱼王分配 prob_target 空间
                    prob_king += prob_target
                    if show_debug:
                        _debug(
                            f"无普通鱼，概率重分配：鱼皇 {prob_emperor_effective:.1f}% 鱼王 {prob_king:.1f}%"
                        )
                elif total_rare > 0:
                    scale = (total_rare + prob_target) / total_rare
                    prob_emperor_effective *= scale
                    prob_king *= scale
                    if show_debug:
                        _debug(
                            f"无普通鱼，概率重分配：鱼皇 {prob_emperor_effective:.1f}% 鱼王 {prob_king:.1f}%"
                        )
            # 单独只有鱼皇或鱼王：不再将 prob_target 分配给单一稀有鱼
            # 维持基础概率设计，避免指定钓场时稀有鱼泛滥

        roll = random.uniform(0, 100)
        if show_debug:
            _debug(f"概率判定 roll={roll:.1f}")
        if emperor_fish and roll < prob_emperor_effective:
            target_pool = emperor_fish
        elif king_fish and roll < prob_emperor_effective + prob_king:
            target_pool = king_fish
        elif normal_fish and roll < prob_emperor_effective + prob_king + prob_target:
            target_pool = normal_fish
        else:
            # 根据配置的概率区间判定，如果没有匹配则视为未上钩
            if normal_fish:
                target_pool = normal_fish
            else:
                return "💨 没有鱼上钩..."

    chosen_fish = random.choice(target_pool)

    # 钓鱼失败率检查（脱钩概率）
    fail_rate = _config.get("fishing_fail_rate", 0) / 100.0
    if fail_rate > 0 and random.random() < fail_rate:
        if show_debug:
            _debug(f"脱钩判定: 命中 {fail_rate * 100:.0f}% 失败率")
        return "💨 鱼脱钩了！"

    # 尺寸生成
    size, is_big = _generate_size(
        chosen_fish["min_size"], chosen_fish["min_big_size"], chosen_fish["max_size"]
    )
    if show_debug:
        _debug(f"尺寸: {size:.1f}cm {'大鱼' if is_big else '普通'}")

    # 价值计算
    value = _calculate_value(chosen_fish, size)

    # 自动锁定：鱼王鱼皇，以及可作为鱼饵的鱼
    is_lure_fish = _db.is_fish_a_lure(chosen_fish["name"])
    auto_locked = (
        1 if chosen_fish["fish_type"] in ("鱼王", "鱼皇") or is_lure_fish else 0
    )

    # 保存
    _db.add_caught(
        user_id,
        group_id,
        chosen_fish["name"],
        chosen_fish["fish_type"],
        size,
        is_big,
        value,
        auto_locked,
    )

    # 如果该鱼也是鱼饵，自动加入背包
    if is_lure_fish:
        _db.add_lure(user_id, group_id, chosen_fish["name"], 1)
    _db.add_log(
        user_id,
        group_id,
        chosen_fish["name"],
        chosen_fish["fish_type"],
        size,
        is_big,
        value,
        effective_bait,
        chosen_fish["fishing_ground"],
        weather_type,
    )

    big_label = "🐠" if is_big else ""
    lock_label = "🔒" if auto_locked else ""
    return f"{big_label} {chosen_fish['name']} ({chosen_fish['fish_type']}) {size:.1f}cm | {int(value)} G {lock_label}"


def _generate_size(min_size, min_big_size, max_size):
    prob_normal = _config.get("size_prob_normal", 75) / 100.0
    if random.random() < prob_normal:
        t = random.betavariate(2.0, 3.0)
        size = min_size + t * (min_big_size - min_size)
        is_big = 0
    else:
        t = random.betavariate(2.0, 2.5)
        size = min_big_size + t * (max_size - min_big_size)
        is_big = 1
    size = max(min_size, min(size, max_size))
    return round(size, 1), is_big


def _calculate_value(fish, size):
    base_value = fish.get("base_value", 50)
    if fish["max_size"] > fish["min_size"]:
        size_ratio = (size - fish["min_size"]) / (fish["max_size"] - fish["min_size"])
    else:
        size_ratio = 0.5
    float_pct = _config.get("value_float_percent", 20) / 100.0
    multiplier = _config.get("value_multiplier", 1.0)
    value = base_value * (1 + (size_ratio - 0.5) * 2 * float_pct) * multiplier
    return round(max(1, value))


def get_current_bait(user_id, group_id):
    """查看当前默认鱼饵"""
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    bait = user.get("default_bait") or "万能鱼饵"
    return f"🎣 {user_id} 当前默认鱼饵：{bait}"


def clear_bait(user_id, group_id):
    """清除默认鱼饵，恢复万能鱼饵"""
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    _db.set_default_bait(user_id, group_id, "万能鱼饵")
    return "✅ 已恢复使用万能鱼饵"


def view_fish_pool(bait_name=None):
    """查看当前鱼池（当前天气下可钓的鱼），天气限定鱼显示在最前面，然后按鱼皇>鱼王>普通鱼排序
    Args:
        bait_name: 可选鱼饵名称，用于筛选该鱼饵在当前天气能钓到的鱼
    """
    weather = _db.get_today_weather()
    weather_type = weather["weather"]
    all_fish = _db.get_all_fish()
    pool = []
    for f in all_fish:
        if f["weather"] == "" or weather_type in f.get("weather", "").split("/"):
            # 如果指定了鱼饵，进一步按鱼饵筛选
            if bait_name:
                fish_bait = f.get("bait", "")
                if fish_bait == "" or fish_bait == bait_name:
                    pass  # 命中：无限制或精确匹配
                elif "/" in fish_bait:
                    bait_parts = fish_bait.split("/")
                    if bait_name in bait_parts:
                        pass  # 命中：多鱼饵匹配
                    else:
                        continue  # 不匹配
                else:
                    continue  # 不匹配
            pool.append(f)
    if not pool:
        return "🐟 当前鱼池为空"
    # 分离天气限定鱼和非限定鱼
    weather_locked = [f for f in pool if f.get("weather", "") != ""]
    no_weather = [f for f in pool if f.get("weather", "") == ""]
    # 按鱼皇>鱼王>普通鱼排序
    type_order = {"鱼皇": 0, "鱼王": 1, "普通鱼": 2}
    weather_locked.sort(key=lambda x: (type_order.get(x["fish_type"], 99), x["name"]))
    no_weather.sort(key=lambda x: (type_order.get(x["fish_type"], 99), x["name"]))
    lines = [f"🐟 当前鱼池（天气：{weather_type}，共 {len(pool)} 种）"]
    current_type = None
    if weather_locked:
        lines.append(f"\n  【天气限定】（{len(weather_locked)} 种）")
        for f in weather_locked:
            if f["fish_type"] != current_type:
                current_type = f["fish_type"]
                lines.append(f"    ── {current_type} ──")
            bait_str = f.get("bait", "") or "通杀"
            weather_str = f.get("weather", "")
            lines.append(f"    {f['name']} - {bait_str} 🌤️{weather_str}")
    current_type = None
    if no_weather:
        lines.append(f"\n  【通用】（{len(no_weather)} 种）")
        for f in no_weather:
            if f["fish_type"] != current_type:
                current_type = f["fish_type"]
                lines.append(f"    ── {current_type} ──")
            bait_str = f.get("bait", "") or "通杀"
            lines.append(f"    {f['name']} - {bait_str}")
    return "\n".join(lines)


def get_fish_help():
    return (
        "📋 FF14 钓鱼游戏命令\n"
        "\n【账号】\n"
        "  /钓鱼注册\n"
        "  /签到\n"
        "  /查看金币\n"
        "  /我的信息\n"
        "  /钓鱼帮助\n"
        "  /鱼池版本\n"
        "\n【钓鱼】\n"
        "  /钓鱼 [鱼饵] [钓场] [次数]\n"
        "  /使用鱼饵 [饵]\n"
        "  /查看当前鱼饵\n"
        "  /不使用鱼饵\n"
        "  /查看天气\n"
        "  /当前鱼池 [鱼饵]\n"
        "\n【背包】\n"
        "  /查看背包\n"
        "  /查看鱼塘 [页码]\n"
        "\n【管理】\n"
        "  /锁定 [id]\n"
        "  /解锁 [id]\n"
        "  /出售 [鱼名]\n"
        "  /出售 [id]\n"
        "  /全部出售\n"
        "\n【商店】\n"
        "  /商城\n"
        "  /购买道具 [id] [数量]\n"
        "  /氪金 [金币]\n"
        "  /查看账单\n"
        "\n【图鉴】\n"
        "  /鱼群图鉴 [鱼名]  - 查询指定鱼的信息\n"
        "  /鱼群图鉴 鱼：[鱼名]  - 强制作为鱼查询（解决鱼/鱼饵重名）\n"
        "  /鱼群图鉴 [鱼饵名]  - 查询使用该鱼饵的鱼\n"
        "  /鱼群图鉴 鱼饵：[鱼饵名]  - 强制作为鱼饵查询\n"
        "  /鱼群图鉴 [鱼的种类]  - 按种类查询（普通鱼/鱼王/鱼皇）\n"
        "  /鱼群图鉴 [天气]  - 按天气查询（如：小雨）\n"
        "  /鱼群图鉴 [地区|钓场|页码] [页码]\n"
        "  /未获取 [地区|钓场] [天气] [鱼饵] [页码]  - 查询未钓到的鱼\n"
        "  /钓鱼记录 [页]\n"
        "  /排行榜 [鱼名] [大/小] [鱼的种类] [页码]\n"
        "\n【管理员】\n"
        "  /修改天气 [天气类型]\n"
        "  /补偿鱼饵 [目标user_id] [鱼饵] [数量]\n"
        "  /补偿 [目标user_id] [金币]\n"
        "\n【WebUI管理面板】\n"
        "  在 AstrBot WebUI 插件详情页打开「admin」页面\n"
        "  可直接管理鱼类数据、鱼饵数据、天气信息和商店配置\n"
        "  所有修改实时生效，无需重启或热更新"
    )


def get_fish_version():
    return f"🐟 鱼池版本：{_config.get('version_string', 'FF14 4.0-4.X')}"


# ==================== 背包与鱼塘 ====================


def view_inventory(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    inventory = _db.get_inventory(user_id, group_id)
    if not inventory:
        return f"💰 金币：{user['gold']} G\n🎒 背包为空"
    lines = [f"🎒 {user_id} 的背包", f"  💰 金币：{user['gold']} G"]
    for item in inventory:
        lines.append(f"  📦 {item['lure_name']} x{item['quantity']}")
    return "\n".join(lines)


def view_fish_pond(user_id, group_id, page=1):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    page_size = 10
    fish_list, total = _db.get_pond(user_id, group_id, page=page, page_size=page_size)
    if not fish_list:
        return "🐟 鱼塘为空"
    total_pages = (total + page_size - 1) // page_size
    if page > total_pages:
        page = total_pages
        fish_list, _ = _db.get_pond(user_id, group_id, page=page, page_size=page_size)
    lines = [f"🐟 {user_id} 的鱼塘（第 {page}/{total_pages} 页，共 {total} 条）"]
    for f in fish_list:
        lock_icon = "🔒" if f["locked"] else ""
        big_icon = "🐠" if f["is_big"] else "🐟"
        lines.append(
            f"  [{f['id']}] {big_icon} {f['fish_name']} ({f['fish_type']}) {f['size']:.1f}cm 价值{int(f['value'])}G {lock_icon} 📅{f['caught_date']}"
        )
    if page < total_pages:
        lines.append(f"\n  下一页：/查看鱼塘 {page + 1}")
    return "\n".join(lines)


def lock_fish(user_id, group_id, fish_id):
    """锁定鱼，支持批量锁定: /锁定 1,2,3"""
    if not fish_id:
        return "❌ 请提供 fish_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    # 解析逗号分隔的ID列表
    raw_ids = str(fish_id).replace("，", ",").split(",")
    id_list = []
    for rid in raw_ids:
        rid = rid.strip()
        try:
            id_list.append(int(rid))
        except (ValueError, TypeError):
            pass
    if not id_list:
        return "❌ fish_id 必须为数字"
    # 批量处理
    locked = []
    failed = []
    for fid in id_list:
        fish = _db.get_caught_by_id(fid, user_id, group_id)
        if not fish:
            failed.append(str(fid))
        elif fish["locked"]:
            # 已锁定，但不报失败
            locked.append(fish["fish_name"])
        else:
            _db.lock_fish(fid, user_id, group_id)
            locked.append(fish["fish_name"])
    lines = []
    if locked:
        lines.append(f"🔒 已锁定：{', '.join(locked)}")
    if failed:
        lines.append(f"❌ 锁定失败：{', '.join(failed)}（ID不存在）")
    return "\n".join(lines)


def unlock_fish(user_id, group_id, fish_id):
    """解锁鱼，支持批量解锁: /解锁 1,2,3"""
    if not fish_id:
        return "❌ 请提供 fish_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    # 解析逗号分隔的ID列表
    raw_ids = str(fish_id).replace("，", ",").split(",")
    id_list = []
    for rid in raw_ids:
        rid = rid.strip()
        try:
            id_list.append(int(rid))
        except (ValueError, TypeError):
            pass
    if not id_list:
        return "❌ fish_id 必须为数字"
    # 批量处理
    unlocked = []
    failed = []
    for fid in id_list:
        fish = _db.get_caught_by_id(fid, user_id, group_id)
        if not fish:
            failed.append(str(fid))
        elif not fish["locked"]:
            # 已解锁，但不报失败
            unlocked.append(fish["fish_name"])
        else:
            _db.unlock_fish(fid, user_id, group_id)
            unlocked.append(fish["fish_name"])
    lines = []
    if unlocked:
        lines.append(f"🔓 已解锁：{', '.join(unlocked)}")
    if failed:
        lines.append(f"❌ 解锁失败：{', '.join(failed)}（ID不存在）")
    return "\n".join(lines)


# ==================== 交易与出售 ====================


def sell_fish_by_name(user_id, group_id, fish_name):
    if not user_id or not fish_name:
        return "❌ 请提供 fish_name"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    count, total = _db.sell_by_name(user_id, group_id, fish_name)
    if count == 0:
        return f"❌ 没有可出售的 {fish_name}"
    return f"✅ 已出售 {count} 条 {fish_name}，获得 {int(total)} G"


def sell_fish_by_id(user_id, group_id, fish_id):
    if not user_id or not fish_id:
        return "❌ 请提供 fish_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    try:
        fish_id = int(fish_id)
    except (ValueError, TypeError):
        return "❌ fish_id 必须为数字"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    result, info = _db.sell_by_id(user_id, group_id, fish_id)
    if result is None:
        return f"❌ {info}"
    return f"✅ 已出售 {info}，获得 {int(result)} G"


def sell_all_fish(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    count, total = _db.sell_all(user_id, group_id)
    if count == 0:
        return "❌ 没有可出售的鱼"
    return f"✅ 已出售 {count} 条鱼，获得 {int(total)} G"


# ==================== 商店 ====================


def view_shop():
    lures = _db.get_shop_lures()
    if not lures:
        return "🏪 商城暂无商品"
    lines = ["🏪 商城 - 可购买的鱼饵"]
    for lure in lures:
        lines.append(f"  [{lure['id']}] {lure['name']} - {lure['price']} G")
    lines.append("\n使用 /购买道具 [item_id] [数量] 购买")
    return "\n".join(lines)


def buy_item(user_id, group_id, item_id, amount=1):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    if not item_id:
        return "❌ 请提供 item_id"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    try:
        amount = int(amount) if amount else 1
    except (ValueError, TypeError):
        amount = 1
    if amount <= 0:
        return "❌ 购买数量必须大于0"
    lures = _db.get_shop_lures()
    target = None
    for lure in lures:
        if str(lure["id"]) == str(item_id) or lure["name"] == str(item_id):
            target = lure
            break
    if not target:
        return "❌ 未找到商品，请使用 /商城 查看"
    total_price = target["price"] * amount
    if user["gold"] < total_price:
        return f"❌ 金币不足！需要 {total_price} G，当前 {user['gold']} G"
    _db.update_user_gold(user_id, group_id, -total_price)
    _db.add_lure(user_id, group_id, target["name"], amount)
    return f"✅ 购买成功！{target['name']} x{amount}，花费 {total_price} G"


# ==================== 氪金（管理员） ====================


def krypton(user_id, group_id, gold):
    if not user_id or gold is None:
        return "❌ 请提供金币数量"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    try:
        gold = int(gold)
    except (ValueError, TypeError):
        return "❌ 金币数量必须为整数"
    if gold <= 0:
        return "❌ 金币数量必须大于0"
    max_gold = _config.get("krypton_max", 1000)
    if gold > max_gold:
        return f"❌ 单次氪金上限为 {max_gold} G"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    _db.update_user_gold(user_id, group_id, gold)
    _db.add_krypton(user_id, group_id, gold)
    return f"✅ 已为用户 {user_id} 添加 {gold} G"


def view_krypton_log(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    records = _db.get_krypton_log(user_id, group_id)
    if not records:
        return f"💳 {user_id} 暂无氪金记录"
    lines = [f"💳 {user_id} 的氪金账单"]
    for r in records[:20]:
        lines.append(f"  {r['created_at']} : +{r['amount']} G")
    return "\n".join(lines)


def compensate(operator_id, group_id, target_user_id, gold):
    """管理员向目标用户补偿金币"""
    if not operator_id:
        return "❌ 请提供 operator_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    if not target_user_id:
        return "❌ 请提供目标用户的 user_id"
    if gold is None:
        return "❌ 请提供金币数量"
    try:
        gold = int(gold)
    except (ValueError, TypeError):
        return "❌ 金币数量必须为整数"
    if gold <= 0:
        return "❌ 金币数量必须大于0"
    target = _db.get_user(target_user_id, group_id)
    if not target:
        return f"❌ 用户 {target_user_id} 在本群不存在"
    _db.update_user_gold(target_user_id, group_id, gold)
    _db.add_krypton(target_user_id, group_id, gold)
    return f"✅ 管理员 {operator_id} 已向用户 {target_user_id} 补偿 {gold} G"


def compensate_lure(operator_id, group_id, target_user_id, lure_name, quantity):
    """管理员向目标用户补偿鱼饵"""
    if not operator_id:
        return "❌ 请提供 operator_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    if not target_user_id:
        return "❌ 请提供目标用户的 user_id"
    if not lure_name:
        return "❌ 请提供鱼饵名称"
    lure = _db.get_lure_by_name(lure_name)
    if not lure:
        return f"❌ 鱼饵 {lure_name} 不存在"
    try:
        qty = int(quantity) if quantity else 1
    except (ValueError, TypeError):
        return "❌ 数量必须为整数"
    if qty <= 0:
        return "❌ 数量必须大于0"
    if qty > 999:
        return "❌ 单次补偿上限为 999"
    target = _db.get_user(target_user_id, group_id)
    if not target:
        return f"❌ 用户 {target_user_id} 在本群不存在"
    _db.add_lure(target_user_id, group_id, lure_name, qty)
    return f"✅ 管理员 {operator_id} 已向用户 {target_user_id} 补偿 {lure_name} x{qty}"


def my_info(user_id):
    """返回用户自己的 user_id"""
    if not user_id:
        return "❌ 无法获取用户信息"
    return f"📋 你的 user_id：{user_id}"


# ==================== 图鉴与排行榜 ====================


def get_distinct_regions():
    """获取所有不重复的区域列表"""
    return _db.get_distinct_regions()


def get_distinct_grounds():
    """获取所有不重复的钓场列表"""
    return _db.get_distinct_grounds()


def get_distinct_baits():
    """获取所有不重复的鱼饵列表"""
    return _db.get_distinct_baits()


def get_all_fish_names():
    """获取所有鱼名列表"""
    return _db.get_all_fish_names()


def get_distinct_weathers():
    """获取所有不重复的天气列表"""
    return _db.get_distinct_weathers()


def fish_handbook(
    user_id,
    group_id,
    page=1,
    region=None,
    fishing_ground=None,
    fish_name=None,
    bait=None,
    fish_type=None,
    weather=None,
):
    """鱼群图鉴 - 分页显示，每页10条
    参数: user_id, group_id, page(默认1), region(可选地区筛选), fishing_ground(可选钓场筛选),
          fish_name(可选鱼名精确查询), bait(可选鱼饵名查询), fish_type(可选鱼的种类查询: 普通鱼/鱼王/鱼皇)
    用法: /鱼群图鉴 [鱼名]  - 查询指定鱼的信息
          /鱼群图鉴 [鱼饵名]  - 查询使用该鱼饵的鱼群信息
          /鱼群图鉴 [鱼的种类]  - 查询指定种类的鱼群信息
          /鱼群图鉴 [地区|钓场|页码] [页码]  - 按地区/钓场/页码筛选
    """
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"

    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1

    handbook = _db.get_handbook(
        user_id,
        group_id,
        region=region,
        fishing_ground=fishing_ground,
        fish_name=fish_name,
        bait=bait,
        fish_type=fish_type,
        weather=weather,
    )
    if not handbook:
        return "📖 图鉴数据为空"

    page_size = 10
    total = len(handbook)
    total_pages = (total + page_size - 1) // page_size
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    page_data = handbook[start : start + page_size]

    # 构建图鉴标题
    title_parts = [f"📖 {user_id} 的鱼群图鉴"]
    if fish_name:
        title_parts.append(f" [鱼名: {fish_name}]")
    if bait:
        title_parts.append(f" [鱼饵: {bait}]")
    if fish_type:
        title_parts.append(f" [种类: {fish_type}]")
    if weather:
        title_parts.append(f" [天气: {weather}]")
    if region:
        title_parts.append(f" [地区: {region}]")
    if fishing_ground:
        title_parts.append(f" [钓场: {fishing_ground}]")
    title_parts.append(f" （第 {page}/{total_pages} 页，共 {total} 种）")
    lines = ["".join(title_parts)]

    # 按区域+钓场分组展示
    current_region = None
    current_ground = None
    for fish in page_data:
        mark = "✅" if fish["obtained"] else "❌"
        bait_str = (
            f"({fish.get('bait', '') or '通杀'})" if fish.get("bait") else "(通杀)"
        )
        rank_str = ""
        if fish["obtained"]:
            rank = _db.get_handbook_user_ranking(group_id, fish["name"], user_id)
            if rank:
                rank_str = f" 🏅#{rank}"

        rregion = fish.get("region", "未知")
        ground = fish.get("fishing_ground", "未知")
        if rregion != current_region:
            lines.append(f"\n  📍 {rregion}")
            current_region = rregion
            current_ground = None
        if ground != current_ground:
            lines.append(f"    🎣 {ground}")
            current_ground = ground

        weather_str = ""
        fish_weather = fish.get("weather", "")
        if fish_weather:
            weather_str = f" 🌤️{fish_weather}"

        # 显示更多详细信息（尺寸、价值）
        size_info = f" {fish['min_size']:.1f}-{fish['max_size']:.1f}cm"
        value_info = f" 💰{int(fish['base_value'])}G"
        lines.append(
            f"    {mark} {fish['name']} ({fish['fish_type']}) {bait_str}{size_info}{value_info}{rank_str}{weather_str}"
        )

    if page < total_pages:
        next_cmd = "/鱼群图鉴"
        if fish_name:
            next_cmd += f" {fish_name}"
        elif bait:
            next_cmd += f" {bait}"
        elif fish_type:
            next_cmd += f" {fish_type}"
        next_cmd += f" {page + 1}"
        if region:
            next_cmd += f" {region}"
        if fishing_ground:
            next_cmd += f" {fishing_ground}"
        lines.append(f"\n  下一页：{next_cmd}")
    return "\n".join(lines)


def unobtained_fish(
    user_id,
    group_id,
    page=1,
    region=None,
    fishing_ground=None,
    bait=None,
    weather=None,
):
    """查询未获取的鱼 - 分页显示，每页10条
    参数: user_id, group_id, page(默认1), region(可选地区筛选), fishing_ground(可选钓场筛选),
          bait(可选鱼饵名查询), weather(可选天气筛选)
    用法: /未获取 [地区|钓场] [天气] [鱼饵] [页码]
    """
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"

    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1

    fish_list = _db.get_unobtained(
        user_id,
        group_id,
        region=region,
        fishing_ground=fishing_ground,
        bait=bait,
        weather=weather,
    )
    if not fish_list:
        return "🎉 恭喜！符合条件的鱼已经全部获取完毕！"

    page_size = 10
    total = len(fish_list)
    total_pages = (total + page_size - 1) // page_size
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    page_data = fish_list[start : start + page_size]

    # 构建标题
    title_parts = [f"❓ {user_id} 未获取的鱼"]
    if region:
        title_parts.append(f" [地区: {region}]")
    if fishing_ground:
        title_parts.append(f" [钓场: {fishing_ground}]")
    if bait:
        title_parts.append(f" [鱼饵: {bait}]")
    if weather:
        title_parts.append(f" [天气: {weather}]")
    title_parts.append(f" （第 {page}/{total_pages} 页，共 {total} 种未获取）")
    lines = ["".join(title_parts)]

    # 按区域+钓场分组展示
    current_region = None
    current_ground = None
    for fish in page_data:
        bait_str = (
            f"({fish.get('bait', '') or '通杀'})" if fish.get("bait") else "(通杀)"
        )

        rregion = fish.get("region", "未知")
        ground = fish.get("fishing_ground", "未知")
        if rregion != current_region:
            lines.append(f"\n  📍 {rregion}")
            current_region = rregion
            current_ground = None
        if ground != current_ground:
            lines.append(f"    🎣 {ground}")
            current_ground = ground

        weather_str = ""
        fish_weather = fish.get("weather", "")
        if fish_weather:
            weather_str = f" 🌤️{fish_weather}"

        size_info = f" {fish['min_size']:.1f}-{fish['max_size']:.1f}cm"
        value_info = f" 💰{int(fish['base_value'])}G"
        lines.append(
            f"    ❌ {fish['name']} ({fish['fish_type']}) {bait_str}{size_info}{value_info}{weather_str}"
        )

    if page < total_pages:
        next_cmd = "/未获取"
        if region:
            next_cmd += f" {region}"
        if fishing_ground:
            next_cmd += f" {fishing_ground}"
        if weather:
            next_cmd += f" {weather}"
        if bait:
            next_cmd += f" {bait}"
        next_cmd += f" {page + 1}"
        lines.append(f"\n  下一页：{next_cmd}")
    return "\n".join(lines)



def fishing_log(user_id, group_id, page=1):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    page_size = _config.get("page_size", 10)
    records, total = _db.get_log(user_id, group_id, page, page_size)
    if not records:
        return "📋 暂无钓鱼记录"
    total_pages = (total + page_size - 1) // page_size
    lines = [f"📋 {user_id} 的钓鱼记录（第 {page}/{total_pages} 页，共 {total} 条）"]
    for r in records:
        big_icon = "🐠" if r["is_big"] else "🐟"
        lines.append(
            f"  {big_icon} {r['fish_name']} ({r['fish_type']}) {r['size']:.1f}cm 价值{int(r['value'])}G | {r['catch_time']}"
        )
    if page < total_pages:
        lines.append(f"  查看更多：/钓鱼记录 {page + 1}")
    return "\n".join(lines)


def leaderboard(group_id, fish_name=None, size_order=None, fish_type=None, page=1):
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    page_size = 10
    order = "DESC"
    order_label = "大"
    if size_order == "小":
        order = "ASC"
        order_label = "小"

    if fish_name:
        # 按鱼名查：每用户取最大/最小尺寸，分页
        rankings, total = _db.get_leaderboard(
            group_id,
            fish_name=fish_name,
            order=order,
            fish_type=None,
            page=page,
            page_size=page_size,
        )
        if not rankings:
            return f"📊 {fish_name} 暂无钓鱼记录"
        total_pages = (total + page_size - 1) // page_size
        title = f"📊 {fish_name}"
        if fish_type:
            title += f" ({fish_type})"
        title += f" 排行榜（从{order_label}到{'小' if order_label == '大' else '大'}，第{page}/{total_pages}页）"
        lines = [title]
        medals = ["🥇", "🥈", "🥉"]
        # 只取当前页
        offset = (page - 1) * page_size
        page_rankings = rankings[offset : offset + page_size]
        for i, r in enumerate(page_rankings):
            global_i = offset + i
            medal = medals[global_i] if global_i < 3 else f"{global_i + 1}."
            lines.append(f"  {medal} {r['user_id']} - {r['size']:.1f}cm")
    else:
        # 按种类或全部：获取全部记录，在内存中分组并限制每种鱼3条
        all_records, _ = _db.get_leaderboard(
            group_id,
            fish_name=None,
            order=order,
            fish_type=fish_type,
            page=1,
            page_size=100000,
        )
        if not all_records:
            if fish_type:
                return f"📊 {fish_type} 暂无钓鱼记录"
            else:
                return "📊 暂无钓鱼记录"

        # 按鱼名分组，按种类/全部查询时每组最多3条
        grouped = []
        current_fish = None
        fish_count = 0
        for r in all_records:
            if r["fish_name"] != current_fish:
                current_fish = r["fish_name"]
                fish_count = 0
            if fish_count < 3:
                grouped.append(r)
                fish_count += 1

        total = len(grouped)
        total_pages = (total + page_size - 1) // page_size
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size
        page_items = grouped[offset : offset + page_size]

        if fish_type:
            title = f"📊 {fish_type}"
        else:
            title = "📊 全部鱼类"
        title += f" 排行榜（从{order_label}到{'小' if order_label == '大' else '大'}，第{page}/{total_pages}页）"
        lines = [title]
        current_fish = None
        fish_rank = 0
        for r in page_items:
            if r["fish_name"] != current_fish:
                current_fish = r["fish_name"]
                fish_rank = 0
                lines.append(f"  [{r.get('fish_type', '')}] {r['fish_name']}")
            fish_rank += 1
            medal = (
                ["🥇", "🥈", "🥉"][fish_rank - 1] if fish_rank <= 3 else f"{fish_rank}."
            )
            lines.append(f"    {medal} {r['user_id']} - {r['size']:.1f}cm")

    if page < total_pages:
        next_cmd = "/排行榜"
        if fish_name:
            next_cmd += f" {fish_name}"
        if size_order:
            next_cmd += f" {size_order}"
        if fish_type:
            next_cmd += f" {fish_type}"
        next_cmd += f" {page + 1}"
        lines.append(f"\n  下一页：{next_cmd}")
    return "\n".join(lines)


# ==================== 管理API（供Plugin Pages使用） ====================


def admin_get_all_fish():
    """获取所有鱼类数据"""
    if _db is None:
        return []
    return _db.get_all_fish()


def admin_add_or_update_fish(data):
    """新增或更新鱼类数据"""
    if _db is None:
        return False
    fish_list = _db.get_all_fish()
    # 查找是否存在同名鱼
    existing_idx = None
    for i, f in enumerate(fish_list):
        if f["name"] == data["name"]:
            existing_idx = i
            break
    if existing_idx is not None:
        fish_list[existing_idx] = data
    else:
        fish_list.append(data)
    _db.reload_fish_data(fish_list)
    return True


def admin_delete_fish(name):
    """删除鱼类数据"""
    if _db is None:
        return False
    fish_list = _db.get_all_fish()
    fish_list = [f for f in fish_list if f["name"] != name]
    _db.reload_fish_data(fish_list)
    return True


def admin_get_all_lures():
    """获取所有鱼饵数据"""
    if _db is None:
        return []
    return _db.get_all_lures()


def admin_add_or_update_lure(data):
    """新增或更新鱼饵"""
    if _db is None:
        return False
    lures = _db.get_all_lures()
    existing_idx = None
    for i, lure in enumerate(lures):
        if lure["name"] == data["name"]:
            existing_idx = i
            break
    if existing_idx is not None:
        lures[existing_idx] = data
    else:
        lures.append(data)
    _db.reload_lure_data(lures)
    return True


def admin_delete_lure(name):
    """删除鱼饵"""
    if _db is None:
        return False
    lures = _db.get_all_lures()
    lures = [lure for lure in lures if lure["name"] != name]
    _db.reload_lure_data(lures)
    return True


def admin_get_weather():
    """获取当前天气数据"""
    if _db is None:
        return {
            "current": [],
            "weather_types": _config.get("weather_types", []) if _config else [],
        }
    weather_data = _db.get_weather()
    weather_types = _config.get("weather_types", []) if _config else []
    return {"current": weather_data, "weather_types": weather_types}


def admin_save_weather_types(weather_types):
    """保存天气类型列表（持久化到DB）"""
    if not isinstance(weather_types, list) or len(weather_types) == 0:
        return False
    global _config
    if _config is not None:
        _config["weather_types"] = weather_types
    if _db is not None:
        _db.set_config("weather_types", weather_types)
    return True


def admin_set_weather(weather_date, slot, weather_type):
    """手动设置天气"""
    if _db is None:
        return False
    weather_types = _config.get("weather_types", []) if _config else []
    if weather_type not in weather_types:
        return False
    _db.set_weather(weather_date, slot, weather_type)
    return True


def admin_get_shop():
    """获取商城商品列表"""
    if _db is None:
        return []
    return _db.get_shop_lures()
