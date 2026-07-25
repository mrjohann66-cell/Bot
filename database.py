import sqlite3
import os
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    joined_at TEXT,
                    vip_expire TEXT
                )
            """)
            
            # Videos table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    code TEXT PRIMARY KEY,
                    photo_id TEXT,
                    caption TEXT,
                    price INTEGER,
                    created_at TEXT
                )
            """)
            
            # Video qualities
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_code TEXT,
                    quality TEXT,
                    file_id TEXT,
                    FOREIGN KEY(video_code) REFERENCES videos(code) ON DELETE CASCADE
                )
            """)
            
            # Purchased videos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    video_code TEXT,
                    bought_at TEXT,
                    UNIQUE(user_id, video_code)
                )
            """)

            # Pending payments
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_payments (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    payment_type TEXT,
                    video_code TEXT,
                    vip_plan TEXT,
                    selected_quality TEXT,
                    amount INTEGER,
                    created_at TEXT
                )
            """)

            # Bot settings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Default settings
            defaults = {
                "card_number": "9860 3501 4870 6350",
                "vip_1w": "10000",
                "vip_1m": "25000",
                "vip_6m": "50000"
            }
            for k, v in defaults.items():
                cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

            conn.commit()

    # User Methods
    def add_user(self, user_id: int, username: str, full_name: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            joined = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, full_name, joined))
            conn.commit()

    def is_user_vip(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT vip_expire FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return False
            try:
                expire_dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                return expire_dt > datetime.now()
            except Exception:
                return False

    def add_vip_user(self, user_id: int, days: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            expire_dt = datetime.now() + timedelta(days=days)
            expire_str = expire_dt.strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE users SET vip_expire = ? WHERE user_id = ?", (expire_str, user_id))
            conn.commit()

    def get_all_users(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, username, full_name, vip_expire FROM users")
            return cursor.fetchall()

    # Video Methods
    def get_video_by_code(self, code: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT code, photo_id, caption, price FROM videos WHERE code = ?", (code,))
            row = cursor.fetchone()
            if row:
                return {"code": row[0], "photo_id": row[1], "caption": row[2], "price": row[3]}
            return None

    def get_video_qualities(self, code: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quality, file_id FROM video_files WHERE video_code = ?", (code,))
            rows = cursor.fetchall()
            return [{"quality": r[0], "file_id": r[1]} for r in rows]

    def get_video_file_by_quality(self, code: str, quality: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quality, file_id FROM video_files WHERE video_code = ? AND quality = ?", (code, quality))
            row = cursor.fetchone()
            if row:
                return {"quality": row[0], "file_id": row[1]}
            return None

    def add_video(self, code: str, photo_id: str, caption: str, price: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT OR REPLACE INTO videos (code, photo_id, caption, price, created_at) VALUES (?, ?, ?, ?, ?)",
                           (code, photo_id, caption, price, now))
            conn.commit()

    def add_video_file(self, video_code: str, quality: str, file_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO video_files (video_code, quality, file_id) VALUES (?, ?, ?)",
                           (video_code, quality, file_id))
            conn.commit()

    def delete_video(self, code: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM video_files WHERE video_code = ?", (code,))
            cursor.execute("DELETE FROM videos WHERE code = ?", (code,))
            conn.commit()

    # Purchase Methods
    def has_user_bought_video(self, user_id: int, video_code: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM purchases WHERE user_id = ? AND video_code = ?", (user_id, video_code))
            return cursor.fetchone() is not None

    def add_purchase(self, user_id: int, video_code: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT OR IGNORE INTO purchases (user_id, video_code, bought_at) VALUES (?, ?, ?)",
                           (user_id, video_code, now))
            conn.commit()

    def get_user_purchased_videos(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.code, v.caption, v.price 
                FROM purchases p 
                JOIN videos v ON p.video_code = v.code 
                WHERE p.user_id = ?
            """, (user_id,))
            return cursor.fetchall()

    # Settings Methods
    def get_setting(self, key: str, default: str = "") -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

    # Pending Payment Methods
    def create_pending_payment(self, payment_id: str, user_id: int, payment_type: str, video_code: str = "", vip_plan: str = "", selected_quality: str = "", amount: int = 0):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO pending_payments (id, user_id, payment_type, video_code, vip_plan, selected_quality, amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (payment_id, user_id, payment_type, video_code, vip_plan, selected_quality, amount, now))
            conn.commit()

    def get_pending_payment(self, payment_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, payment_type, video_code, vip_plan, selected_quality, amount FROM pending_payments WHERE id = ?", (payment_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0], "user_id": row[1], "payment_type": row[2],
                    "video_code": row[3], "vip_plan": row[4], "selected_quality": row[5], "amount": row[6]
                }
            return None

    def delete_pending_payment(self, payment_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM pending_payments WHERE id = ?", (payment_id,))
            conn.commit()