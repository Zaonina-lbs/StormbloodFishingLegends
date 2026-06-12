"""
热更新模块 - 从 YAML 配置文件热更新游戏数据
支持二次确认和打印变更内容
"""

import os
import yaml
from .database import get_db


def load_yaml_config(filepath):
    """加载 YAML 配置文件"""
    if not os.path.isabs(filepath):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def show_fish_diff(current_fish, new_fish):
    """对比并显示鱼类数据变更"""
    changes = []
    for nf in new_fish:
        name = nf["name"]
        cf = current_fish.get(name)
        if cf is None:
            changes.append(f"  🆕 新增: {name}")
            continue
        for key in ["base_value"]:
            old_val = cf.get(key, "N/A")
            new_val = nf.get(key, "N/A")
            if str(old_val) != str(new_val):
                changes.append(f"  ✏️ {name}: {key} {old_val} -> {new_val}")
    for name in current_fish:
        if name not in {f["name"] for f in new_fish}:
            changes.append(f"  🗑️ 删除: {name}")
    return changes


def show_lure_diff(current_lures, new_lures):
    """对比并显示鱼饵数据变更"""
    changes = []
    current_map = {lure["name"]: lure for lure in current_lures}
    new_map = {lure["name"]: lure for lure in new_lures}
    for name, nl in new_map.items():
        cl = current_map.get(name)
        if cl is None:
            changes.append(f"  🆕 新增: {name}")
            continue
        for key in ["sellable", "price"]:
            old_val = cl.get(key, "N/A")
            new_val = nl.get(key, "N/A")
            if str(old_val) != str(new_val):
                changes.append(f"  ✏️ {name}: {key} {old_val} -> {new_val}")
    return changes


def preview_reload(fish_file="fish_data.yaml", lure_file="lure_data.yaml"):
    """
    预览热更新变更内容，不实际执行
    返回: (fish_changes, lure_changes, new_fish_list, new_lure_list)
    """
    db = get_db()
    current_fish = {f["name"]: f for f in db.get_all_fish()}
    current_lures = {lure["name"]: lure for lure in db.get_all_lures()}

    new_fish = load_yaml_config(fish_file)
    new_lures = load_yaml_config(lure_file)

    fish_changes = []
    lure_changes = []

    if new_fish and "fishes" in new_fish:
        fish_changes = show_fish_diff(current_fish, new_fish["fishes"])
    if new_lures and "lures" in new_lures:
        lure_changes = show_lure_diff(current_lures, new_lures["lures"])

    new_fish_list = new_fish["fishes"] if new_fish else []
    new_lure_list = new_lures["lures"] if new_lures else []

    return fish_changes, lure_changes, new_fish_list, new_lure_list


def do_reload(fish_file="fish_data.yaml", lure_file="lure_data.yaml", confirm=False):
    """
    执行热更新
    Args:
        fish_file: 鱼数据 YAML 文件
        lure_file: 鱼饵数据 YAML 文件
        confirm: 如果为 True，跳过确认直接执行
    Returns:
        (success, message)
    """
    fish_changes, lure_changes, new_fish_list, new_lure_list = preview_reload(
        fish_file, lure_file
    )

    if not fish_changes and not lure_changes:
        return True, "✅ 没有检测到数据变更"

    # 打印变更
    print("\n" + "=" * 60)
    print("📋 检测到以下数据变更：")
    if fish_changes:
        print("\n🐟 鱼类数据变更：")
        for c in fish_changes:
            print(c)
    if lure_changes:
        print("\n🎣 鱼饵数据变更：")
        for c in lure_changes:
            print(c)
    print("=" * 60)

    # 确认
    if not confirm:
        user_input = input("\n是否确认热更新？(y/n): ").strip().lower()
        if user_input != "y":
            return False, "❌ 已取消热更新"

    # 执行更新
    db = get_db()
    if new_fish_list:
        db.reload_fish_data(new_fish_list)
    if new_lure_list:
        db.reload_lure_data(new_lure_list)

    # 重新加载配置
    from . import game_engine

    game_engine._reload_config()

    return True, "✅ 热更新完成！"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="游戏数据热更新")
    parser.add_argument("--preview", action="store_true", help="仅预览变更")
    parser.add_argument("--confirm", action="store_true", help="跳过二次确认")
    parser.add_argument("--fish", type=str, default="fish_data.yaml", help="鱼数据文件")
    parser.add_argument(
        "--lure", type=str, default="lure_data.yaml", help="鱼饵数据文件"
    )
    args = parser.parse_args()

    if args.preview:
        fc, lc, _, _ = preview_reload(args.fish, args.lure)
        if not fc and not lc:
            print("没有检测到数据变更")
        else:
            for c in fc + lc:
                print(c)
    else:
        success, msg = do_reload(args.fish, args.lure, confirm=args.confirm)
        print(msg)
