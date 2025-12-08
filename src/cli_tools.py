"""
CLIツール: 未知パターン表示、統計表示など
"""
import sys
import os

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


def show_unknown_patterns(db_path: str = 'db/monitor.db', limit: int = 100):
    """
    未知パターンの一覧を表示
    
    Args:
        db_path: データベースパス
        limit: 表示件数の上限
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, regex_rule, sample_message, label, total_count,
               first_seen_at, last_seen_at
        FROM regex_patterns
        WHERE label = 'unknown'
        ORDER BY total_count DESC
        LIMIT ?
    """, (limit,))
    
    patterns = cursor.fetchall()
    
    if not patterns:
        print("No unknown patterns found")
        return
    
    print(f"Found {len(patterns)} unknown patterns (showing top {limit}):\n")
    print(f"{'ID':<8} {'Count':<10} {'First Seen':<20} {'Last Seen':<20}")
    print("-" * 80)
    
    for pattern in patterns:
        print(f"{pattern['id']:<8} {pattern['total_count']:<10} "
              f"{pattern['first_seen_at']:<20} {pattern['last_seen_at']:<20}")
        print(f"  Regex: {pattern['regex_rule'][:70]}...")
        print(f"  Sample: {pattern['sample_message'][:70]}...")
        print()
    
    db.close()


def show_stats(db_path: str = 'db/monitor.db'):
    """
    統計情報を表示
    
    Args:
        db_path: データベースパス
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # ログエントリの総数
    cursor.execute("SELECT COUNT(*) as count FROM log_entries")
    total_logs = cursor.fetchone()['count']
    
    # パターン数
    cursor.execute("SELECT COUNT(*) as count FROM regex_patterns")
    total_patterns = cursor.fetchone()['count']
    
    # 分類別の件数
    cursor.execute("""
        SELECT classification, COUNT(*) as count
        FROM log_entries
        GROUP BY classification
        ORDER BY count DESC
    """)
    classification_counts = cursor.fetchall()
    
    # ラベル別のパターン数
    cursor.execute("""
        SELECT label, COUNT(*) as count
        FROM regex_patterns
        GROUP BY label
        ORDER BY count DESC
    """)
    label_counts = cursor.fetchall()
    
    # アラート統計
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM alerts
        GROUP BY status
    """)
    alert_counts = cursor.fetchall()
    
    print("=== Log Monitoring System Statistics ===\n")
    print(f"Total log entries: {total_logs:,}")
    print(f"Total patterns: {total_patterns:,}\n")
    
    print("Classification distribution:")
    for row in classification_counts:
        print(f"  {row['classification']:<15} {row['count']:>10,}")
    
    print("\nPattern label distribution:")
    for row in label_counts:
        print(f"  {row['label']:<15} {row['count']:>10,}")
    
    if alert_counts:
        print("\nAlert status distribution:")
        for row in alert_counts:
            print(f"  {row['status']:<15} {row['count']:>10,}")
    
    # 最近の異常ログ
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM log_entries
        WHERE classification = 'abnormal'
        AND ts >= datetime('now', '-24 hours')
    """)
    recent_abnormal = cursor.fetchone()['count']
    
    # 最近の未知ログ
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM log_entries
        WHERE classification = 'unknown'
        AND ts >= datetime('now', '-24 hours')
    """)
    recent_unknown = cursor.fetchone()['count']
    
    print(f"\nLast 24 hours:")
    print(f"  Abnormal logs: {recent_abnormal:,}")
    print(f"  Unknown logs: {recent_unknown:,}")
    
    db.close()


def update_pattern_label(db_path: str, pattern_id: int, label: str, severity: str = None, note: str = None):
    """
    パターンのラベルを更新
    
    Args:
        db_path: データベースパス
        pattern_id: パターンID
        label: 新しいラベル（'normal', 'abnormal', 'unknown', 'ignore'）
        severity: 重要度（オプション）
        note: ノート（オプション）
    """
    if label not in ('normal', 'abnormal', 'unknown', 'ignore'):
        print(f"Error: Invalid label '{label}'. Must be one of: normal, abnormal, unknown, ignore")
        sys.exit(1)
    
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # パターンを更新
    if severity and note:
        cursor.execute("""
            UPDATE regex_patterns
            SET label = ?, severity = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (label, severity, note, pattern_id))
    elif severity:
        cursor.execute("""
            UPDATE regex_patterns
            SET label = ?, severity = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (label, severity, pattern_id))
    elif note:
        cursor.execute("""
            UPDATE regex_patterns
            SET label = ?, note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (label, note, pattern_id))
    else:
        cursor.execute("""
            UPDATE regex_patterns
            SET label = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (label, pattern_id))
    
    # このパターンに属するログエントリのclassificationも更新
    cursor.execute("""
        UPDATE log_entries
        SET classification = ?,
            severity = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE pattern_id = ?
    """, (label, severity, pattern_id))
    
    conn.commit()
    
    affected = cursor.rowcount
    print(f"Updated pattern {pattern_id} to label '{label}'")
    print(f"Updated {affected} log entries")
    
    db.close()


