#!/usr/bin/env python3
"""
閾値ルール追加スクリプト

pattern_rules テーブルに閾値チェックルールを追加するためのCLIツール
"""
import sys
import os
import argparse

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


def add_threshold_rule(
    db_path: str,
    pattern_id: int,
    rule_type: str,
    field_name: str = None,
    op: str = None,
    threshold_value1: float = None,
    threshold_value2: float = None,
    severity_if_match: str = 'critical',
    is_abnormal_if_match: bool = True,
    message: str = None,
    is_active: bool = True
):
    """
    閾値ルールを追加
    
    Args:
        db_path: データベースパス
        pattern_id: パターンID
        rule_type: ルールタイプ ('threshold', 'contains', 'regex')
        field_name: パラメータ名（threshold の場合に必要）
        op: 演算子 ('>', '<', '>=', '<=', '==', '!=', 'between', 'not_between')
        threshold_value1: 閾値1
        threshold_value2: 閾値2（'between' の場合に必要）
        severity_if_match: 異常時の重要度
        is_abnormal_if_match: 異常フラグ
        message: 異常理由メッセージ
        is_active: アクティブフラグ
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # パターンが存在するか確認
    cursor.execute("SELECT id, sample_message FROM regex_patterns WHERE id = ?", (pattern_id,))
    pattern = cursor.fetchone()
    if not pattern:
        print(f"Error: Pattern {pattern_id} not found")
        db.close()
        sys.exit(1)
    
    # ルールタイプに応じたデフォルト値を設定
    if rule_type == 'threshold':
        if not field_name:
            print("Error: field_name is required for threshold rule")
            db.close()
            sys.exit(1)
        if not op:
            print("Error: op is required for threshold rule")
            db.close()
            sys.exit(1)
        if threshold_value1 is None:
            print("Error: threshold_value1 is required for threshold rule")
            db.close()
            sys.exit(1)
    elif rule_type == 'contains':
        if threshold_value1 is None:
            print("Error: threshold_value1 (search string) is required for contains rule")
            db.close()
            sys.exit(1)
        op = 'contains'  # contains の場合は op を自動設定
    elif rule_type == 'regex':
        if threshold_value1 is None:
            print("Error: threshold_value1 (regex pattern) is required for regex rule")
            db.close()
            sys.exit(1)
        op = 'matches'  # regex の場合は op を自動設定
    
    # メッセージが未指定の場合は自動生成
    if not message:
        if rule_type == 'threshold':
            if op == 'between':
                message = f"{field_name} between {threshold_value1} and {threshold_value2}"
            elif op == 'not_between':
                message = f"{field_name} not between {threshold_value1} and {threshold_value2}"
            else:
                message = f"{field_name} {op} {threshold_value1}"
        elif rule_type == 'contains':
            message = f"Message contains '{threshold_value1}'"
        elif rule_type == 'regex':
            message = f"Message matches pattern '{threshold_value1}'"
    
    # ルールを追加
    cursor.execute("""
        INSERT INTO pattern_rules (
            pattern_id, rule_type, field_name, op,
            threshold_value1, threshold_value2,
            severity_if_match, is_abnormal_if_match,
            message, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pattern_id,
        rule_type,
        field_name,
        op,
        threshold_value1,
        threshold_value2,
        severity_if_match,
        1 if is_abnormal_if_match else 0,
        message,
        1 if is_active else 0
    ))
    
    rule_id = cursor.lastrowid
    conn.commit()
    
    print(f"Successfully added rule (ID: {rule_id})")
    print(f"  Pattern ID: {pattern_id}")
    print(f"  Pattern sample: {pattern['sample_message'][:80]}...")
    print(f"  Rule type: {rule_type}")
    if field_name:
        print(f"  Field name: {field_name}")
    if op:
        print(f"  Operator: {op}")
    if threshold_value1 is not None:
        print(f"  Threshold1: {threshold_value1}")
    if threshold_value2 is not None:
        print(f"  Threshold2: {threshold_value2}")
    print(f"  Severity if match: {severity_if_match}")
    print(f"  Is abnormal: {is_abnormal_if_match}")
    print(f"  Message: {message}")
    print(f"  Is active: {is_active}")
    
    db.close()
    return rule_id


def main():
    """コマンドラインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description='Add threshold rule to pattern_rules table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 閾値チェック（温度が80度を超えた場合）
  python3 scripts/add_threshold_rule.py \\
    --pattern-id 100 \\
    --rule-type threshold \\
    --field-name temp \\
    --op '>' \\
    --threshold 80.0 \\
    --severity critical \\
    --message "GPU temp > 80°C"
  
  # 文字列含有チェック
  python3 scripts/add_threshold_rule.py \\
    --pattern-id 100 \\
    --rule-type contains \\
    --threshold "ERROR" \\
    --severity critical
  
  # 正規表現チェック
  python3 scripts/add_threshold_rule.py \\
    --pattern-id 100 \\
    --rule-type regex \\
    --threshold ".*ERROR.*" \\
    --severity warning
        """
    )
    
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    parser.add_argument('--pattern-id', type=int, required=True, help='Pattern ID')
    parser.add_argument('--rule-type', choices=['threshold', 'contains', 'regex'], 
                       required=True, help='Rule type')
    parser.add_argument('--field-name', help='Parameter name (required for threshold)')
    parser.add_argument('--op', choices=['>', '<', '>=', '<=', '==', '!=', 'between', 'not_between'],
                       help='Operator (required for threshold)')
    parser.add_argument('--threshold', dest='threshold_value1',
                       help='Threshold value 1 (float for threshold, string for contains/regex)')
    parser.add_argument('--threshold2', type=float, dest='threshold_value2',
                       help='Threshold value 2 (required for between/not_between)')
    parser.add_argument('--severity', default='critical', 
                       choices=['info', 'warning', 'critical'],
                       dest='severity_if_match',
                       help='Severity if rule matches')
    parser.add_argument('--is-abnormal', action='store_true', default=True,
                       dest='is_abnormal_if_match',
                       help='Mark as abnormal if rule matches (default: True)')
    parser.add_argument('--is-normal', action='store_false',
                       dest='is_abnormal_if_match',
                       help='Mark as normal if rule matches')
    parser.add_argument('--message', help='Anomaly reason message')
    parser.add_argument('--inactive', action='store_false', dest='is_active',
                       help='Add rule as inactive')
    
    args = parser.parse_args()
    
    # threshold_value1 を適切な型に変換
    if args.threshold_value1 is not None:
        if args.rule_type == 'threshold':
            # threshold の場合は float に変換
            try:
                threshold_value1 = float(args.threshold_value1)
            except ValueError:
                print(f"Error: threshold must be a number for threshold rule type")
                sys.exit(1)
        else:
            # contains, regex の場合は文字列として扱う
            threshold_value1 = str(args.threshold_value1)
    else:
        threshold_value1 = None
    
    add_threshold_rule(
        db_path=args.db,
        pattern_id=args.pattern_id,
        rule_type=args.rule_type,
        field_name=args.field_name,
        op=args.op,
        threshold_value1=threshold_value1,
        threshold_value2=args.threshold_value2,
        severity_if_match=args.severity_if_match,
        is_abnormal_if_match=args.is_abnormal_if_match,
        message=args.message,
        is_active=args.is_active
    )


if __name__ == '__main__':
    main()

