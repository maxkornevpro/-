import sqlite3
import json
from datetime import datetime, timedelta
from config import DB_FILE, DEVICE_LIMIT_DEFAULT

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_tables()

    def _column_exists(self, table_name, column_name):
        self.cursor.execute(f"PRAGMA table_info({table_name})")
        columns = self.cursor.fetchall()
        return any(column[1] == column_name for column in columns)

    def _ensure_column(self, table_name, column_name, definition):
        if not self._column_exists(table_name, column_name):
            self.cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
    
    def _init_tables(self):
        # Users table - add referral fields
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_used INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                referrer_id INTEGER,
                balance INTEGER DEFAULT 0,
                bonus_hours INTEGER DEFAULT 0,
                device_limit INTEGER DEFAULT {default_devices},
                FOREIGN KEY (referrer_id) REFERENCES users(user_id)
            )
        """.format(default_devices=DEVICE_LIMIT_DEFAULT))
        self.conn.commit()
        
        # Subscriptions table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                duration_type TEXT,
                price INTEGER,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        self.conn.commit()
        
        # VPN Keys table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS vpn_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                uuid TEXT UNIQUE,
                public_key TEXT,
                private_key TEXT,
                short_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                vless_link TEXT,
                server TEXT DEFAULT 'estonia',
                email TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        self.conn.commit()
        
        # Orders table (for purchase requests)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                duration_type TEXT,
                price INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                invoice_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        self.conn.commit()
        
        # Migrate old databases in place.
        self._ensure_column("users", "trial_used", "INTEGER DEFAULT 0")
        self._ensure_column("users", "is_active", "INTEGER DEFAULT 1")
        self._ensure_column("users", "referrer_id", "INTEGER")
        self._ensure_column("users", "balance", "INTEGER DEFAULT 0")
        self._ensure_column("users", "bonus_hours", "INTEGER DEFAULT 0")
        self._ensure_column("users", "device_limit", f"INTEGER DEFAULT {DEVICE_LIMIT_DEFAULT}")

        self._ensure_column("subscriptions", "is_active", "INTEGER DEFAULT 1")

        self._ensure_column("vpn_keys", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        self._ensure_column("vpn_keys", "expires_at", "TIMESTAMP")
        self._ensure_column("vpn_keys", "is_active", "INTEGER DEFAULT 1")
        self._ensure_column("vpn_keys", "vless_link", "TEXT")
        self._ensure_column("vpn_keys", "server", "TEXT DEFAULT 'estonia'")
        self._ensure_column("vpn_keys", "email", "TEXT")

        self._ensure_column("orders", "invoice_id", "INTEGER")
        self._ensure_column("orders", "paid_at", "TIMESTAMP")

        self.conn.commit()
    
    def add_user(self, user_id, username, first_name, referrer_id=None):
        self.cursor.execute(
            """INSERT OR IGNORE INTO users 
               (user_id, username, first_name, referrer_id) 
               VALUES (?, ?, ?, ?)""",
            (user_id, username, first_name, referrer_id)
        )
        self.conn.commit()
        
        # If has referrer, add bonus time to referrer
        if referrer_id:
            self.add_referral_bonus(referrer_id)
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def get_user_by_username(self, username):
        """Найти пользователя по @username (без учёта регистра)."""
        username = (username or "").lstrip("@").strip()
        if not username:
            return None
        self.cursor.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        )
        return self.cursor.fetchone()
    
    def has_used_trial(self, user_id):
        self.cursor.execute("SELECT trial_used FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 1
    
    def set_trial_used(self, user_id):
        self.cursor.execute(
            "UPDATE users SET trial_used = 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()
    
    def add_subscription(self, user_id, duration_type, price, days):
        start_date = datetime.now()
        if duration_type == "forever":
            end_date = datetime(2099, 12, 31)
        else:
            end_date = start_date + timedelta(days=days)
        
        self.cursor.execute(
            """INSERT INTO subscriptions (user_id, start_date, end_date, duration_type, price)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, start_date, end_date, duration_type, price)
        )
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_active_subscription(self, user_id):
        self.cursor.execute(
            """SELECT * FROM subscriptions 
               WHERE user_id = ? AND is_active = 1 AND end_date > ?
               ORDER BY end_date DESC LIMIT 1""",
            (user_id, datetime.now())
        )
        return self.cursor.fetchone()
    
    def add_vpn_key(self, user_id, uuid, public_key, private_key, short_id, expires_at, vless_link, server='estonia', email=None):
        self.cursor.execute(
            """INSERT INTO vpn_keys (user_id, uuid, public_key, private_key, short_id, expires_at, vless_link, server, email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, uuid, public_key, private_key, short_id, expires_at, vless_link, server, email)
        )
        self.conn.commit()
        return self.cursor.lastrowid

    def get_active_key(self, user_id):
        """Самый свежий активный ключ пользователя (или None)."""
        self.cursor.execute(
            """SELECT * FROM vpn_keys WHERE user_id = ? AND is_active = 1
               AND (expires_at > ? OR expires_at IS NULL)
               ORDER BY id DESC LIMIT 1""",
            (user_id, datetime.now())
        )
        return self.cursor.fetchone()

    def get_active_key_email(self, user_id):
        """Email активного ключа (нужен для 3x-ui: счётчик устройств / лимиты)."""
        row = self.get_active_key(user_id)
        if not row:
            return None
        # email — последняя добавленная колонка vpn_keys
        return row[-1]
    
    def get_user_keys(self, user_id):
        self.cursor.execute(
            """SELECT * FROM vpn_keys WHERE user_id = ? AND is_active = 1 
               AND (expires_at > ? OR expires_at IS NULL)""",
            (user_id, datetime.now())
        )
        return self.cursor.fetchall()
    
    def get_expired_keys(self):
        """Get all expired but still active keys."""
        self.cursor.execute(
            """SELECT * FROM vpn_keys 
               WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at <= ?""",
            (datetime.now(),)
        )
        return self.cursor.fetchall()
    
    def deactivate_key(self, key_id):
        """Deactivate a VPN key by ID."""
        self.cursor.execute(
            "UPDATE vpn_keys SET is_active = 0 WHERE id = ?",
            (key_id,)
        )
        self.conn.commit()

    def update_key_expiry(self, key_id, expires_at):
        """Обновить дату окончания ключа (используется при продлении оплатой).

        expires_at — datetime или None (None = бессрочно).
        """
        self.cursor.execute(
            "UPDATE vpn_keys SET expires_at = ? WHERE id = ?",
            (expires_at, key_id)
        )
        self.conn.commit()
    
    def create_order(self, user_id, username, duration_type, price, invoice_id=None):
        self.cursor.execute(
            """INSERT INTO orders (user_id, username, duration_type, price, invoice_id)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, duration_type, price, invoice_id)
        )
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_pending_orders(self):
        self.cursor.execute(
            "SELECT * FROM orders WHERE status = 'pending' ORDER BY created_at"
        )
        return self.cursor.fetchall()
    
    def mark_order_paid(self, order_id):
        self.cursor.execute(
            "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
            (datetime.now(), order_id)
        )
        self.conn.commit()
    
    def is_user_blocked(self, user_id):
        """Check if user is blocked."""
        self.cursor.execute("SELECT is_active FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result and result[0] == 0
    
    def block_user(self, user_id):
        """Block user."""
        self.cursor.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )
        # Also deactivate all their keys
        self.cursor.execute(
            "UPDATE vpn_keys SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()
    
    def unblock_user(self, user_id):
        """Unblock user."""
        self.cursor.execute(
            "UPDATE users SET is_active = 1 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()
    
    def block_key(self, key_id):
        """Block specific key."""
        self.cursor.execute(
            "UPDATE vpn_keys SET is_active = 0 WHERE id = ?",
            (key_id,)
        )
        self.conn.commit()
    
    def unblock_key(self, key_id):
        """Unblock specific key."""
        self.cursor.execute(
            "UPDATE vpn_keys SET is_active = 1 WHERE id = ?",
            (key_id,)
        )
        self.conn.commit()
    
    # ==================== REFERRAL SYSTEM ====================
    
    def add_referral_bonus(self, referrer_id):
        """Add +6 hours bonus to referrer."""
        self.cursor.execute(
            "UPDATE users SET bonus_hours = bonus_hours + 6 WHERE user_id = ?",
            (referrer_id,)
        )
        self.conn.commit()
    
    def add_purchase_cashback(self, referrer_id, purchase_amount):
        """Add 2% cashback from purchase to referrer balance."""
        cashback = int(purchase_amount * 0.02)
        self.cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (cashback, referrer_id)
        )
        self.conn.commit()
        return cashback
    
    def get_user_balance(self, user_id):
        """Get user balance and bonus hours."""
        self.cursor.execute(
            "SELECT balance, bonus_hours, referrer_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        if result:
            return {
                'balance': result[0] or 0,
                'bonus_hours': result[1] or 0,
                'referrer_id': result[2]
            }
        return {'balance': 0, 'bonus_hours': 0, 'referrer_id': None}
    
    def get_referral_count(self, user_id):
        """Get count of users referred by this user."""
        self.cursor.execute(
            "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
            (user_id,)
        )
        return self.cursor.fetchone()[0]
    
    def use_balance_for_purchase(self, user_id, amount):
        """Deduct from user balance for purchase."""
        self.cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, user_id, amount)
        )
        self.conn.commit()
        return self.cursor.rowcount > 0

    # ==================== УСТРОЙСТВА ====================

    def get_device_limit(self, user_id):
        """Сколько устройств разрешено пользователю (одновременных подключений)."""
        self.cursor.execute("SELECT device_limit FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        if not result or result[0] is None:
            return DEVICE_LIMIT_DEFAULT
        return int(result[0])

    def add_device_slots(self, user_id, count):
        """Докупить устройства: увеличить лимит на count. Возвращает новый лимит."""
        # На случай, если строки пользователя ещё нет — создаём с дефолтом.
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, device_limit) VALUES (?, ?)",
            (user_id, DEVICE_LIMIT_DEFAULT)
        )
        self.cursor.execute(
            "UPDATE users SET device_limit = COALESCE(device_limit, ?) + ? WHERE user_id = ?",
            (DEVICE_LIMIT_DEFAULT, count, user_id)
        )
        self.conn.commit()
        return self.get_device_limit(user_id)
    
    # ==================== ADMIN/STATS ====================
    
    def get_all_users(self):
        self.cursor.execute("SELECT * FROM users ORDER BY joined_at DESC")
        return self.cursor.fetchall()
    
    def get_all_user_ids(self):
        """Get all user IDs for broadcasting."""
        self.cursor.execute("SELECT user_id FROM users WHERE is_active = 1")
        return [row[0] for row in self.cursor.fetchall()]
    
    def get_blocked_users(self):
        """Get list of blocked users."""
        self.cursor.execute("SELECT * FROM users WHERE is_active = 0")
        return self.cursor.fetchall()
    
    def get_stats(self):
        stats = {}
        now = datetime.now()
        self.cursor.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = self.cursor.fetchone()[0]

        # Активные подписки = пользователи, у кого срок ещё не истёк.
        self.cursor.execute(
            "SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE is_active = 1 AND end_date > ?",
            (now,)
        )
        stats['active_subs'] = self.cursor.fetchone()[0]

        # Активные ключи = включённые и не истёкшие.
        self.cursor.execute(
            "SELECT COUNT(*) FROM vpn_keys WHERE is_active = 1 AND (expires_at > ? OR expires_at IS NULL)",
            (now,)
        )
        stats['active_keys'] = self.cursor.fetchone()[0]

        return stats
    
    def close(self):
        self.conn.close()