def map_unknown_log_to_pattern(db_path: str, log_id: int, pattern_id: int):
    """
    未知ログを既知パターンに手動で紐付ける
    
    Args:
        db_path: データベースパス
        log_id: ログエントリのID
        pattern_id: 紐付けるパターンID
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # パターン情報を取得
    cursor.execute("""
        SELECT label, severity
        FROM regex_patterns
        WHERE id = ?
    """, (pattern_id,))
    
    pattern_row = cursor.fetchone()
    if not pattern_row:
        print(f"Error: Pattern {pattern_id} not found")
        db.close()
        sys.exit(1)
    
    # ログエントリを更新
    cursor.execute("""
        UPDATE log_entries
        SET pattern_id = ?,
            is_known = 1,
            is_manual_mapped = 1,
            classification = ?,
            severity = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (pattern_id, pattern_row['label'], pattern_row['severity'], log_id))
    
    conn.commit()
    
    affected = cursor.rowcount
    if affected > 0:
        print(f"Successfully mapped log {log_id} to pattern {pattern_id}")
        print(f"Classification: {pattern_row['label']}, Severity: {pattern_row['severity']}")
    else:
        print(f"Error: Log {log_id} not found")
    
    db.close()


def add_pattern(db_path: str, regex_rule: str, sample_message: str, 
                label: str = 'normal', severity: str = None, 
                component: str = None, note: str = None, 
                update_existing: bool = False):
    """
    手動で正規表現パターンを追加
    
    Args:
        db_path: データベースパス
        regex_rule: 正規表現パターン
        sample_message: サンプルメッセージ
        label: ラベル（'normal', 'abnormal', 'unknown', 'ignore'）
        severity: 重要度（'info', 'warning', 'critical', 'unknown'）
        component: コンポーネント（例: 'kernel'）。NULLの場合は全コンポーネント対象
        note: ノート（説明など）
        update_existing: 既存パターンが見つかった場合に更新するかどうか
    """
    import re
    from datetime import datetime
    
    # 正規表現の妥当性をチェック
    try:
        re.compile(regex_rule)
    except re.error as e:
        print(f"Error: Invalid regex pattern: {e}")
        sys.exit(1)
    
    if label not in ('normal', 'abnormal', 'unknown', 'ignore'):
        print(f"Error: Invalid label '{label}'. Must be one of: normal, abnormal, unknown, ignore")
        sys.exit(1)
    
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # 既に同じパターンが存在するかチェック（regex_rule と manual_regex_rule の両方をチェック）
    cursor.execute("""
        SELECT id, label, severity
        FROM regex_patterns
        WHERE regex_rule = ? OR manual_regex_rule = ?
    """, (regex_rule, regex_rule))
    
    existing = cursor.fetchone()
    if existing:
        if update_existing:
            cursor.execute("""
                UPDATE regex_patterns
                SET label = ?,
                    severity = ?,
                    note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (label, severity, note, existing['id']))
            conn.commit()
            print(f"Updated pattern {existing['id']}")
            db.close()
            return existing['id']
        else:
            print(f"Warning: Pattern already exists (ID: {existing['id']})")
            print(f"  Current label: {existing['label']}, severity: {existing['severity']}")
            print("  Use --update flag to update existing pattern")
            db.close()
            return existing['id']
    
    # 新規パターンを追加（手動なので manual_regex_rule に格納、regex_rule は NULL）
    now = datetime.now()
    cursor.execute("""
        INSERT INTO regex_patterns
        (regex_rule, manual_regex_rule, sample_message, label, severity, note, first_seen_at, last_seen_at, total_count)
        VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (regex_rule, sample_message, label, severity, note, now, now))
    
    pattern_id = cursor.lastrowid
    conn.commit()
    
    print(f"Successfully added pattern (ID: {pattern_id})")
    print(f"  Regex: {regex_rule[:80]}...")
    print(f"  Label: {label}, Severity: {severity}")
    if component:
        print(f"  Component: {component}")
    if note:
        print(f"  Note: {note[:80]}...")
    
    db.close()
    return pattern_id


