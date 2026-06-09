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
    """初始化游戏引擎，设置数据目录。
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
    gold_min = _config.get("sign_gold_min", 1000)
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
        return results[0][4:] if results and results[0].startswith("  [1] ") else (results[0] if results else "❌")

    # 汇总
    lines = [f"🎣 连续钓鱼 {count} 次完成！"]
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

    # 自动锁定
    auto_locked = 0
    lock_reason = ""
    if chosen_fish["fish_type"] in ("鱼王", "鱼皇"):
        auto_locked = 1
        lock_reason = "L"
    if not auto_locked:
        extreme = _db.get_extreme(group_id, chosen_fish["name"])
        if extreme["max_size"] is None or size > extreme["max_size"]:
            auto_locked = 1
            lock_reason = "M"
        elif extreme["min_size"] is None or size < extreme["min_size"]:
            auto_locked = 1
            lock_reason = "m"

    # 保存
    _db.add_caught(user_id, group_id, chosen_fish["name"], chosen_fish["fish_type"], size, is_big, value, auto_locked)
    _db.add_log(user_id, group_id, chosen_fish["name"], chosen_fish["fish_type"], size, is_big, value, effective_bait, chosen_fish["fishing_ground"], weather_type)

    if effective_bait != "万能鱼饵":
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
    value = base_value * (1 + (size_ratio - 0.5) * 2 * float_pct)
    return round(max(1, value))


def get_fish_help():
    return (
        "📋 FF14 钓鱼游戏命令\n"
        "【账号】/钓鱼注册 /签到 /查看金币 /钓鱼帮助\n"
        "【钓鱼】/钓鱼 [鱼饵] [钓场] [次数] /使用鱼饵 [饵] /查看天气 /鱼池版本\n"
        "【背包】/查看背包 /查看鱼塘\n"
        "【管理】/锁定 [id] /解锁 [id] /出售 [鱼名] /出售 id[N] /全部出售\n"
        "【商店】/商城 /购买道具 [id] [数量] /氪金 [金币] /查看账单\n"
        "【图鉴】/鱼群图鉴 [页码] [钓场] /钓鱼记录 [页] /排行榜 [鱼名] [大/小]\n"
        "【管理】/热更新（管理员）"
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


def view_fish_pond(user_id, group_id):
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"
    user = _db.get_user(user_id, group_id)
    if not user:
        return f"❌ 用户 {user_id} 在本群不存在"
    fish_list = _db.get_pond(user_id, group_id)
    if not fish_list:
        return "🐟 鱼塘为空"
    lines = [f"🐟 {user_id} 的鱼塘（按日期倒序）"]
    for f in fish_list[:30]:
        lock_icon = "🔒" if f["locked"] else "🔓"
        big_icon = "🐠" if f["is_big"] else "🐟"
        lines.append(f"  [{f['id']}] {big_icon} {f['fish_name']} ({f['fish_type']}) {f['size']:.1f}cm 价值{int(f['value'])}G {lock_icon}")
    if len(fish_list) > 30:
        lines.append(f"  ... 共 {len(fish_list)} 条鱼")
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
    if not fish["locked"]:
        return f"🔓 {fish['fish_name']} 已是解锁状态"
    _db.unlock_fish(fish_id, user_id, group_id)
    return f"🔓 {fish['fish_name']} 已解锁"


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

def fish_handbook(user_id, group_id, page=1, fishing_ground=None):
    """鱼群图鉴 - 分页显示，每页10条
    参数: user_id, group_id, page(默认1), fishing_ground(可选筛选项)
    用法: /鱼群图鉴 [页码] [钓场]
    """
    if not user_id:
        return "❌ 请提供 user_id"
    if not group_id:
        return "❌ 请提供 group_id（群号）"

    # 参数智能识别：如果 fishing_ground 是纯数字，当作 page
    try:
        if fishing_ground is not None:
            int(str(fishing_ground))
            # fishing_ground looks like a number → swap
            if page == 1:
                page = int(fishing_ground)
                fishing_ground = None
    except (ValueError, TypeError):
        pass

    try:
        page = int(page) if page else 1
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1

    handbook = _db.get_handbook(user_id, group_id, fishing_ground)
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

        region = fish.get("region", "未知")
        ground = fish.get("fishing_ground", "未知")
        if region != current_region:
            lines.append(f"\n  📍 {region}")
            current_region = region
            current_ground = None
        if ground != current_ground:
            lines.append(f"    🎣 {ground}")
            current_ground = ground

        lines.append(f"    {mark} {fish['name']} ({fish['fish_type']}) {bait_str}{rank_str}")

    if page < total_pages:
        if fishing_ground:
            lines.append(f"\n  下一页：/鱼群图鉴 {page+1} {fishing_ground}")
        else:
            lines.append(f"\n  下一页：/鱼群图鉴 {page+1}")
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
