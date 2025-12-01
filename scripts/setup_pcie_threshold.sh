#!/bin/bash
# PCIe帯域幅ログの閾値設定スクリプト
# add_threshold_rule.py を使用して閾値を設定

set -e

DB_PATH="${1:-db/monitor.db}"

echo "=================================================================================="
echo "PCIe帯域幅ログの閾値設定"
echo "=================================================================================="
echo ""

# ステップ1: パターンを追加
echo "ステップ1: パターンを追加中..."
PATTERN_ID=$(python3 src/cli_tools.py add-pattern \
    "\[\s+\d+\.\d+\]\s+pci\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<available_bandwidth>\d+\.?\d*)\s+Gb/s\s+available\s+PCIe\s+bandwidth,\s+limited\s+by\s+(?P<limited_by_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\s+at\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s+\(capable\s+of\s+(?P<capable_bandwidth>\d+\.?\d*)\s+Gb/s\s+with\s+(?P<capable_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\)" \
    "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)" \
    --label normal \
    --severity info \
    --component kernel \
    --note "PCIe帯域幅ログ（available_bandwidth, limited_by_speed, capable_bandwidth, capable_speedを抽出可能）" \
    --db "$DB_PATH" 2>&1 | grep -oP 'ID: \K\d+' | head -1)

if [ -z "$PATTERN_ID" ]; then
    # 既存パターンを検索
    PATTERN_ID=$(sqlite3 "$DB_PATH" "SELECT id FROM regex_patterns WHERE sample_message LIKE '%available PCIe bandwidth%' AND manual_regex_rule IS NOT NULL ORDER BY id DESC LIMIT 1")
    if [ -z "$PATTERN_ID" ]; then
        echo "❌ パターンの追加または検索に失敗しました"
        exit 1
    fi
    echo "既存のパターンを使用 (ID: $PATTERN_ID)"
else
    echo "✅ パターン追加完了 (ID: $PATTERN_ID)"
fi
echo ""

# ステップ2: 閾値ルールを追加
echo "ステップ2: 閾値ルールを追加中..."
echo ""

# ルール1: available_bandwidth <= 50.0 Gb/s の場合に warning
echo "  ルール1: available_bandwidth <= 50.0 Gb/s → warning"
python3 scripts/add_threshold_rule.py \
    --pattern-id "$PATTERN_ID" \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 50.0 \
    --severity warning \
    --message "PCIe available bandwidth <= 50 Gb/s (性能低下の可能性)" \
    --db "$DB_PATH" || echo "  ⚠️  ルール1追加エラー（既に存在する可能性）"
echo ""

# ルール2: available_bandwidth <= 30.0 Gb/s の場合に critical
echo "  ルール2: available_bandwidth <= 30.0 Gb/s → critical"
python3 scripts/add_threshold_rule.py \
    --pattern-id "$PATTERN_ID" \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 30.0 \
    --severity critical \
    --message "PCIe available bandwidth <= 30 Gb/s (重大な性能低下)" \
    --db "$DB_PATH" || echo "  ⚠️  ルール2追加エラー（既に存在する可能性）"
echo ""

echo "=================================================================================="
echo "設定完了"
echo "=================================================================================="
echo ""
echo "パターンID: $PATTERN_ID"
echo "設定された閾値:"
echo "  - available_bandwidth <= 50.0 Gb/s → warning"
echo "  - available_bandwidth <= 30.0 Gb/s → critical"
echo ""
echo "次のステップ:"
echo "  1. ログを取り込む: python3 src/ingest.py <log_file>"
echo "  2. 設定状況を確認: python3 scripts/check_pcie_threshold_status.py"

