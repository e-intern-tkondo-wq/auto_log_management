"""
パターンマッチング: 既知/未知判定とパラメータ抽出
"""
import re
import sys
import os
from typing import Optional, Dict, List, Tuple

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


class PatternMatcher:
    """ログパターンマッチングを実行するクラス"""
    
    def __init__(self, db: Database):
        """
        Args:
            db: Databaseインスタンス
        """
        self.db = db
        self._pattern_cache = None
        self._cache_valid = False
    
    def invalidate_cache(self):
        """パターンキャッシュを無効化"""
        self._cache_valid = False
        self._pattern_cache = None
    
    def _load_patterns(self) -> List[Dict]:
        """
        アクティブなパターンをデータベースから読み込む
        
        Returns:
            パターンのリスト
        """
        if self._cache_valid and self._pattern_cache is not None:
            return self._pattern_cache
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, regex, component, default_severity
            FROM patterns
            WHERE is_active = 1
            ORDER BY id
        """)
        
        patterns = []
        for row in cursor.fetchall():
            try:
                # 正規表現をコンパイルして検証
                regex = re.compile(row['regex'])
                patterns.append({
                    'id': row['id'],
                    'name': row['name'],
                    'regex': regex,
                    'component': row['component'],
                    'default_severity': row['default_severity']
                })
            except re.error as e:
                # 無効な正規表現はスキップ
                print(f"Warning: Invalid regex pattern '{row['name']}': {e}")
                continue
        
        self._pattern_cache = patterns
        self._cache_valid = True
        return patterns
    
    def match_pattern(self, component: str, message: str) -> Optional[Tuple[int, Dict]]:
        """
        ログメッセージにマッチするパターンを検索
        
        Args:
            component: ログのコンポーネント（例: "kernel"）
            message: ログメッセージ本体
            
        Returns:
            (pattern_id, match_info) のタプル。マッチしない場合はNone
            match_infoには以下が含まれる:
            - 'severity': デフォルトのseverity
            - 'groups': 名前付きキャプチャグループの辞書
        """
        patterns = self._load_patterns()
        
        for pattern in patterns:
            # コンポーネントフィルタリング
            if pattern['component'] is not None and pattern['component'] != component:
                continue
            
            # 正規表現マッチング
            match = pattern['regex'].search(message)
            if match:
                # 名前付きキャプチャグループを抽出
                groups = match.groupdict() if match.groupdict() else {}
                
                return (pattern['id'], {
                    'severity': pattern['default_severity'],
                    'groups': groups
                })
        
        return None
    
    def update_log_entry(self, log_id: int, pattern_id: Optional[int], 
                        is_known: bool, classification: str, severity: str):
        """
        ログエントリの分類情報を更新
        
        Args:
            log_id: ログエントリのID
            pattern_id: マッチしたパターンID（Noneの場合は既存値を保持）
            is_known: 既知ログかどうか
            classification: 分類（'normal', 'abnormal', 'unknown'）
            severity: 重要度（'info', 'warning', 'critical', 'unknown'）
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if pattern_id is not None:
            cursor.execute("""
                UPDATE log_entries
                SET pattern_id = ?,
                    is_known = ?,
                    classification = ?,
                    severity = ?
                WHERE id = ?
            """, (pattern_id, 1 if is_known else 0, classification, severity, log_id))
        else:
            cursor.execute("""
                UPDATE log_entries
                SET is_known = ?,
                    classification = ?,
                    severity = ?
                WHERE id = ?
            """, (1 if is_known else 0, classification, severity, log_id))
        
        conn.commit()
    
    def save_log_params(self, log_id: int, params: Dict[str, any]):
        """
        ログから抽出したパラメータを保存
        
        Args:
            log_id: ログエントリのID
            params: パラメータ名 -> 値の辞書
        """
        if not params:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        for param_name, param_value in params.items():
            # 数値に変換可能かチェック
            param_value_num = None
            param_value_text = str(param_value)
            
            try:
                # 数値として解釈を試みる
                if isinstance(param_value, (int, float)):
                    param_value_num = float(param_value)
                else:
                    # 文字列から数値を抽出（例: "16M" -> 16, "85.5" -> 85.5）
                    num_match = re.match(r'^([+-]?\d+\.?\d*)', str(param_value))
                    if num_match:
                        param_value_num = float(num_match.group(1))
            except (ValueError, TypeError):
                pass
            
            cursor.execute("""
                INSERT INTO log_params (log_id, param_name, param_value_num, param_value_text)
                VALUES (?, ?, ?, ?)
            """, (log_id, param_name, param_value_num, param_value_text))
        
        conn.commit()

