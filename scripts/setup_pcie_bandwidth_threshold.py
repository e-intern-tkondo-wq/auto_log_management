#!/usr/bin/env python3
"""
PCIe帯域幅ログの閾値設定スクリプト

このスクリプトは以下の処理を実行します:
1. PCIe帯域幅ログのパターンを手動で追加（named capture groupを含む）
2. 閾値ルールを設定（available_bandwidth が 50 Gb/s 以下の場合に異常）
3. 設定状況を確認
"""
import sys
import os

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.cli_tools import add_pattern

# add_threshold_rule をインポート
scripts_dir = os.path.dirname(os.path.abspath(__file__))
add_threshold_rule_path = os.path.join(scripts_dir, "add_threshold_rule.py")
if os.path.exists(add_threshold_rule_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("add_threshold_rule", add_threshold_rule_path)
    add_threshold_rule_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(add_threshold_rule_module)
    add_threshold_rule = add_threshold_rule_module.add_threshold_rule
else:
    # フォールバック: 直接SQLで追加
    def add_threshold_rule(*args, **kwargs):
        raise ImportError("add_threshold_rule.py not found")


def setup_pcie_bandwidth_threshold(db_path: str = 'db/monitor.db'):
    """
    PCIe帯域幅ログのパターンと閾値ルールを設定
    
    Args:
        db_path: データベースパス
    """
    # サンプルログメッセージ
    sample_message = "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)"
    
    # 正規表現パターン（named capture groupを含む）
    # パラメータ:
    # - available_bandwidth: 利用可能な帯域幅 (Gb/s)
    # - limited_by_speed: 制限されている速度 (GT/s)
    # - capable_bandwidth: 可能な最大帯域幅 (Gb/s)
    # - capable_speed: 可能な最大速度 (GT/s)
    regex_pattern = r"\[\s+\d+\.\d+\]\s+pci\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<available_bandwidth>\d+\.?\d*)\s+Gb/s\s+available\s+PCIe\s+bandwidth,\s+limited\s+by\s+(?P<limited_by_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\s+at\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s+\(capable\s+of\s+(?P<capable_bandwidth>\d+\.?\d*)\s+Gb/s\s+with\s+(?P<capable_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\)"
    
    print("=" * 80)
    print("PCIe帯域幅ログの閾値設定")
    print("=" * 80)
    print()
    
    # ステップ1: パターンを追加
    print("ステップ1: パターンを追加中...")
    try:
        pattern_id = add_pattern(
            db_path=db_path,
            regex_rule=regex_pattern,
            sample_message=sample_message,
            label='normal',  # 正常系として登録（閾値チェックで異常を検知）
            severity='info',
            component='kernel',
            note='PCIe帯域幅ログ（available_bandwidth, limited_by_speed, capable_bandwidth, capable_speedを抽出可能）',
            update_existing=True
        )
        print(f"✅ パターン追加完了 (ID: {pattern_id})")
        print()
    except Exception as e:
        print(f"❌ パターン追加エラー: {e}")
        # 既存パターンを検索
        db = Database(db_path)
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM regex_patterns
            WHERE manual_regex_rule = ? OR sample_message LIKE ?
        """, (regex_pattern, f"%available PCIe bandwidth%"))
        existing = cursor.fetchone()
        if existing:
            pattern_id = existing['id']
            print(f"既存のパターンを使用 (ID: {pattern_id})")
            db.close()
        else:
            print("エラー: パターンが見つかりません")
            db.close()
            sys.exit(1)
    
    # ステップ2: 閾値ルールを追加
    print("ステップ2: 閾値ルールを追加中...")
    
    # ルール1: available_bandwidth が 50 Gb/s 以下の場合に異常
    print("  ルール1: available_bandwidth <= 50 Gb/s の場合に異常")
    try:
        rule_id1 = add_threshold_rule(
            db_path=db_path,
            pattern_id=pattern_id,
            rule_type='threshold',
            field_name='available_bandwidth',
            op='<=',
            threshold_value1=50.0,
            severity_if_match='warning',
            is_abnormal_if_match=True,
            message='PCIe available bandwidth <= 50 Gb/s (性能低下の可能性)',
            is_active=True
        )
        print(f"  ✅ ルール1追加完了 (ID: {rule_id1})")
    except Exception as e:
        print(f"  ⚠️  ルール1追加エラー（既に存在する可能性）: {e}")
    
    # ルール2: available_bandwidth が capable_bandwidth の 50% 以下の場合に異常
    # 注意: これは2つのパラメータを比較するため、別のアプローチが必要
    # 今回は available_bandwidth の絶対値でチェック
    
    # ルール3: available_bandwidth が 30 Gb/s 以下の場合に critical
    print("  ルール2: available_bandwidth <= 30 Gb/s の場合に critical")
    try:
        rule_id2 = add_threshold_rule(
            db_path=db_path,
            pattern_id=pattern_id,
            rule_type='threshold',
            field_name='available_bandwidth',
            op='<=',
            threshold_value1=30.0,
            severity_if_match='critical',
            is_abnormal_if_match=True,
            message='PCIe available bandwidth <= 30 Gb/s (重大な性能低下)',
            is_active=True
        )
        print(f"  ✅ ルール2追加完了 (ID: {rule_id2})")
    except Exception as e:
        print(f"  ⚠️  ルール2追加エラー（既に存在する可能性）: {e}")
    
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
    
    parser = argparse.ArgumentParser(description='Setup PCIe bandwidth threshold')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    
    args = parser.parse_args()
    
    setup_pcie_bandwidth_threshold(args.db)


if __name__ == '__main__':
    main()

