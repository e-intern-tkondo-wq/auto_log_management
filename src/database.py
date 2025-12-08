"""
データベーススキーマ定義と初期化
SQLiteを使用したログ監視システムのデータベース管理
"""
import sqlite3
import os
from datetime import datetime

# Python 3.12+ の datetime adapter 警告を回避
def adapt_datetime(dt):
    return dt.isoformat()

def convert_datetime(s):
    return datetime.fromisoformat(s.decode())

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("DATETIME", convert_datetime)


class Database:
    """SQLiteデータベース管理クラス"""
    
    def __init__(self, db_path: str = "db/monitor.db"):
        """
        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """データベースを初期化し、テーブルを作成"""
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # 1. regex_patterns テーブル（パターンマスタ）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS regex_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regex_rule TEXT UNIQUE,
                manual_regex_rule TEXT UNIQUE,
                sample_message TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'normal',
                severity TEXT,
                note TEXT,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                total_count INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK ((regex_rule IS NOT NULL AND manual_regex_rule IS NULL) OR 
                       (regex_rule IS NULL AND manual_regex_rule IS NOT NULL))
            )
        """)
        
        # 既存テーブルのマイグレーション（regex_rule の NOT NULL 制約を削除）
        try:
            # 既存テーブルの構造を確認
            cursor.execute("PRAGMA table_info(regex_patterns)")
            columns = cursor.fetchall()
            regex_rule_not_null = any(col[1] == 'regex_rule' and col[3] == 1 for col in columns)
            has_manual_regex = any(col[1] == 'manual_regex_rule' for col in columns)
            
            # regex_rule が NOT NULL の場合、テーブルを再作成
            if regex_rule_not_null or not has_manual_regex:
                # 1. 新しいテーブルを作成
                cursor.execute("""
                    CREATE TABLE regex_patterns_migrated (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        regex_rule TEXT UNIQUE,
                        manual_regex_rule TEXT UNIQUE,
                        sample_message TEXT NOT NULL,
                        label TEXT NOT NULL DEFAULT 'normal',
                        severity TEXT,
                        note TEXT,
                        first_seen_at DATETIME NOT NULL,
                        last_seen_at DATETIME NOT NULL,
                        total_count INTEGER NOT NULL DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        CHECK ((regex_rule IS NOT NULL AND manual_regex_rule IS NULL) OR 
                               (regex_rule IS NULL AND manual_regex_rule IS NOT NULL))
                    )
                """)
                
                # 2. 既存データをコピー
                cursor.execute("""
                    INSERT INTO regex_patterns_migrated 
                    SELECT id, regex_rule, NULL, sample_message, label, severity, note,
                           first_seen_at, last_seen_at, total_count, created_at, updated_at
                    FROM regex_patterns
                """)
                
                # 3. 外部キー制約を一時的に無効化
                cursor.execute("PRAGMA foreign_keys=OFF")
                
                # 4. 古いテーブルを削除して新しいテーブルに置き換え
                cursor.execute("DROP TABLE regex_patterns")
                cursor.execute("ALTER TABLE regex_patterns_migrated RENAME TO regex_patterns")
                
                # 5. インデックスを再作成
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_regex_patterns_regex_rule ON regex_patterns(regex_rule) WHERE regex_rule IS NOT NULL")
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_regex_patterns_manual_regex_rule ON regex_patterns(manual_regex_rule) WHERE manual_regex_rule IS NOT NULL")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_regex_patterns_label ON regex_patterns(label)")
                
                # 6. 外部キー制約を再有効化
                cursor.execute("PRAGMA foreign_keys=ON")
                
                self.conn.commit()
        except sqlite3.OperationalError as e:
            # 既にマイグレーション済みの場合はスキップ
            if "already exists" not in str(e) and "no such table" not in str(e):
                print(f"Warning: Migration issue: {e}", file=__import__('sys').stderr)
            pass
        
        # 2. log_entries テーブル（ログ本体）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS log_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME NOT NULL,
                host TEXT,
                component TEXT,
                raw_line TEXT NOT NULL,
                message TEXT NOT NULL,
                pattern_id INTEGER,
                is_known INTEGER DEFAULT 0,
                is_manual_mapped INTEGER DEFAULT 0,
                classification TEXT DEFAULT 'normal',
                severity TEXT,
                anomaly_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
            )
        """)
        
        # 3. log_params テーブル（パラメータ抽出結果）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS log_params (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                param_name TEXT NOT NULL,
                param_value_num REAL,
                param_value_text TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (log_id) REFERENCES log_entries(id)
            )
        """)
        
        # 4. pattern_rules テーブル（異常判定ルール）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pattern_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_id INTEGER NOT NULL,
                rule_type TEXT NOT NULL,
                field_name TEXT,
                op TEXT NOT NULL,
                threshold_value1 REAL,
                threshold_value2 REAL,
                severity_if_match TEXT NOT NULL,
                is_abnormal_if_match INTEGER DEFAULT 1,
                message TEXT,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
            )
        """)
        
        # 5. alerts テーブル（通知履歴）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sent_at DATETIME,
                resolved_at DATETIME,
                FOREIGN KEY (log_id) REFERENCES log_entries(id)
            )
        """)
        
        # 6. ai_analyses テーブル（AI解析結果）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id INTEGER NOT NULL,
                prompt TEXT,
                response TEXT,
                model_name TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (log_id) REFERENCES log_entries(id)
            )
        """)
        
        # インデックス作成
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regex_patterns_regex_rule ON regex_patterns(regex_rule)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regex_patterns_label ON regex_patterns(label)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_entries_ts ON log_entries(ts)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_entries_pattern_id ON log_entries(pattern_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_entries_classification ON log_entries(classification)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_entries_is_known ON log_entries(is_known)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_entries_is_manual_mapped ON log_entries(is_manual_mapped)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_params_log_id ON log_params(log_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_rules_pattern_id ON pattern_rules(pattern_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pattern_rules_is_active ON pattern_rules(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_log_id ON alerts(log_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_analyses_log_id ON ai_analyses(log_id)")
        
        self.conn.commit()
    
    def get_connection(self):
        """データベース接続を取得"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def close(self):
        """データベース接続を閉じる"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
