"""
数据迁移脚本：校准鱼饵背包数据
将 fish_caught 中未出售的 "苦尔鳗" 和 "硬头鳟" 同步到 inventory 表中作为鱼饵
"""

import sys
import os

# 确保能找到项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database

# 新增的鱼饵名称
NEW_LURES = ["苦尔鳗", "硬头鳟"]


def migrate(db_path=None):
    db = Database(db_path) if db_path else Database()
    db.connect()

    for lure_name in NEW_LURES:
        # 1. 确保 lures 表中存在该鱼饵记录
        existing = db.conn.execute(
            "SELECT id FROM lures WHERE name=?", (lure_name,)
        ).fetchone()
        if not existing:
            db.conn.execute(
                "INSERT INTO lures(name, sellable, price) VALUES(?, 0, 0)",
                (lure_name,),
            )
            print(f"[lures] 新增鱼饵记录: {lure_name}")

        # 2. 查找所有拥有该鱼（未出售）的用户
        rows = db.conn.execute(
            """
            SELECT user_id, group_id, COUNT(*) as cnt
            FROM fish_caught
            WHERE fish_name=? AND is_sold=0
            GROUP BY user_id, group_id
            """,
            (lure_name,),
        ).fetchall()

        if not rows:
            print(f"[inventory] {lure_name}: 没有用户拥有未出售的该鱼")
            continue

        for row in rows:
            user_id = row["user_id"]
            group_id = row["group_id"]
            cnt = row["cnt"]

            # 3. 检查 inventory 中是否已有记录
            inv = db.conn.execute(
                "SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
                (user_id, group_id, lure_name),
            ).fetchone()

            if inv:
                # 已有记录，补齐差额（如果需要）
                current_qty = inv["quantity"]
                if current_qty < cnt:
                    db.conn.execute(
                        "UPDATE inventory SET quantity=? WHERE user_id=? AND group_id=? AND lure_name=?",
                        (cnt, user_id, group_id, lure_name),
                    )
                    print(
                        f"[inventory] {lure_name}: {user_id}@{group_id} 校准: {current_qty} -> {cnt}"
                    )
                else:
                    print(
                        f"[inventory] {lure_name}: {user_id}@{group_id} 已有 {current_qty}，无需校准"
                    )
            else:
                # 没有记录，插入
                db.conn.execute(
                    "INSERT INTO inventory(user_id, group_id, lure_name, quantity) VALUES(?,?,?,?)",
                    (user_id, group_id, lure_name, cnt),
                )
                print(
                    f"[inventory] {lure_name}: {user_id}@{group_id} 新增背包记录: {cnt} 个"
                )

    db.conn.commit()
    db.close()
    print("\n迁移完成！")


if __name__ == "__main__":
    db_path = None
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    migrate(db_path)
