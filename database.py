"""
数据库模块 - SQLite 数据库的创建、连接和数据操作
"""

import sqlite3
import os
from datetime import datetime, date
import yaml


def load_config():
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Database:
    def __init__(self, db_path=None, data_dir=None):
        if db_path is None:
            if data_dir:
                db_path = os.path.join(data_dir, "fishing_game.db")
            else:
                config = load_config()
                db_path = config.get("db_path", "fishing_game.db")
        if not os.path.isabs(db_path):
            if data_dir:
                db_path = os.path.join(data_dir, "fishing_game.db")
            else:
                db_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), db_path
                )
        # ensure parent directory exists
        parent = os.path.dirname(db_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        self.db_path = db_path
        self.conn = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def init_database(self):
        self.connect()
        c = self.conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                gold INTEGER NOT NULL DEFAULT 0,
                default_bait TEXT DEFAULT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                last_sign_date TEXT DEFAULT NULL,
                last_fishing_time TEXT DEFAULT NULL,
                last_fishing_count INTEGER DEFAULT NULL,
                PRIMARY KEY (user_id, group_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS fish_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                region TEXT NOT NULL,
                fishing_ground TEXT NOT NULL,
                bait TEXT DEFAULT '',
                weather TEXT DEFAULT '',
                fish_type TEXT NOT NULL CHECK(fish_type IN ('普通鱼','鱼王','鱼皇')),
                min_size REAL NOT NULL,
                min_big_size REAL NOT NULL,
                max_size REAL NOT NULL,
                base_value REAL NOT NULL DEFAULT 50
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS lures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sellable INTEGER NOT NULL DEFAULT 0,
                price INTEGER NOT NULL DEFAULT 200
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS weather (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weather_date TEXT NOT NULL,
                slot INTEGER NOT NULL DEFAULT 0,
                weather_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                UNIQUE(weather_date, slot)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                lure_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id,group_id,lure_name)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS fish_caught (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                fish_name TEXT NOT NULL,
                fish_type TEXT NOT NULL,
                size REAL NOT NULL,
                is_big INTEGER NOT NULL DEFAULT 0,
                value REAL NOT NULL DEFAULT 0,
                locked INTEGER NOT NULL DEFAULT 0,
                caught_date TEXT NOT NULL DEFAULT (date('now','localtime')),
                caught_time TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                is_sold INTEGER NOT NULL DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS fishing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                fish_name TEXT NOT NULL,
                fish_type TEXT NOT NULL,
                size REAL NOT NULL,
                is_big INTEGER NOT NULL DEFAULT 0,
                value REAL NOT NULL DEFAULT 0,
                bait_used TEXT DEFAULT NULL,
                fishing_ground TEXT DEFAULT NULL,
                weather TEXT DEFAULT NULL,
                catch_time TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS krypton_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_fc_user ON fish_caught(user_id,group_id,is_sold)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_fl_user ON fishing_log(user_id,group_id,catch_time)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_inv_user ON inventory(user_id,group_id,lure_name)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_weather_date ON weather(weather_date,slot)"
        )

        # plugin_config 持久化配置表（天气类型等热更新配置）
        c.execute(
            "CREATE TABLE IF NOT EXISTS plugin_config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        # 迁移：为已有的 users 表添加 last_fishing_time 列（如果不存在）
        try:
            c.execute(
                "ALTER TABLE users ADD COLUMN last_fishing_time TEXT DEFAULT NULL"
            )
        except sqlite3.OperationalError:
            pass  # 列已存在
        # 迁移：为已有的 users 表添加 last_fishing_count 列（如果不存在）
        try:
            c.execute(
                "ALTER TABLE users ADD COLUMN last_fishing_count INTEGER DEFAULT NULL"
            )
        except sqlite3.OperationalError:
            pass  # 列已存在

        self.conn.commit()
        self.close()

    def reset_database(self):
        self.connect()
        tables = [
            "fishing_log",
            "fish_caught",
            "inventory",
            "weather",
            "krypton_log",
            "plugin_config",
            "lures",
            "fish_base",
            "users",
        ]
        for t in tables:
            self.conn.execute(f"DROP TABLE IF EXISTS {t}")
        self.conn.commit()
        self.close()
        self.init_database()

    def import_fish_data(self, fish_list):
        self.connect()
        self.conn.execute("DELETE FROM fish_base")
        for fish in fish_list:
            self.conn.execute(
                "INSERT INTO fish_base(name,region,fishing_ground,bait,weather,fish_type,min_size,min_big_size,max_size,base_value) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    fish["name"],
                    fish["region"],
                    fish["fishing_ground"],
                    fish.get("bait", ""),
                    fish.get("weather", ""),
                    fish["fish_type"],
                    fish["min_size"],
                    fish["min_big_size"],
                    fish["max_size"],
                    fish.get("base_value", 50),
                ),
            )
        self.conn.commit()
        self.close()

    def import_lure_data(self, lure_list):
        self.connect()
        self.conn.execute("DELETE FROM lures")
        for lure in lure_list:
            sellable = 1 if lure.get("sellable", False) else 0
            price = lure.get("price") if lure.get("price") is not None else 0
            self.conn.execute(
                "INSERT INTO lures(name,sellable,price) VALUES(?,?,?)",
                (lure["name"], sellable, price),
            )
        self.conn.commit()
        self.close()

    # ---- user ----
    def create_user(self, user_id, group_id):
        self.connect()
        config = load_config()
        ig = config.get("initial_gold", 2000)
        try:
            self.conn.execute(
                "INSERT INTO users(user_id,group_id,gold) VALUES(?,?,?)",
                (user_id, group_id, ig),
            )
            self.conn.commit()
            return True, f"注册成功！初始金币：{ig}"
        except sqlite3.IntegrityError:
            return False, "该用户已在本群注册"
        finally:
            self.close()

    def get_user(self, user_id, group_id):
        self.connect()
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id=? AND group_id=?", (user_id, group_id)
        ).fetchone()
        self.close()
        return dict(row) if row else None

    def update_user_gold(self, user_id, group_id, delta):
        self.connect()
        self.conn.execute(
            "UPDATE users SET gold=gold+? WHERE user_id=? AND group_id=?",
            (delta, user_id, group_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id=? AND group_id=?", (user_id, group_id)
        ).fetchone()
        self.close()
        return dict(row) if row else None

    def set_default_bait(self, user_id, group_id, bait_name):
        self.connect()
        self.conn.execute(
            "UPDATE users SET default_bait=? WHERE user_id=? AND group_id=?",
            (bait_name, user_id, group_id),
        )
        self.conn.commit()
        self.close()

    def get_default_bait(self, user_id, group_id):
        self.connect()
        row = self.conn.execute(
            "SELECT default_bait FROM users WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchone()
        self.close()
        return row["default_bait"] if row else None

    def update_sign_date(self, user_id, group_id):
        self.connect()
        self.conn.execute(
            "UPDATE users SET last_sign_date=? WHERE user_id=? AND group_id=?",
            (date.today().isoformat(), user_id, group_id),
        )
        self.conn.commit()
        self.close()

    def get_last_sign_date(self, user_id, group_id):
        self.connect()
        row = self.conn.execute(
            "SELECT last_sign_date FROM users WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchone()
        self.close()
        return row["last_sign_date"] if row else None

    # ---- fishing CD ----
    def update_fishing_time(self, user_id, group_id, count=1):
        """更新玩家最后钓鱼时间和钓鱼次数"""
        self.connect()
        self.conn.execute(
            "UPDATE users SET last_fishing_time=datetime('now','localtime'), last_fishing_count=? WHERE user_id=? AND group_id=?",
            (count, user_id, group_id),
        )
        self.conn.commit()
        self.close()

    def get_last_fishing_time(self, user_id, group_id):
        """获取玩家最后钓鱼时间"""
        self.connect()
        row = self.conn.execute(
            "SELECT last_fishing_time FROM users WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchone()
        self.close()
        return row["last_fishing_time"] if row else None

    def get_last_fishing_count(self, user_id, group_id):
        """获取玩家上次钓鱼的次数（用于CD计算）"""
        self.connect()
        row = self.conn.execute(
            "SELECT last_fishing_count FROM users WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchone()
        self.close()
        return row["last_fishing_count"] if row else None

    # ---- inventory ----
    def add_lure(self, user_id, group_id, lure_name, qty=1):
        self.connect()
        self.conn.execute(
            "INSERT INTO inventory(user_id,group_id,lure_name,quantity) VALUES(?,?,?,?) ON CONFLICT(user_id,group_id,lure_name) DO UPDATE SET quantity=quantity+?",
            (user_id, group_id, lure_name, qty, qty),
        )
        self.conn.commit()
        self.close()

    def remove_lure(self, user_id, group_id, lure_name, qty=1):
        self.connect()
        row = self.conn.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
            (user_id, group_id, lure_name),
        ).fetchone()
        if not row or row["quantity"] < qty:
            self.close()
            return False
        nq = row["quantity"] - qty
        if nq <= 0:
            self.conn.execute(
                "DELETE FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
                (user_id, group_id, lure_name),
            )
        else:
            self.conn.execute(
                "UPDATE inventory SET quantity=? WHERE user_id=? AND group_id=? AND lure_name=?",
                (nq, user_id, group_id, lure_name),
            )
        self.conn.commit()
        self.close()
        return True

    def get_inventory(self, user_id, group_id):
        self.connect()
        rows = self.conn.execute(
            "SELECT lure_name,quantity FROM inventory WHERE user_id=? AND group_id=? AND quantity>0",
            (user_id, group_id),
        ).fetchall()
        self.close()
        return [dict(r) for r in rows]

    def check_lure(self, user_id, group_id, lure_name):
        self.connect()
        row = self.conn.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
            (user_id, group_id, lure_name),
        ).fetchone()
        self.close()
        return row and row["quantity"] > 0

    # ---- fish caught ----
    def add_caught(
        self, user_id, group_id, fish_name, fish_type, size, is_big, value, locked=0
    ):
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO fish_caught(user_id,group_id,fish_name,fish_type,size,is_big,value,locked) VALUES(?,?,?,?,?,?,?,?)",
            (user_id, group_id, fish_name, fish_type, size, is_big, value, locked),
        )
        fid = cur.lastrowid
        self.conn.commit()
        self.close()
        return fid

    def get_pond(self, user_id, group_id, page=1, page_size=10, fish_type=None, fish_name=None):
        self.connect()
        offset = (page - 1) * page_size
        conditions = ["user_id=? AND group_id=? AND is_sold=0"]
        params = [user_id, group_id]
        if fish_type:
            conditions.append("fish_type=?")
            params.append(fish_type)
        if fish_name:
            conditions.append("fish_name=?")
            params.append(fish_name)
        where = " WHERE " + " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT * FROM fish_caught{where} ORDER BY caught_time DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        total = self.conn.execute(
            f"SELECT COUNT(*) as cnt FROM fish_caught{where}",
            params,
        ).fetchone()["cnt"]
        self.close()
        return [dict(r) for r in rows], total

    def lock_fish(self, fish_id, user_id, group_id):
        self.connect()
        self.conn.execute(
            "UPDATE fish_caught SET locked=1 WHERE id=? AND user_id=? AND group_id=?",
            (fish_id, user_id, group_id),
        )
        self.conn.commit()
        self.close()

    def unlock_fish(self, fish_id, user_id, group_id):
        self.connect()
        self.conn.execute(
            "UPDATE fish_caught SET locked=0 WHERE id=? AND user_id=? AND group_id=?",
            (fish_id, user_id, group_id),
        )
        self.conn.commit()
        self.close()

    def sell_by_name(self, user_id, group_id, fish_name):
        self.connect()
        rows = self.conn.execute(
            "SELECT id,value FROM fish_caught WHERE user_id=? AND group_id=? AND fish_name=? AND locked=0 AND is_sold=0",
            (user_id, group_id, fish_name),
        ).fetchall()
        if not rows:
            self.close()
            return 0, 0
        total = sum(r["value"] for r in rows)
        ids = [r["id"] for r in rows]
        ph = ",".join("?" * len(ids))
        self.conn.execute(f"UPDATE fish_caught SET is_sold=1 WHERE id IN ({ph})", ids)
        self.conn.execute(
            "UPDATE users SET gold=gold+? WHERE user_id=? AND group_id=?",
            (total, user_id, group_id),
        )
        # 如果该鱼也是鱼饵，从背包中清除对应数量
        if self._is_lure_name(fish_name):
            self._remove_lure_silent(user_id, group_id, fish_name, len(ids))
        self.conn.commit()
        self.close()
        return len(ids), total

    def sell_by_id(self, user_id, group_id, fish_id):
        self.connect()
        row = self.conn.execute(
            "SELECT id,fish_name,value,locked FROM fish_caught WHERE id=? AND user_id=? AND group_id=? AND is_sold=0",
            (fish_id, user_id, group_id),
        ).fetchone()
        if not row:
            self.close()
            return None, "未找到该鱼"
        if row["locked"]:
            self.close()
            return None, f"{row['fish_name']} 已锁定"
        self.conn.execute("UPDATE fish_caught SET is_sold=1 WHERE id=?", (fish_id,))
        self.conn.execute(
            "UPDATE users SET gold=gold+? WHERE user_id=? AND group_id=?",
            (row["value"], user_id, group_id),
        )
        # 如果该鱼也是鱼饵，从背包中清除
        if self._is_lure_name(row["fish_name"]):
            self._remove_lure_silent(user_id, group_id, row["fish_name"], 1)
        self.conn.commit()
        self.close()
        return row["value"], row["fish_name"]

    def sell_all(self, user_id, group_id):
        self.connect()
        rows = self.conn.execute(
            "SELECT id,fish_name,value FROM fish_caught WHERE user_id=? AND group_id=? AND locked=0 AND is_sold=0",
            (user_id, group_id),
        ).fetchall()
        if not rows:
            self.close()
            return 0, 0
        total = sum(r["value"] for r in rows)
        ids = [r["id"] for r in rows]
        ph = ",".join("?" * len(ids))
        self.conn.execute(f"UPDATE fish_caught SET is_sold=1 WHERE id IN ({ph})", ids)
        self.conn.execute(
            "UPDATE users SET gold=gold+? WHERE user_id=? AND group_id=?",
            (total, user_id, group_id),
        )
        # 统计需从背包清除的鱼饵类鱼种
        lure_counts = {}
        for r in rows:
            name = r["fish_name"]
            if self._is_lure_name(name):
                lure_counts[name] = lure_counts.get(name, 0) + 1
        for name, qty in lure_counts.items():
            self._remove_lure_silent(user_id, group_id, name, qty)
        self.conn.commit()
        self.close()
        return len(ids), total

    def force_sell(self, user_id, group_id, mode="保留"):
        """强制出售鱼塘中的所有鱼（无视锁定状态）。
        mode: 保留 - 保留所有鱼饵鱼+每种其它鱼留最大的一条（默认）
              仅留唯一 - 每种鱼只保留最大的一条
              无保留 - 全部出售"""
        self.connect()
        rows = self.conn.execute(
            "SELECT id,fish_name,size,value FROM fish_caught WHERE user_id=? AND group_id=? AND is_sold=0",
            (user_id, group_id),
        ).fetchall()
        if not rows:
            self.close()
            return 0, 0, 0

        ids_to_sell = []
        total = 0
        if mode == "无保留":
            ids_to_sell = [r["id"] for r in rows]
            total = sum(r["value"] for r in rows)
        else:
            groups = {}
            for r in rows:
                name = r["fish_name"]
                if name not in groups:
                    groups[name] = []
                groups[name].append(r)
            for name, group_rows in groups.items():
                sorted_rows = sorted(group_rows, key=lambda x: x["size"], reverse=True)
                is_lure = self._is_lure_name(name)
                if mode == "保留" and is_lure:
                    continue
                for r in sorted_rows[1:]:
                    ids_to_sell.append(r["id"])
                    total += r["value"]

        keep_count = len(rows) - len(ids_to_sell)
        if not ids_to_sell:
            self.close()
            return 0, 0, keep_count

        ph = ",".join("?" * len(ids_to_sell))
        self.conn.execute(
            f"UPDATE fish_caught SET is_sold=1 WHERE id IN ({ph})", ids_to_sell
        )
        self.conn.execute(
            "UPDATE users SET gold=gold+? WHERE user_id=? AND group_id=?",
            (total, user_id, group_id),
        )
        lure_counts = {}
        for r in rows:
            if r["id"] in ids_to_sell and self._is_lure_name(r["fish_name"]):
                lure_counts[r["fish_name"]] = lure_counts.get(r["fish_name"], 0) + 1
        for name, qty in lure_counts.items():
            self._remove_lure_silent(user_id, group_id, name, qty)
        self.conn.commit()
        self.close()
        return len(ids_to_sell), total, keep_count
    def get_caught_by_id(self, fish_id, user_id, group_id):
        self.connect()
        row = self.conn.execute(
            "SELECT * FROM fish_caught WHERE id=? AND user_id=? AND group_id=?",
            (fish_id, user_id, group_id),
        ).fetchone()
        self.close()
        return dict(row) if row else None

    # ---- fishing log ----
    def add_log(
        self,
        user_id,
        group_id,
        fish_name,
        fish_type,
        size,
        is_big,
        value,
        bait_used,
        fishing_ground,
        weather,
    ):
        self.connect()
        self.conn.execute(
            "INSERT INTO fishing_log(user_id,group_id,fish_name,fish_type,size,is_big,value,bait_used,fishing_ground,weather) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                group_id,
                fish_name,
                fish_type,
                size,
                is_big,
                value,
                bait_used,
                fishing_ground,
                weather,
            ),
        )
        self.conn.commit()
        self.close()

    def get_log(self, user_id, group_id, page=1, page_size=10):
        self.connect()
        offset = (page - 1) * page_size
        rows = self.conn.execute(
            "SELECT * FROM fishing_log WHERE user_id=? AND group_id=? ORDER BY catch_time DESC LIMIT ? OFFSET ?",
            (user_id, group_id, page_size, offset),
        ).fetchall()
        total = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM fishing_log WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchone()["cnt"]
        self.close()
        return [dict(r) for r in rows], total

    # ---- fish query ----
    def get_all_fish(self):
        self.connect()
        rows = self.conn.execute("SELECT * FROM fish_base").fetchall()
        self.close()
        return [dict(r) for r in rows]

    def get_fish_by_name(self, name):
        self.connect()
        rows = self.conn.execute(
            "SELECT * FROM fish_base WHERE name=?", (name,)
        ).fetchall()
        self.close()
        return [dict(r) for r in rows]

    def get_fish_by_bait(self, bait, weather_type=None, fishing_ground=None):
        self.connect()
        if bait:
            # 支持多鱼饵：bait 字段可能为 "蓝矶沙蚕/苦尔鳗" 格式
            # 匹配条件：bait 为空(通杀)、bait 完全匹配、bait 以 "/" 分隔包含当前饵
            query = "SELECT * FROM fish_base WHERE (bait=? OR bait='' OR bait LIKE ? OR bait LIKE ? OR bait LIKE ?)"
            params = [
                bait,
                bait + "/%",  # bait 开头段匹配：如 "蓝矶沙蚕/..."
                "%/" + bait,  # bait 末尾段匹配：如 ".../蓝矶沙蚕"
                "%/" + bait + "/%",  # bait 中间段匹配：如 ".../蓝矶沙蚕/..."
            ]
        else:
            query = "SELECT * FROM fish_base WHERE 1=1"
            params = []
        if weather_type:
            query += " AND (weather='' OR weather LIKE ?)"
            params.append(f"%{weather_type}%")
        else:
            query += " AND weather=''"
        if fishing_ground:
            query += " AND fishing_ground=?"
            params.append(fishing_ground)
        rows = self.conn.execute(query, params).fetchall()
        self.close()
        return [dict(r) for r in rows]

    def get_fish_by_ground(self, fishing_ground, weather_type=None):
        self.connect()
        query = "SELECT * FROM fish_base WHERE fishing_ground=?"
        params = [fishing_ground]
        if weather_type:
            query += " AND (weather='' OR weather LIKE ?)"
            params.append(f"%{weather_type}%")
        else:
            query += " AND weather=''"
        rows = self.conn.execute(query, params).fetchall()
        self.close()
        return [dict(r) for r in rows]

    def get_caught_names(self, user_id, group_id):
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT fish_name FROM fishing_log WHERE user_id=? AND group_id=?",
            (user_id, group_id),
        ).fetchall()
        self.close()
        return {r["fish_name"] for r in rows}

    # ---- leaderboard ----
    def get_leaderboard(
        self,
        group_id,
        fish_name=None,
        order="DESC",
        fish_type=None,
        page=1,
        page_size=10,
    ):
        """排行榜查询
        - fish_name: 按鱼名查（返回所有记录，上游分页，每页最多10条）
        - fish_type: 按种类查（返回所有记录，由上层分组并限制每种鱼最多3条）
        - 都为空: 返回所有种类
        返回: (records_list, total_count)
        """
        self.connect()
        order_clause = "DESC" if order == "DESC" else "ASC"
        if fish_name:
            # 按鱼名查：返回所有记录（每条钓鱼记录独立排行）
            query = f"SELECT user_id,fish_name,size,catch_time FROM fishing_log WHERE group_id=? AND fish_name=? ORDER BY size {order_clause}"
            rows = self.conn.execute(query, (group_id, fish_name)).fetchall()
            total = self.conn.execute(
                "SELECT COUNT(*) FROM fishing_log WHERE group_id=? AND fish_name=?",
                (group_id, fish_name),
            ).fetchone()[0]
        elif fish_type:
            # 按种类查：返回所有记录，不分组
            query = f"SELECT user_id,fish_name,fish_type,size,catch_time FROM fishing_log WHERE group_id=? AND fish_type=? ORDER BY fish_name,size {order_clause}"
            rows = self.conn.execute(query, (group_id, fish_type)).fetchall()
            total = self.conn.execute(
                "SELECT COUNT(*) FROM fishing_log WHERE group_id=? AND fish_type=?",
                (group_id, fish_type),
            ).fetchone()[0]
        else:
            # 全部
            query = f"SELECT user_id,fish_name,fish_type,size,catch_time FROM fishing_log WHERE group_id=? ORDER BY CASE fish_type WHEN '鱼皇' THEN 0 WHEN '鱼王' THEN 1 ELSE 2 END, fish_name, size {order_clause}"
            rows = self.conn.execute(query, (group_id,)).fetchall()
            total = self.conn.execute(
                "SELECT COUNT(*) FROM fishing_log WHERE group_id=?", (group_id,)
            ).fetchone()[0]
        self.close()
        return [dict(r) for r in rows], total

    def get_extreme(self, group_id, fish_name):
        self.connect()
        max_r = self.conn.execute(
            "SELECT user_id,MAX(size) as size FROM fishing_log WHERE group_id=? AND fish_name=? GROUP BY fish_name",
            (group_id, fish_name),
        ).fetchone()
        min_r = self.conn.execute(
            "SELECT user_id,MIN(size) as size FROM fishing_log WHERE group_id=? AND fish_name=? GROUP BY fish_name",
            (group_id, fish_name),
        ).fetchone()
        self.close()
        return {
            "max_user": max_r["user_id"] if max_r else None,
            "max_size": max_r["size"] if max_r else None,
            "min_user": min_r["user_id"] if min_r else None,
            "min_size": min_r["size"] if min_r else None,
        }

    # ---- weather ----
    # 天气每12小时变更一次，每日下午6点切换 (slot=0: 00:00-17:59, slot=1: 18:00-23:59)

    @staticmethod
    def _current_slot():
        """返回当前所属的天气时段: 0=上午(00:00-17:59), 1=下午(18:00-23:59)"""
        return 1 if datetime.now().hour >= 18 else 0

    def generate_weather(self, weather_date, slot, weather_type=None):
        if weather_type is None:
            import random

            config = load_config()
            wts = config.get("weather_types", ["晴朗"])
            weather_type = random.choice(wts)
        self.connect()
        try:
            self.conn.execute(
                "INSERT INTO weather(weather_date,slot,weather_type) VALUES(?,?,?)",
                (weather_date, slot, weather_type),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
        self.close()
        return weather_type

    def get_weather(self, start_date=None, days=4):
        from datetime import date as dt, timedelta

        if start_date is None:
            start_date = dt.today().isoformat()
        sd = dt.fromisoformat(start_date)
        dates = [(sd + timedelta(days=i)).isoformat() for i in range(days)]
        self.connect()
        ph = ",".join("?" * len(dates))
        rows = self.conn.execute(
            f"SELECT weather_date,slot,weather_type FROM weather WHERE weather_date IN ({ph}) ORDER BY weather_date,slot",
            dates,
        ).fetchall()
        self.close()
        wmap = {}
        for r in rows:
            wmap.setdefault(r["weather_date"], {})[r["slot"]] = r["weather_type"]
        result = []
        for d in dates:
            for slot in (0, 1):
                if d not in wmap or slot not in wmap.get(d, {}):
                    if d not in wmap:
                        wmap[d] = {}
                    wmap[d][slot] = self.generate_weather(d, slot)
                wtype = wmap[d][slot]
                label = "白天" if slot == 0 else "晚上"
                result.append(
                    {"date": d, "slot": slot, "label": f"{d} {label}", "weather": wtype}
                )
        return result

    def get_today_weather(self):
        """返回当前时段的天气"""
        from datetime import date as dt

        today = dt.today().isoformat()
        slot = self._current_slot()
        self.connect()
        row = self.conn.execute(
            "SELECT weather_type FROM weather WHERE weather_date=? AND slot=?",
            (today, slot),
        ).fetchone()
        self.close()
        if row:
            return {"date": today, "slot": slot, "weather": row["weather_type"]}
        return {
            "date": today,
            "slot": slot,
            "weather": self.generate_weather(today, slot),
        }

    def set_weather(self, weather_date, slot, weather_type):
        self.connect()
        self.conn.execute(
            "INSERT OR REPLACE INTO weather(weather_date,slot,weather_type,created_at) VALUES(?,?,?,datetime('now','localtime'))",
            (weather_date, slot, weather_type),
        )
        self.conn.commit()
        self.close()

    # ---- shop ----
    def get_shop_lures(self):
        self.connect()
        rows = self.conn.execute("SELECT * FROM lures WHERE sellable=1").fetchall()
        self.close()
        return [dict(r) for r in rows]

    def get_lure_by_name(self, name):
        self.connect()
        row = self.conn.execute("SELECT * FROM lures WHERE name=?", (name,)).fetchone()
        self.close()
        return dict(row) if row else None

    def get_all_lures(self):
        self.connect()
        rows = self.conn.execute("SELECT * FROM lures").fetchall()
        self.close()
        return [dict(r) for r in rows]

    def is_fish_a_lure(self, fish_name):
        """检查鱼名是否也存在于鱼饵表中（即可作为鱼饵使用的鱼）"""
        self.connect()
        row = self.conn.execute(
            "SELECT name FROM lures WHERE name=?", (fish_name,)
        ).fetchone()
        self.close()
        return row is not None

    def _is_lure_name(self, fish_name):
        """内部方法：在同一连接内判断鱼名是否也是鱼饵（不自带 connect/close）"""
        row = self.conn.execute(
            "SELECT name FROM lures WHERE name=?", (fish_name,)
        ).fetchone()
        return row is not None

    def consume_pond_fish(self, user_id, group_id, fish_name, count=1):
        """当鱼被用作鱼饵钓鱼时，从鱼塘中消耗对应数量的鱼（标记为已出售）。
        优先消耗未锁定的鱼，然后消耗已锁定的鱼（因为用作鱼饵是主动行为）。"""
        self.connect()
        remaining = count
        # 先消耗未锁定的
        if remaining > 0:
            rows = self.conn.execute(
                "SELECT id FROM fish_caught WHERE user_id=? AND group_id=? AND fish_name=? AND is_sold=0 AND locked=0 ORDER BY caught_time DESC LIMIT ?",
                (user_id, group_id, fish_name, remaining),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                ph = ",".join("?" * len(ids))
                self.conn.execute(
                    f"UPDATE fish_caught SET is_sold=1 WHERE id IN ({ph})", ids
                )
                remaining -= len(ids)
        # 如果还不够，再消耗已锁定的（锁定只防误售，用作鱼饵是主动行为）
        if remaining > 0:
            rows = self.conn.execute(
                "SELECT id FROM fish_caught WHERE user_id=? AND group_id=? AND fish_name=? AND is_sold=0 AND locked=1 ORDER BY caught_time DESC LIMIT ?",
                (user_id, group_id, fish_name, remaining),
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                ph = ",".join("?" * len(ids))
                self.conn.execute(
                    f"UPDATE fish_caught SET is_sold=1 WHERE id IN ({ph})", ids
                )
        self.conn.commit()
        self.close()

    def _remove_lure_silent(self, user_id, group_id, lure_name, qty=1):
        """内部方法：在同一连接内从背包移除鱼饵（不自带 connect/close），不清零则删除记录"""
        row = self.conn.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
            (user_id, group_id, lure_name),
        ).fetchone()
        if not row:
            return
        nq = row["quantity"] - qty
        if nq <= 0:
            self.conn.execute(
                "DELETE FROM inventory WHERE user_id=? AND group_id=? AND lure_name=?",
                (user_id, group_id, lure_name),
            )
        else:
            self.conn.execute(
                "UPDATE inventory SET quantity=? WHERE user_id=? AND group_id=? AND lure_name=?",
                (nq, user_id, group_id, lure_name),
            )

    # ---- krypton ----
    def add_krypton(self, user_id, group_id, amount):
        self.connect()
        self.conn.execute(
            "INSERT INTO krypton_log(user_id,group_id,amount) VALUES(?,?,?)",
            (user_id, group_id, amount),
        )
        self.conn.commit()
        self.close()

    def get_krypton_log(self, user_id, group_id):
        self.connect()
        rows = self.conn.execute(
            "SELECT * FROM krypton_log WHERE user_id=? AND group_id=? ORDER BY created_at DESC",
            (user_id, group_id),
        ).fetchall()
        self.close()
        return [dict(r) for r in rows]

    # ---- handbook ----
    def get_handbook(self, user_id, group_id, region=None, fishing_ground=None,
                     fish_name=None, bait=None, fish_type=None, weather=None):
        """获取图鉴数据，支持按地区和/或钓场筛选。
        返回按 region→fishing_ground→fish_type→name 排序的列表，
        包含 bait、base_value、min_size、max_size 等信息。"""
        self.connect()
        query = "SELECT DISTINCT name,fish_type,region,fishing_ground,bait,weather,base_value,min_size,min_big_size,max_size FROM fish_base"
        conditions = []
        params = []
        if region:
            conditions.append("region=?")
            params.append(region)
        if fishing_ground:
            conditions.append("fishing_ground=?")
            params.append(fishing_ground)
        if fish_name:
            conditions.append("name LIKE ?")
            params.append(f"%{fish_name}%")
        if bait:
            conditions.append("(bait=? OR bait LIKE ? OR bait LIKE ? OR bait LIKE ?)")
            params.extend([bait, bait + "/%", "%/" + bait, "%/" + bait + "/%"])
        if fish_type:
            conditions.append("fish_type=?")
            params.append(fish_type)
        if weather:
            conditions.append("weather LIKE ?")
            params.append(f"%{weather}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY region, fishing_ground, fish_type, name"
        bf = self.conn.execute(query, params).fetchall()
        bf = [dict(r) for r in bf]
        caught = set()
        q = "SELECT DISTINCT fish_name FROM fishing_log WHERE user_id=? AND group_id=?"
        cq_params = [user_id, group_id]
        if region:
            q += " AND fishing_ground IN (SELECT DISTINCT fishing_ground FROM fish_base WHERE region=?)"
            cq_params.append(region)
        if fishing_ground:
            q += " AND fishing_ground=?"
            cq_params.append(fishing_ground)
        rows = self.conn.execute(q, cq_params).fetchall()
        caught = {r["fish_name"] for r in rows}
        self.close()
        for f in bf:
            f["obtained"] = f["name"] in caught
        return bf

    def get_distinct_regions(self):
        """获取所有不重复的区域列表"""
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT region FROM fish_base ORDER BY region"
        ).fetchall()
        self.close()
        return [r["region"] for r in rows]

    def get_distinct_grounds(self):
        """获取所有不重复的钓场列表"""
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT fishing_ground FROM fish_base ORDER BY fishing_ground"
        ).fetchall()
        self.close()
        return [r["fishing_ground"] for r in rows]

    def get_distinct_baits(self):
        """获取所有不重复的鱼饵名称列表（拆分 / 分隔的多鱼饵）"""
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT bait FROM fish_base WHERE bait != ''"
        ).fetchall()
        self.close()
        baits = set()
        for r in rows:
            for b in r["bait"].split("/"):
                b = b.strip()
                if b:
                    baits.add(b)
        return sorted(baits)

    def get_all_fish_names(self):
        """获取所有鱼名列表"""
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT name FROM fish_base ORDER BY name"
        ).fetchall()
        self.close()
        return [r["name"] for r in rows]


    def get_handbook_user_ranking(self, group_id, fish_name, user_id=None):
        """获取当前用户在某个鱼种的排行（按尺寸降序）"""
        self.connect()
        if user_id:
            row = self.conn.execute(
                """
                SELECT COUNT(*)+1 as rank FROM fishing_log
                WHERE group_id=? AND fish_name=? AND size > (
                    SELECT MAX(size) FROM fishing_log WHERE group_id=? AND fish_name=? AND user_id=?
                )
            """,
                (group_id, fish_name, group_id, fish_name, user_id),
            ).fetchone()
        else:
            row = {"rank": None}
        self.close()
        return row["rank"] if row else None



    def get_distinct_weathers(self):
        """获取所有不重复的天气列表（从 fish_base 表的 weather 字段拆分 / 分隔的多天气）"""
        self.connect()
        rows = self.conn.execute(
            "SELECT DISTINCT weather FROM fish_base WHERE weather != ''"
        ).fetchall()
        self.close()
        weathers = set()
        for r in rows:
            for w in r["weather"].split("/"):
                w = w.strip()
                if w:
                    weathers.add(w)
        return sorted(weathers)

    def get_unobtained(self, user_id, group_id, region=None, fishing_ground=None,
                       bait=None, weather=None):
        """获取未获取的鱼列表，支持按地区和/或钓场、鱼饵、天气筛选。
        返回按 region→fishing_ground→fish_type→name 排序的列表，
        包含 bait、base_value、min_size、max_size 等信息。
        仅返回该用户尚未钓到的鱼。"""
        self.connect()
        query = "SELECT DISTINCT name,fish_type,region,fishing_ground,bait,weather,base_value,min_size,min_big_size,max_size FROM fish_base"
        conditions = []
        params = []
        if region:
            conditions.append("region=?")
            params.append(region)
        if fishing_ground:
            conditions.append("fishing_ground=?")
            params.append(fishing_ground)
        if bait:
            conditions.append("(bait=? OR bait LIKE ? OR bait LIKE ? OR bait LIKE ?)")
            params.extend([bait, bait + "/%", "%/" + bait, "%/" + bait + "/%"])
        if weather:
            conditions.append("weather LIKE ?")
            params.append(f"%{weather}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY region, fishing_ground, fish_type, name"
        bf = self.conn.execute(query, params).fetchall()
        bf = [dict(r) for r in bf]

        # 获取用户已钓到的鱼名
        cq = "SELECT DISTINCT fish_name FROM fishing_log WHERE user_id=? AND group_id=?"
        cq_params = [user_id, group_id]
        rows = self.conn.execute(cq, cq_params).fetchall()
        caught = {r["fish_name"] for r in rows}
        self.close()

        # 仅返回未钓到的鱼
        result = [f for f in bf if f["name"] not in caught]
        for f in result:
            f["obtained"] = False
        return result

    # ---- plugin config ----
    def get_config(self, key):
        """获取持久化配置值"""
        self.connect()
        row = self.conn.execute(
            "SELECT value FROM plugin_config WHERE key=?", (key,)
        ).fetchone()
        self.close()
        if row:
            import json
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        return None

    def set_config(self, key, value):
        """设置持久化配置值"""
        import json
        self.connect()
        self.conn.execute(
            "INSERT OR REPLACE INTO plugin_config(key,value) VALUES(?,?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()
        self.close()

    # ---- hot reload ----
    def reload_lure_data(self, lure_list):
        """热更新鱼饵数据"""
        self.connect()
        for lure in lure_list:
            sellable = 1 if lure.get("sellable", False) else 0
            price = lure.get("price") if lure.get("price") is not None else 0
            self.conn.execute(
                "INSERT OR REPLACE INTO lures(id,name,sellable,price) VALUES((SELECT id FROM lures WHERE name=?),?,?,?)",
                (lure["name"], lure["name"], sellable, price),
            )
        self.conn.commit()
        self.close()

    def reload_fish_data(self, fish_list):
        """热更新鱼基础数据，同步 bait、weather、fish_type、尺寸和基础价值等字段"""
        self.connect()
        for fish in fish_list:
            self.conn.execute(
                "UPDATE fish_base SET bait=?, weather=?, fish_type=?, min_size=?, min_big_size=?, max_size=?, base_value=? WHERE name=?",
                (
                    fish.get("bait", ""),
                    fish.get("weather", ""),
                    fish.get("fish_type", "普通鱼"),
                    fish.get("min_size", 0),
                    fish.get("min_big_size", 0),
                    fish.get("max_size", 0),
                    fish.get("base_value", 50),
                    fish["name"],
                ),
            )
        self.conn.commit()
        self.close()


_db_instance = None


def get_db(db_path=None, data_dir=None):
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path, data_dir=data_dir)
    return _db_instance


def get_db_path():
    return get_db().db_path


def init_db_with_path(db_path, data_dir=None):
    global _db_instance
    _db_instance = Database(db_path, data_dir=data_dir)
    return _db_instance
