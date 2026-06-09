"""
游戏引擎模块 - 提供纯函数，供 AstrBot 直接调用
所有用户相关操作均需传入 group_id 以区分群聊
"""

import os
import random
import yaml
from datetime import date, timedelta

_config = None
_db = None
_data_dir = None


def _load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
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


def init_engine(data_dir=None):
    """初始化游戏引擎，设置数据目录并创建/导入数据。
    在 AstrBot 插件中调用此函数设置数据库路径。
    
    Args:
        data_dir: AstrBot 插件数据目录，数据库文件将存放在此目录下
    """
    global _data_dir, _db, _config
    _data_dir = data_dir
    _config = _load_config()
    from .database import init_db_with_path
    if data_dir:
        _db = init_db_with_path(None, data_dir=data_dir)
    else:
        _db = get_db()
    
    # 创建数据库表结构
    _db.init_database()
    
    # 如果鱼基础数据表为空，从 YAML/配置导入初始数据
    all_fish = _db.get_all_fish()
    if not all_fish:
        # 优先从 fish_data.yaml 加载完整的鱼基础数据
        fish_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fish_data.yaml")
        fish_data = _config.get("fishes", [])
        if os.path.exists(fish_data_path):
            with open(fish_data_path, "r", encoding="utf-8") as f:
                fish_yaml = yaml.safe_load(f)
                if fish_yaml and "fishes" in fish_yaml:
                    fish_data = fish_yaml["fishes"]
        if fish_data:
            _db.import_fish_data(fish_data)
            logger.info(f"已导入 {len(fish_data)} 条鱼基础数据到数据库")
        
        # 导入鱼饵数据（从 config.yaml 加载）
        lures = _config.get("lures", [])
        if lures:
            _db.import_lure_data(lures)
            logger.info(f"已导入 {len(lures)} 条鱼饵数据到数据库")
    
    # 生成天气数据
    from datetime import date as dt, timedelta
    today = dt.today()
    for i in range(4):
        d = (today + timedelta(days=i)).isoformat()
        for slot in (0, 1):
            _db.generate_weather(d, slot)
    
    if is_debug():
        _debug(f"引擎初始化完成，数据库路径: {_db.db_path}")
        _debug(f"鱼种数: {len(_db.get_all_fish())}, 鱼饵数: {len(_db.get_all_lures())}")


# 在模块加载时记录日志（不是 AstrBot 环境时使用）
import logging
try:
    logger = logging.getLogger("astrbot")
except Exception:
    logger = logging.getLogger(__name__)

