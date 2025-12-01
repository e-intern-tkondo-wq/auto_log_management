#!/usr/bin/env python3
"""
PCIe帯域幅ログの閾値設定スクリプト
add_threshold_rule.py を使用して閾値を設定
"""
import sys
import os
import subprocess

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.cli_tools import add_pattern


def setup_pcie_threshold(db_path: str = 'db/monitor.db'):
    """
    PCIe帯域幅ログのパターンと閾値ルールを設定
    add_threshold_rule.py を使用
    """
    print("=" * 80)
    print("PCIe帯域幅ログの閾値設定")
    print("=" * 80)
    print()
    
    # ステップ1: パターンを追加
    print("ステップ1: パターンを追加中...")
    regex_pattern = r"\[\s+\d+\.\d+\]\s+pci\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<available_bandwidth>\d+\.?\d*)\s+Gb/s\s+available\s+PCIe\s+bandwidth,\s+limited\s+by\s+(?P<limited_by_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\s+at\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s+\(capable\s+of\s+(?P<capable_bandwidth>\d+\.?\d*)\s+Gb/s\s+with\s+(?P<capable_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\)"
    sample_message = "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)"
    
    try:
        pattern_id = add_pattern(
            db_path=db_path,
            regex_rule=regex_pattern,
            sample_message=sample_message,
            label='normal',
            severity='info',
            component='kernel',
            note='PCIe帯域幅ログ（available_bandwidth, limited_by_speed, capable_bandwidth, capable_speedを抽出可能）',
            update_existing=True
        )
        print(f"✅ パターン追加完了 (ID: {pattern_id})")
        print()
    except Exception as e:
        print(f"⚠️  パターン追加エラー: {e}")
        # 既存パターンを検索
        db = Database(db_path)
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM regex_patterns
            WHERE manual_regex_rule = ? OR sample_message LIKE ?
            ORDER BY id DESC LIMIT 1
        """, (regex_pattern, "%available PCIe bandwidth%"))
        existing = cursor.fetchone()
        if existing:
            pattern_id = existing['id']
            print(f"既存のパターンを使用 (ID: {pattern_id})")
        else:
            print("❌ パターンが見つかりません")
            db.close()
            sys.exit(1)
        db.close()
        print()
    
    # ステップ2: 閾値ルールを追加（add_threshold_rule.py を使用）
    print("ステップ2: 閾値ルールを追加中...")
    print()
    
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    add_threshold_rule_script = os.path.join(scripts_dir, "add_threshold_rule.py")
    
    # ルール1: available_bandwidth <= 50.0 Gb/s の場合に warning
    print("  ルール1: available_bandwidth <= 50.0 Gb/s → warning")
    cmd1 = [
        sys.executable, add_threshold_rule_script,
        "--pattern-id", str(pattern_id),
        "--rule-type", "threshold",
        "--field-name", "available_bandwidth",
        "--op", "<=",
        "--threshold", "50.0",
        "--severity", "warning",
        "--message", "PCIe available bandwidth <= 50 Gb/s (性能低下の可能性)",
        "--db", db_path
    ]
    result1 = subprocess.run(cmd1, capture_output=True, text=True)
    if result1.returncode == 0:
        print(f"  ✅ ルール1追加完了")
        print(f"     {result1.stdout.strip()}")
    else:
        print(f"  ⚠️  ルール1追加エラー（既に存在する可能性）")
        if result1.stderr:
            print(f"     {result1.stderr.strip()}")
    print()
    
    # ルール2: available_bandwidth <= 30.0 Gb/s の場合に critical
    print("  ルール2: available_bandwidth <= 30.0 Gb/s → critical")
    cmd2 = [
        sys.executable, add_threshold_rule_script,
        "--pattern-id", str(pattern_id),
        "--rule-type", "threshold",
        "--field-name", "available_bandwidth",
        "--op", "<=",
        "--threshold", "30.0",
        "--severity", "critical",
        "--message", "PCIe available bandwidth <= 30 Gb/s (重大な性能低下)",
        "--db", db_path
    ]
    result2 = subprocess.run(cmd2, capture_output=True, text=True)
    if result2.returncode == 0:
        print(f"  ✅ ルール2追加完了")
        print(f"     {result2.stdout.strip()}")
    else:
        print(f"  ⚠️  ルール2追加エラー（既に存在する可能性）")
        if result2.stderr:
            print(f"     {result2.stderr.strip()}")
    print()
    
    print("=" * 80)
    print("設定完了")
    print("=" * 80)
    print()
    print(f"パターンID: {pattern_id}")
    print("設定された閾値:")
    print("  - available_bandwidth <= 50.0 Gb/s → warning")
    print("  - available_bandwidth <= 30.0 Gb/s → critical")
    print()
    print("次のステップ:")
    print("  1. ログを取り込む: python3 src/ingest.py <log_file>")
    print("  2. 設定状況を確認: python3 scripts/check_pcie_threshold_status.py")


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup PCIe bandwidth threshold using add_threshold_rule.py')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    
    args = parser.parse_args()
    
    setup_pcie_threshold(args.db)


if __name__ == '__main__':
    main()