def add_pattern_from_log(db_path: str, log_id: int, label: str = 'normal', 
                         severity: str = None, note: str = None):
    """
    未知ログから正規表現パターンを生成して追加
    
    Args:
        db_path: データベースパス
        log_id: ログエントリのID
        label: ラベル（'normal', 'abnormal', 'unknown', 'ignore'）
        severity: 重要度
        note: ノート
    """
    from src.abstract_message import abstract_message
    
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # ログエントリを取得
    cursor.execute("""
        SELECT message, component
        FROM log_entries
        WHERE id = ?
    """, (log_id,))
    
    log_row = cursor.fetchone()
    if not log_row:
        print(f"Error: Log {log_id} not found")
        db.close()
        sys.exit(1)
    
    # abstract_message()でパターンを生成
    regex_rule = abstract_message(log_row['message'])
    sample_message = log_row['message']
    component = log_row['component']
    
    # パターンを追加（既存パターンの場合は既存IDを返す）
    pattern_id = add_pattern(db_path, regex_rule, sample_message, label, severity, component, note, update_existing=False)
    
    if pattern_id:
        # このログエントリを新しく追加したパターンに紐付け
        cursor.execute("""
            UPDATE log_entries
            SET pattern_id = ?,
                is_known = 1,
                is_manual_mapped = 1,
                classification = ?,
                severity = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (pattern_id, label, severity, log_id))
        
        conn.commit()
        print(f"Log {log_id} has been mapped to pattern {pattern_id}")
    
    db.close()
    return pattern_id


def reprocess_pattern(db_path: str, pattern_id: int, verbose: bool = False):
    """
    既存のログエントリを指定されたパターンにマッチさせて再処理
    パラメータ抽出と異常判定を実行
    
    Args:
        db_path: データベースパス
        pattern_id: パターンID
        verbose: 詳細出力するかどうか
    """
    import re
    from src.param_extractor import ParamExtractor
    from src.anomaly_detector import AnomalyDetector
    
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # パターン情報を取得
    cursor.execute("""
        SELECT id, regex_rule, manual_regex_rule, label, severity
        FROM regex_patterns
        WHERE id = ?
    """, (pattern_id,))
    
    pattern_row = cursor.fetchone()
    if not pattern_row:
        print(f"Error: Pattern {pattern_id} not found")
        db.close()
        sys.exit(1)
    
    # 使用する正規表現パターンを決定
    pattern_to_use = pattern_row['manual_regex_rule'] or pattern_row['regex_rule']
    if not pattern_to_use:
        print(f"Error: Pattern {pattern_id} has no regex rule")
        db.close()
        sys.exit(1)
    
    # パターンをコンパイル
    try:
        compiled_pattern = re.compile(pattern_to_use)
    except re.error as e:
        print(f"Error: Invalid regex pattern: {e}")
        db.close()
        sys.exit(1)
    
    # すべてのログエントリを取得して、パターンにマッチするものを再処理
    # 既にこのパターンに紐付いているログ、またはマッチする可能性のあるログを処理
    cursor.execute("""
        SELECT id, message, classification, is_known
        FROM log_entries
        ORDER BY id
    """)
    
    logs = cursor.fetchall()
    
    param_extractor = ParamExtractor()
    anomaly_detector = AnomalyDetector(db)
    
    matched_count = 0
    param_extracted_count = 0
    abnormal_detected_count = 0
    
    for log_row in logs:
        log_id = log_row['id']
        message = log_row['message']
        
        # パターンにマッチするかチェック
        if compiled_pattern.search(message):
            matched_count += 1
            
            # ログエントリを更新（is_known=1に設定）
            classification = pattern_row['label']
            if classification == 'unknown':
                classification = 'normal'
            
            cursor.execute("""
                UPDATE log_entries
                SET pattern_id = ?,
                    is_known = 1,
                    classification = ?,
                    severity = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (pattern_id, classification, pattern_row['severity'], log_id))
            
            # 既存のパラメータを削除（再抽出のため）
            cursor.execute("DELETE FROM log_params WHERE log_id = ?", (log_id,))
            
            # パラメータ抽出
            params = param_extractor.extract_params(pattern_to_use, message)
            if params:
                param_extracted_count += 1
                for param_name, param_data in params.items():
                    cursor.execute("""
                        INSERT INTO log_params
                        (log_id, param_name, param_value_num, param_value_text)
                        VALUES (?, ?, ?, ?)
                    """, (log_id, param_name, param_data['num'], param_data['text']))
            
            # 異常判定を実行
            anomaly_info = anomaly_detector.check_anomaly(log_id, pattern_id)
            if anomaly_info:
                abnormal_detected_count += 1
                cursor.execute("""
                    UPDATE log_entries
                    SET classification = ?,
                        severity = ?,
                        anomaly_reason = ?
                    WHERE id = ?
                """, (
                    anomaly_info['classification'],
                    anomaly_info['severity'],
                    anomaly_info['anomaly_reason'],
                    log_id
                ))
                if verbose:
                    print(f"Log {log_id}: abnormal detected - {anomaly_info['anomaly_reason']}")
    
    conn.commit()
    
    print(f"Reprocessed pattern {pattern_id}")
    print(f"  Matched logs: {matched_count}")
    print(f"  Logs with parameters extracted: {param_extracted_count}")
    print(f"  Logs marked as abnormal: {abnormal_detected_count}")
    
    db.close()


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description='CLI tools for log monitoring system')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # show-unknown コマンド
    parser_unknown = subparsers.add_parser('show-unknown', help='Show unknown patterns')
    parser_unknown.add_argument('--db', default='db/monitor.db', help='Database path')
    parser_unknown.add_argument('--limit', type=int, default=100, help='Limit number of results')
    
    # stats コマンド
    parser_stats = subparsers.add_parser('stats', help='Show statistics')
    parser_stats.add_argument('--db', default='db/monitor.db', help='Database path')
    
    # update-label コマンド
    parser_update = subparsers.add_parser('update-label', help='Update pattern label')
    parser_update.add_argument('pattern_id', type=int, help='Pattern ID')
    parser_update.add_argument('label', choices=['normal', 'abnormal', 'unknown', 'ignore'], help='New label')
    parser_update.add_argument('--severity', help='Severity (info, warning, critical, etc.)')
    parser_update.add_argument('--note', help='Note text')
    parser_update.add_argument('--db', default='db/monitor.db', help='Database path')
    
    # map-log コマンド
    parser_map = subparsers.add_parser('map-log', help='Map unknown log to known pattern')
    parser_map.add_argument('log_id', type=int, help='Log entry ID')
    parser_map.add_argument('pattern_id', type=int, help='Pattern ID to map to')
    parser_map.add_argument('--db', default='db/monitor.db', help='Database path')
    
    # add-pattern コマンド
    parser_add = subparsers.add_parser('add-pattern', help='Add manual regex pattern')
    parser_add.add_argument('regex_rule', help='Regular expression pattern')
    parser_add.add_argument('sample_message', help='Sample message')
    parser_add.add_argument('--label', choices=['normal', 'abnormal', 'unknown', 'ignore'], 
                           default='normal', help='Pattern label')
    parser_add.add_argument('--severity', help='Severity (info, warning, critical, etc.)')
    parser_add.add_argument('--component', help='Component filter (e.g., kernel)')
    parser_add.add_argument('--note', help='Note text')
    parser_add.add_argument('--update', action='store_true', 
                           help='Update existing pattern if found')
    parser_add.add_argument('--db', default='db/monitor.db', help='Database path')
    
    # add-pattern-from-log コマンド
    parser_from_log = subparsers.add_parser('add-pattern-from-log', 
                                           help='Generate pattern from unknown log and add it')
    parser_from_log.add_argument('log_id', type=int, help='Log entry ID')
    parser_from_log.add_argument('--label', choices=['normal', 'abnormal', 'unknown', 'ignore'], 
                                 default='normal', help='Pattern label')
    parser_from_log.add_argument('--severity', help='Severity (info, warning, critical, etc.)')
    parser_from_log.add_argument('--note', help='Note text')
    parser_from_log.add_argument('--db', default='db/monitor.db', help='Database path')
    
    # reprocess-pattern コマンド
    parser_reprocess = subparsers.add_parser('reprocess-pattern', 
                                             help='Reprocess existing logs to match a pattern and extract parameters')
    parser_reprocess.add_argument('pattern_id', type=int, help='Pattern ID to reprocess')
    parser_reprocess.add_argument('--db', default='db/monitor.db', help='Database path')
    parser_reprocess.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'show-unknown':
        show_unknown_patterns(args.db, args.limit)
    elif args.command == 'stats':
        show_stats(args.db)
    elif args.command == 'update-label':
        update_pattern_label(args.db, args.pattern_id, args.label, args.severity, args.note)
    elif args.command == 'map-log':
        map_unknown_log_to_pattern(args.db, args.log_id, args.pattern_id)
    elif args.command == 'add-pattern':
        add_pattern(args.db, args.regex_rule, args.sample_message, 
                   args.label, args.severity, args.component, args.note, args.update)
    elif args.command == 'add-pattern-from-log':
        add_pattern_from_log(args.db, args.log_id, args.label, args.severity, args.note)
    elif args.command == 'reprocess-pattern':
        reprocess_pattern(args.db, args.pattern_id, args.verbose)


if __name__ == '__main__':
    main()