_config = _load_config()
_init_db()


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
    gold_min = _config.get("sign_gold_min", 2500)
    gold_max = _config.get("sign_gold_max", 4000)
    if roll < 0.5:
        gold = random.randint(gold_min, gold_max)
        _db.update_user_gold(user_id, group_id, gold)
        _db.update_sign_date(user_id, group_id)
        return f"✅ 签到成功！获得 {gold} 金币"
    else:
        # 鱼饵奖励总价值约为金币奖励的2倍
        # 金币范围 avg ≈ 1500，2x ≈ 3000
        # 从可购买的鱼饵中随机选一个，按数量凑到目标价值附近
        shop_lures = [l for l in _db.get_shop_lures() if l["price"] > 0]
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

    lines = [f"🎣 当前使用鱼饵：{effective_bait}"]
    if count > 1:
        lines.append(f"  连续钓鱼 {count} 次")
    results = []
    total_value = 0
    fish_counts = {}

    for i in range(count):
        if count > 1:
            _debug(f"--- 第 {i+1}/{count} 次 ---")
        result = _do_single_fish(user_id, group_id, effective_bait, fishing_ground, i == 0)
        if result is None:
            return "❌ 当前条件下没有可钓的鱼"
        if result.startswith("❌"):
            if count == 1:
                return result
            results.append(f"  [{i+1}] {result}")
            continue
        results.append(f"  [{i+1}] {result}")
        # 统计
        parts = result.split("|")
        if len(parts) >= 2:
            try:
                val_str = parts[1].strip().split()[0]
                total_value += int(val_str)
            except:
                pass
        for word in result.split():
            if "鱼王" in word or "鱼皇" in word or "普通鱼" in word:
                # extract fish name
                name = result.split("]：")[1].split("\n")[0] if "]：" in result else "unknown"
                fish_counts[name] = fish_counts.get(name, 0) + 1

    if count == 1:
        single_result = results[0][4:] if results and results[0].startswith("  [1] ") else (results[0] if results else "❌")
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
            fish_summary = " | ".join(f"{k}x{v}" for k, v in sorted(unique_fish.items()))
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
                if f["weather"] == "" or weather_type in f.get("weather", "").split("/"):
                    candidate_fish.append(f)
            if not candidate_fish:
                candidate_fish = [f for f in all_fish if f["fish_type"] == "普通鱼"]
    else:
        if fishing_ground:
            all_in_ground = _db.get_fish_by_ground(fishing_ground, weather_type)
            candidate_fish = []
            for f in all_in_ground:
                if f["bait"] == effective_bait or f["bait"] == "":
                    candidate_fish.append(f)
        else:
            candidate_fish = _db.get_fish_by_bait(effective_bait, weather_type)

    if not candidate_fish:
        return None

    if show_debug:
        _debug(f"鱼池共 {len(candidate_fish)} 条鱼")

    # 按类型分组
    normal_fish = [f for f in candidate_fish if f["fish_type"] == "普通鱼"]
    king_fish = [f for f in candidate_fish if f["fish_type"] == "鱼王"]
    emperor_fish = [f for f in candidate_fish if f["fish_type"] == "鱼皇"]
    if show_debug:
        _debug(f"普通鱼:{len(normal_fish)} 鱼王:{len(king_fish)} 鱼皇:{len(emperor_fish)}")

    # 概率判定
    if effective_bait == "万能鱼饵":
        if not normal_fish:
            return None
        target_pool = normal_fish
    else:
        prob_target = _config.get("bait_prob_target", 25)
        prob_king = _config.get("bait_prob_king", 2)
        prob_emperor = _config.get("bait_prob_emperor", 0.2)
        roll = random.uniform(0, 100)
        if show_debug:
            _debug(f"概率判定 roll={roll:.1f}")
        if emperor_fish and roll < prob_emperor:
            target_pool = emperor_fish
        elif king_fish and roll < prob_emperor + prob_king:
            target_pool = king_fish
        elif normal_fish and roll < prob_emperor + prob_king + prob_target:
            target_pool = normal_fish
        else:
            target_pool = normal_fish if normal_fish else candidate_fish

    chosen_fish = random.choice(target_pool)

    # 尺寸生成
    size, is_big = _generate_size(chosen_fish["min_size"], chosen_fish["min_big_size"], chosen_fish["max_size"])
    if show_debug:
        _debug(f"尺寸: {size:.1f}cm {'大鱼' if is_big else '普通'}")

    # 价值计算
    value = _calculate_value(chosen_fish, size)

    # 自动锁定：仅鱼王鱼皇
    auto_locked = 1 if chosen_fish["fish_type"] in ("鱼王", "鱼皇") else 0

    # 保存
    _db.add_caught(user_id, group_id, chosen_fish["name"], chosen_fish["fish_type"], size, is_big, value, auto_locked)
    _db.add_log(user_id, group_id, chosen_fish["name"], chosen_fish["fish_type"], size, is_big, value, effective_bait, chosen_fish["fishing_ground"], weather_type)

    if effective_bait == "万能鱼饵":
        _db.update_user_gold(user_id, group_id, -_config.get("default_bait_price", 100))
    else:
        _db.remove_lure(user_id, group_id, effective_bait, 1)

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

