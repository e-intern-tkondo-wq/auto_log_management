#!/usr/bin/env python3
"""
PCIe帯域幅閾値設定の確認スクリプト

このスクリプトは以下を確認します:
1. パターンが正しく登録されているか
2. 閾値ルールが正しく設定されているか
3. ログが取り込まれているか
4. パラメータが抽出されているか
5. 異常判定が実行されているか
"""
import sys
import os

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


def check_pcie_threshold_status(db_path: str = 'db/monitor.db'):
    """
    PCIe帯域幅閾値設定の状況を確認
    
    Args:
        db_path: データベースパス
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    print("=" * 80)
    print("PCIe帯域幅閾値設定の確認")
    print("=" * 80)
    print()
    
    # 1. パターンの確認
    print("1. パターンの確認")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            id,
            manual_regex_rule,
            sample_message,
            label,
            severity,
            note,
            total_count
        FROM regex_patterns
        WHERE sample_message LIKE '%available PCIe bandwidth%'
           OR manual_regex_rule LIKE '%available_bandwidth%'
        ORDER BY id DESC
        LIMIT 5
    """)
    
    patterns = cursor.fetchall()
    if patterns:
        # 最初のパターン（最新のもの）を使用
        pattern_id = None
        for pattern in patterns:
            if pattern_id is None:
                pattern_id = pattern['id']  # 最初のパターンIDを保存
            print(f"  パターンID: {pattern['id']}")
            print(f"  ラベル: {pattern['label']}")
            print(f"  重要度: {pattern['severity']}")
            print(f"  カウント: {pattern['total_count']}")
            print(f"  サンプル: {pattern['sample_message'][:80]}...")
            if pattern['note']:
                print(f"  ノート: {pattern['note']}")
            print()
    else:
        print("  ❌ PCIe帯域幅パターンが見つかりません")
        print("     先に python3 scripts/setup_pcie_bandwidth_threshold.py を実行してください")
        db.close()
        return
    
    if pattern_id is None:
        print("  ❌ パターンIDが取得できませんでした")
        db.close()
        return
    
    print(f"  使用するパターンID: {pattern_id}")
    print()
    
    # 2. 閾値ルールの確認
    print("2. 閾値ルールの確認")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            pr.id,
            pr.rule_type,
            pr.field_name,
            pr.op,
            pr.threshold_value1,
            pr.threshold_value2,
            pr.severity_if_match,
            pr.is_abnormal_if_match,
            pr.message,
            pr.is_active
        FROM pattern_rules pr
        WHERE pr.pattern_id = ?
        ORDER BY pr.id
    """, (pattern_id,))
    
    rules = cursor.fetchall()
    if rules:
        for rule in rules:
            status = "✅ 有効" if rule['is_abnormal_if_match'] else "ℹ️  情報"
            active = "🟢 アクティブ" if rule['is_active'] else "🔴 無効"
            print(f"  ルールID: {rule['id']} ({active})")
            print(f"  タイプ: {rule['rule_type']}")
            print(f"  フィールド: {rule['field_name']}")
            print(f"  演算子: {rule['op']}")
            print(f"  閾値1: {rule['threshold_value1']}")
            if rule['threshold_value2']:
                print(f"  閾値2: {rule['threshold_value2']}")
            print(f"  重要度: {rule['severity_if_match']} ({status})")
            if rule['message']:
                print(f"  メッセージ: {rule['message']}")
            print()
    else:
        print("  ❌ 閾値ルールが見つかりません")
        print("     先に python3 scripts/setup_pcie_bandwidth_threshold.py を実行してください")
    print()
    
    # 3. ログエントリの確認
    print("3. ログエントリの確認")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_known = 1 THEN 1 ELSE 0 END) as known,
            SUM(CASE WHEN is_known = 0 THEN 1 ELSE 0 END) as unknown,
            SUM(CASE WHEN classification = 'abnormal' THEN 1 ELSE 0 END) as abnormal
        FROM log_entries
        WHERE pattern_id = ?
    """, (pattern_id,))
    
    log_stats = cursor.fetchone()
    if log_stats and log_stats['total'] > 0:
        print(f"  総ログ数: {log_stats['total']}")
        print(f"  既知ログ: {log_stats['known']}")
        print(f"  未知ログ: {log_stats['unknown']}")
        print(f"  異常ログ: {log_stats['abnormal']}")
    else:
        print("  ⚠️  このパターンにマッチするログがまだ取り込まれていません")
        print("     ログを取り込む: python3 src/ingest.py <log_file>")
    print()
    
    # 4. パラメータ抽出の確認
    print("4. パラメータ抽出の確認")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            lp.param_name,
            COUNT(*) as count,
            MIN(lp.param_value_num) as min_value,
            MAX(lp.param_value_num) as max_value,
            AVG(lp.param_value_num) as avg_value
        FROM log_params lp
        JOIN log_entries le ON lp.log_id = le.id
        WHERE le.pattern_id = ?
        GROUP BY lp.param_name
        ORDER BY lp.param_name
    """, (pattern_id,))
    
    params = cursor.fetchall()
    if params:
        for param in params:
            print(f"  {param['param_name']}:")
            print(f"    抽出数: {param['count']}")
            print(f"    最小値: {param['min_value']}")
            print(f"    最大値: {param['max_value']}")
            print(f"    平均値: {param['avg_value']:.2f}")
            print()
    else:
        print("  ⚠️  パラメータが抽出されていません")
        print("     パターンに named capture group が含まれているか確認してください")
    print()
    
    # 5. 異常判定の確認
    print("5. 異常判定の確認")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            le.id,
            le.ts,
            le.host,
            le.message,
            le.classification,
            le.severity,
            le.anomaly_reason,
            lp.param_name,
            lp.param_value_num
        FROM log_entries le
        LEFT JOIN log_params lp ON le.id = lp.log_id AND lp.param_name = 'available_bandwidth'
        WHERE le.pattern_id = ?
          AND le.classification = 'abnormal'
        ORDER BY le.ts DESC
        LIMIT 10
    """, (pattern_id,))
    
    abnormal_logs = cursor.fetchall()
    if abnormal_logs:
        print(f"  異常ログ数: {len(abnormal_logs)} (最新10件を表示)")
        print()
        for log in abnormal_logs:
            print(f"  ログID: {log['id']}")
            print(f"  時刻: {log['ts']}")
            print(f"  ホスト: {log['host']}")
            print(f"  重要度: {log['severity']}")
            if log['param_value_num']:
                print(f"  available_bandwidth: {log['param_value_num']} Gb/s")
            if log['anomaly_reason']:
                print(f"  異常理由: {log['anomaly_reason']}")
            print(f"  メッセージ: {log['message'][:80]}...")
            print()
    else:
        print("  ℹ️  異常ログはありません（閾値を超えていないか、ログが取り込まれていません）")
    print()
    
    # 6. サンプルログの確認
    print("6. サンプルログ（最新5件）")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            le.id,
            le.ts,
            le.host,
            le.message,
            le.classification,
            le.is_known,
            (SELECT GROUP_CONCAT(param_name || '=' || param_value_num, ', ')
             FROM log_params
             WHERE log_id = le.id) as params
        FROM log_entries le
        WHERE le.pattern_id = ?
        ORDER BY le.ts DESC
        LIMIT 5
    """, (pattern_id,))
    
    sample_logs = cursor.fetchall()
    if sample_logs:
        for log in sample_logs:
            known_status = "既知" if log['is_known'] else "未知"
            print(f"  [{log['ts']}] {log['host']} ({known_status}, {log['classification']})")
            if log['params']:
                print(f"    パラメータ: {log['params']}")
            print(f"    {log['message'][:70]}...")
            print()
    else:
        print("  ⚠️  ログがまだ取り込まれていません")
    
    print()
    print("=" * 80)
    print("確認完了")
    print("=" * 80)
    
    db.close()


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Check PCIe bandwidth threshold status')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    
    args = parser.parse_args()
    
    check_pcie_threshold_status(args.db)


if __name__ == '__main__':
    main()

