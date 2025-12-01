"""
異常検知: ルールベースの異常判定
"""
import sys
import os
from typing import List, Dict, Optional

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


class AnomalyDetector:
    """ルールベースの異常検知を実行するクラス"""
    
    def __init__(self, db: Database):
        """
        Args:
            db: Databaseインスタンス
        """
        self.db = db
    
    def check_anomaly(self, log_id: int, pattern_id: int) -> Optional[Dict]:
        """
        ログエントリに対して異常判定を実行
        
        Args:
            log_id: ログエントリのID
            pattern_id: パターンID
            
        Returns:
            異常が検知された場合、以下の情報を含む辞書:
            {
                'is_abnormal': True,
                'classification': 'abnormal',
                'severity': str,
                'anomaly_reason': str
            }
            異常が検知されない場合はNone
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # パターンに関連するアクティブなルールを取得
        cursor.execute("""
            SELECT id, rule_type, field_name, op, 
                   threshold_value1, threshold_value2,
                   severity_if_match, is_abnormal_if_match, message
            FROM pattern_rules
            WHERE pattern_id = ? AND is_active = 1
            ORDER BY id
        """, (pattern_id,))
        
        rules = cursor.fetchall()
        if not rules:
            return None
        
        # ログエントリとパラメータを取得
        cursor.execute("""
            SELECT message, component
            FROM log_entries
            WHERE id = ?
        """, (log_id,))
        log_entry = cursor.fetchone()
        if not log_entry:
            return None
        
        # パラメータを取得
        cursor.execute("""
            SELECT param_name, param_value_num, param_value_text
            FROM log_params
            WHERE log_id = ?
        """, (log_id,))
        
        params = {}
        for row in cursor.fetchall():
            param_name = row['param_name']
            # 数値があれば数値を使用、なければテキスト
            params[param_name] = row['param_value_num'] if row['param_value_num'] is not None else row['param_value_text']
        
        # 各ルールを評価
        for rule in rules:
            if self._evaluate_rule(rule, log_entry['message'], params):
                return {
                    'is_abnormal': bool(rule['is_abnormal_if_match']),
                    'classification': 'abnormal',
                    'severity': rule['severity_if_match'],
                    'anomaly_reason': rule['message'] or f"Rule {rule['id']} matched"
                }
        
        return None
    
    def _evaluate_rule(self, rule: Dict, message: str, params: Dict) -> bool:
        """
        個別のルールを評価
        
        Args:
            rule: ルール情報（データベース行）
            message: ログメッセージ
            params: 抽出されたパラメータ
            
        Returns:
            ルールにマッチした場合True
        """
        rule_type = rule['rule_type']
        op = rule['op']
        field_name = rule.get('field_name')
        
        if rule_type == 'threshold':
            # しきい値チェック（パラメータが必要）
            if not field_name or field_name not in params:
                return False
            
            value = params[field_name]
            if not isinstance(value, (int, float)):
                return False
            
            threshold1 = rule['threshold_value1']
            threshold2 = rule['threshold_value2']
            
            if op == '>':
                return value > threshold1
            elif op == '>=':
                return value >= threshold1
            elif op == '<':
                return value < threshold1
            elif op == '<=':
                return value <= threshold1
            elif op == '==':
                return abs(value - threshold1) < 0.0001  # 浮動小数点比較
            elif op == '!=':
                return abs(value - threshold1) >= 0.0001
            elif op == 'between':
                if threshold1 is None or threshold2 is None:
                    return False
                return threshold1 <= value <= threshold2
            elif op == 'not_between':
                if threshold1 is None or threshold2 is None:
                    return False
                return not (threshold1 <= value <= threshold2)
        
        elif rule_type == 'contains':
            # メッセージに特定の文字列が含まれるかチェック
            if field_name:
                # パラメータの値に含まれるかチェック
                if field_name in params:
                    search_text = str(params[field_name])
                else:
                    return False
            else:
                # メッセージ本文に含まれるかチェック
                search_text = message
            
            threshold1 = rule['threshold_value1']  # 検索文字列として使用
            if threshold1 is None:
                return False
            
            return str(threshold1) in search_text
        
        elif rule_type == 'regex':
            # 正規表現マッチング
            import re
            threshold1 = rule['threshold_value1']  # 正規表現パターンとして使用
            if threshold1 is None:
                return False
            
            try:
                pattern = re.compile(str(threshold1))
                if field_name and field_name in params:
                    return bool(pattern.search(str(params[field_name])))
                else:
                    return bool(pattern.search(message))
            except re.error:
                return False
        
        return False
    
    def update_log_anomaly(self, log_id: int, anomaly_info: Dict):
        """
        ログエントリに異常情報を記録
        
        Args:
            log_id: ログエントリのID
            anomaly_info: check_anomaly()の戻り値
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE log_entries
            SET is_abnormal = ?,
                classification = ?,
                severity = ?,
                anomaly_reason = ?
            WHERE id = ?
        """, (
            1 if anomaly_info['is_abnormal'] else 0,
            anomaly_info['classification'],
            anomaly_info['severity'],
            anomaly_info['anomaly_reason'],
            log_id
        ))
        
        conn.commit()