def view_fish_pool():
    """查看当前鱼池（当前天气下可钓的鱼），按鱼皇>鱼王>普通鱼排序"""
    weather = _db.get_today_weather()
    weather_type = weather["weather"]
    all_fish = _db.get_all_fish()
    pool = []
    for f in all_fish:
        if f["weather"] == "" or weather_type in f.get("weather", "").split("/"):
            pool.append(f)
    if not pool:
        return "🐟 当前鱼池为空"
    # 按鱼皇>鱼王>普通鱼排序
    type_order = {"鱼皇": 0, "鱼王": 1, "普通鱼": 2}
    pool.sort(key=lambda x: (type_order.get(x["fish_type"], 99), x["name"]))
    lines = [f"🐟 当前鱼池（天气：{weather_type}，共 {len(pool)} 种）"]
    current_type = None
    for f in pool:
        if f["fish_type"] != current_type:
            current_type = f["fish_type"]
            lines.append(f"\n  【{current_type}】")
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
        "  /钓鱼帮助\n"
        "  /鱼池版本\n"
        "\n【钓鱼】\n"
        "  /钓鱼 [鱼饵] [钓场] [次数]\n"
        "  /使用鱼饵 [饵]\n"
        "  /查看当前鱼饵\n"
        "  /不使用鱼饵\n"
        "  /查看天气\n"
        "  /当前鱼池\n"
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
        "  /鱼群图鉴 [地区|钓场|页码] [页码]\n"
        "  /钓鱼记录 [页]\n"
        "  /排行榜 [鱼名] [大/小]\n"
        "\n【管理】\n"
        "  /热更新（管理员）"
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
        return "🎒 背包为空"
    lines = [f"🎒 {user_id} 的背包"]
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
        lines.append(f"  [{f['id']}] {big_icon} {f['fish_name']} ({f['fish_type']}) {f['size']:.1f}cm 价值{int(f['value'])}G {lock_icon} 📅{f['caught_date']}")
    if page < total_pages:
        lines.append(f"\n  下一页：/查看鱼塘 {page+1}")
    return "\n".join(lines)


def lock_fish(user_id, group_id, fish_id):
    if not fish_id:
        return "❌ 请提供 fish_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    try:
        fish_id = int(fish_id)
    except (ValueError, TypeError):
        return "❌ fish_id 必须为数字"
    fish = _db.get_caught_by_id(fish_id, user_id, group_id)
    if not fish:
        return f"❌ 未找到鱼 ID={fish_id}"
    if fish["locked"]:
        return f"🔒 {fish['fish_name']} 已是锁定状态"
    _db.lock_fish(fish_id, user_id, group_id)
    return f"🔒 {fish['fish_name']} 已锁定"


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


# ==================== 图鉴与排行榜 ====================

def get_distinct_regions():
    """获取所有不重复的区域列表"""
    return _db.get_distinct_regions()

def get_distinct_grounds():
    """获取所有不重复的钓场列表"""
    return _db.get_distinct_grounds()

def fish_handbook(user_id, group_id, page=1, region=None, fishing_ground=None):
    """鱼群图鉴 - 分页显示，每页10条
    参数: user_id, group_id, page(默认1), region(可选地区筛选), fishing_ground(可选钓场筛选)
    用法: /鱼群图鉴 [地区|钓场|页码] [页码]
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

    handbook = _db.get_handbook(user_id, group_id, region=region, fishing_ground=fishing_ground)
    if not handbook:
        return "📖 图鉴数据为空"

    page_size = 10
    total = len(handbook)
    total_pages = (total + page_size - 1) // page_size
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    page_data = handbook[start:start + page_size]

    # 构建图鉴标题
    title_parts = [f"📖 {user_id} 的鱼群图鉴"]
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
        bait_str = f"({fish.get('bait','') or '通杀'})" if fish.get('bait') else "(通杀)"
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
        lines.append(f"    {mark} {fish['name']} ({fish['fish_type']}) {bait_str}{rank_str}{weather_str}")

    if page < total_pages:
        next_cmd = f"/鱼群图鉴 {page+1}"
        if region:
            next_cmd += f" {region}"
        if fishing_ground:
            next_cmd += f" {fishing_ground}"
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
        lines.append(f"  {big_icon} {r['fish_name']} ({r['fish_type']}) {r['size']:.1f}cm 价值{int(r['value'])}G | {r['catch_time']}")
    if page < total_pages:
        lines.append(f"  查看更多：/钓鱼记录 {page + 1}")
    return "\n".join(lines)


def leaderboard(group_id, fish_name, size_order=None):
    if not fish_name:
        return "❌ 请提供鱼名"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    order = "DESC"
    order_label = "大"
    if size_order == "小":
        order = "ASC"
        order_label = "小"
    rankings = _db.get_leaderboard(group_id, fish_name, order)
    if not rankings:
        return f"📊 {fish_name} 暂无钓鱼记录"
    lines = [f"📊 {fish_name} 排行榜（从{order_label}到{'小' if order_label=='大' else '大'}，前10）"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rankings):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"  {medal} {r['user_id']} - {r['size']:.1f}cm")
    return "\n".join(lines)
