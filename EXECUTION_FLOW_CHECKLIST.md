# ログ処理システム 実行フロー確認チェックリスト

このドキュメントは、ログ処理システムの各機能が正しく動作しているかを1つ1つコマンドを叩いて確認するためのフローです。

## 前提条件

- データベース: `db/monitor.db`
- ログファイル: `log_flower/bootlog/` 配下のログファイル
- Python環境: 仮想環境が有効化されていること

---

## ステップ1: 初期データベースの準備

### 1-1. データベースの状態確認

```bash
# データベースが存在するか確認
ls -la db/monitor.db

# 統計情報を確認（既存データがある場合）
python3 src/cli_tools.py stats --db db/monitor.db
```

### 1-2. 必要に応じてデータベースをリセット（オプション）

```bash
# 既存データベースをバックアップ
cp db/monitor.db db/monitor.db.backup

# データベースを削除して再作成（注意: 全データが消えます）
rm db/monitor.db
python3 -c "from src.database import Database; Database('db/monitor.db')"
```

---

## ステップ2: 172.20.224.101.log-20250714 の取り込みとテンプレート作成

### 2-1. ログファイルの取り込み

```bash
python3 src/ingest.py log_flower/bootlog/172.20.224.101.log-20250714 --db db/monitor.db -v
```

**確認ポイント:**
- 取り込みが正常に完了したか
- 新規パターンが作成されたか
- エラーが発生していないか

### 2-2. 取り込み結果の確認

```bash
# 統計情報を確認
python3 src/cli_tools.py stats --db db/monitor.db

# 未知パターンの確認
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 20
```

---

## ステップ3: PCIe帯域幅パターンの追加

### 3-1. PCIe帯域幅パターンの追加

```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+pci\s+\S+:\s+(?P<available_bandwidth>\d+\.\d+)\s+Gb/s\s+available\s+PCIe\s+bandwidth" \
  "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth" \
  --label normal \
  --severity info \
  --component kernel \
  --note "PCIe帯域幅ログ（パラメータ: available_bandwidth）" \
  --db db/monitor.db
```

**確認ポイント:**
- パターンが正常に追加されたか
- パターンIDをメモしておく

### 3-2. 追加したパターンIDの確認

```bash
# PCIe帯域幅パターンのIDを取得
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")
echo "Pattern ID: $PATTERN_ID"
```

### 3-3. 既存のログを新しいパターンにマッチさせて再処理

**重要**: ステップ2で取り込んだログは、この時点ではまだパターンが存在しなかったため、`is_known=0`として保存されています。パターンを追加した後、既存のログをこのパターンにマッチさせて、パラメータ抽出と異常判定を実行する必要があります。

```bash
# パターンIDを取得（前ステップで取得済みの場合）
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")

# 既存のログを再処理（パラメータ抽出と異常判定を実行）
python3 src/cli_tools.py reprocess-pattern $PATTERN_ID --db db/monitor.db -v
```

**確認ポイント:**
- 既存のログがパターンにマッチしたか
- パラメータが抽出されたか
- 異常判定が実行されたか

---

## ステップ4: PCIe帯域幅の閾値ルール追加

### 4-1. 閾値ルールの追加

```bash
# パターンIDを取得（前ステップで取得済みの場合）
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")

# 閾値ルールを追加
python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name available_bandwidth \
  --op '<' \
  --threshold 1000.0 \
  --severity warning \
  --message "PCIe bandwidth < 10 Gb/s" \
  --db db/monitor.db
```

**確認ポイント:**
- ルールが正常に追加されたか
- ルールIDをメモしておく

### 4-2. 閾値ルールの確認

```bash
# 追加したルールを確認
sqlite3 db/monitor.db "SELECT * FROM pattern_rules WHERE pattern_id = $PATTERN_ID;"
```

### 4-3. 閾値ルール追加後の既存ログの再処理

**重要**: 閾値ルールを追加した後、既存のログに対して異常判定を再実行する必要があります。これにより、既に取り込まれているログが閾値違反でabnormalと判定されます。

```bash
# パターンIDを取得
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")

# 既存のログを再処理（異常判定を再実行）
python3 src/cli_tools.py reprocess-pattern $PATTERN_ID --db db/monitor.db -v
```

**確認ポイント:**
- 閾値違反のログがabnormalと判定されたか
- `anomaly_reason`が正しく設定されたか

### 4-4. 閾値違反ログの確認

```bash
# 閾値違反でabnormalと判定されたログを確認
sqlite3 db/monitor.db "SELECT le.id, le.ts, le.host, le.classification, le.severity, le.anomaly_reason, le.message, lp.param_value_num FROM log_entries le JOIN log_params lp ON le.id = lp.log_id WHERE lp.param_name = 'available_bandwidth' AND le.classification = 'abnormal' LIMIT 10;"
```

---

## ステップ5: ログID 1の正規化パターンをunknownからabnormalに変更

### 5-1. ログID 1の情報確認

```bash
# ログID 1の情報を確認
sqlite3 db/monitor.db "SELECT id, pattern_id, classification, message FROM log_entries WHERE id = 1;"

# パターンIDを確認
PATTERN_ID_1=$(sqlite3 db/monitor.db "SELECT pattern_id FROM log_entries WHERE id = 1;")
echo "Pattern ID for log 1: $PATTERN_ID_1"
```

### 5-2. パターンのラベルをabnormalに変更

**方法A: パターンのラベルを更新（推奨）**

```bash
# ログID 1のパターンIDを取得
PATTERN_ID_1=$(sqlite3 db/monitor.db "SELECT pattern_id FROM log_entries WHERE id = 1;")

# パターンのラベルをabnormalに更新（これにより、このパターンに属するすべてのログがabnormalになる）
python3 src/cli_tools.py update-label \
  $PATTERN_ID_1 \
  abnormal \
  --severity warning \
  --note "手動でabnormalに設定" \
  --db db/monitor.db
```

**方法B: 特定のログエントリのみをabnormalに変更（SQLite直接）**

```bash
# ログID 1のみをabnormalに変更
sqlite3 db/monitor.db "UPDATE log_entries SET classification = 'abnormal', severity = 'warning' WHERE id = 1;"
```

### 5-3. 変更結果の確認

```bash
# ログID 1の状態を確認
sqlite3 db/monitor.db "SELECT id, pattern_id, classification, severity, message FROM log_entries WHERE id = 1;"
```

---

## ステップ6: 172.20.224.102.log-20250714 の取り込み

### 6-1. ログファイルの取り込み

```bash
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v
```

**確認ポイント:**
- 取り込みが正常に完了したか
- 新規パターンが作成されたか

### 6-2. abnormalログの確認

```bash
# abnormalに分類されたログを確認
sqlite3 db/monitor.db "SELECT id, ts, host, component, classification, severity, anomaly_reason, message FROM log_entries WHERE classification = 'abnormal' ORDER BY id DESC LIMIT 20;"

# ステップ5で設定したパターンに属するabnormalログを確認
PATTERN_ID_1=$(sqlite3 db/monitor.db "SELECT pattern_id FROM log_entries WHERE id = 1;")
sqlite3 db/monitor.db "SELECT id, ts, host, component, classification, severity, message FROM log_entries WHERE pattern_id = $PATTERN_ID_1 AND classification = 'abnormal' LIMIT 10;"
```

### 6-3. 閾値違反によるabnormalログの確認

```bash
# PCIe帯域幅の閾値違反によるabnormalログを確認
sqlite3 db/monitor.db "SELECT le.id, le.ts, le.host, le.component, le.classification, le.severity, le.anomaly_reason, le.message FROM log_entries le JOIN log_params lp ON le.id = lp.log_id WHERE lp.param_name = 'available_bandwidth' AND CAST(lp.param_value_num AS REAL) < 30.0 AND le.classification = 'abnormal' LIMIT 10;"
```

### 6-4. unknownログの確認

```bash
# unknownに分類されたログを確認
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 20

# より詳細な情報を確認
sqlite3 db/monitor.db "SELECT id, ts, host, component, message FROM log_entries WHERE classification = 'unknown' ORDER BY id DESC LIMIT 20;"
```

---

## ステップ7: unknownログの手動パターン追加

### 7-1. unknownログの確認と選択

```bash
# unknownログの一覧を確認
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 50

# 特定のログの詳細を確認（例: ログID 100）
sqlite3 db/monitor.db "SELECT id, message FROM log_entries WHERE id = 100;"
```

### 7-2. ixgbeドライバのパターンを追加

```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+ixgbe\s+([0-9a-fA-F]+:[0-9a-fA-F]+:[0-9a-fA-F]+\.\d+):\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})" \
  "[   26.518341] ixgbe 0000:0b:00.0: 5c:ff:35:fe:1c:58" \
  --label normal \
  --severity info \
  --component kernel \
  --note "ixgbe ドライバの初期化ログ。PCI アドレスと MAC アドレスを含む通常メッセージ" \
  --db db/monitor.db
```

### 7-3. 追加したパターンにunknownログを紐付け

```bash
# 追加したパターンIDを取得
#ここのLIKE内の内容を決めるのが重要 　
IXGBE_PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%ixgbe%' ORDER BY id DESC LIMIT 1;")
echo "ixgbe Pattern ID: $IXGBE_PATTERN_ID"

# このパターンに正規表現でマッチするunknownログのみを抽出して確認
# （単純なLIKEだと過剰マッチするため、安全にフィルタする）
python3 - <<'PY'
import re, sqlite3
pat = re.compile(r"\[\s+\d+\.\d+\]\s+ixgbe\s+([0-9a-fA-F]+:[0-9a-fA-F]+:[0-9a-fA-F]+\.\d+):\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})")
conn = sqlite3.connect("db/monitor.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, message FROM log_entries WHERE classification = 'unknown' AND message LIKE '%ixgbe%'"
).fetchall()
for r in rows:
    m = pat.search(r["message"])
    if m:
        print(f"{r['id']}\t{m.group(1)}\t{m.group(2)}\t{r['message'][:120]}")
conn.close()
PY

# 上で確認したIDのみを手動で紐付け（例: ログID 100 をパターンに紐付け）
python3 src/cli_tools.py map-log 100 $IXGBE_PATTERN_ID --db db/monitor.db
```

**注意:** 複数のログを紐付ける場合は、各ログIDに対して `map-log` コマンドを実行する必要があります。

---

## ステップ8: LLMアナライザーによるunknownログの処理

### 8-1. LLMアナライザーの実行（自動処理なし）

```bash
# unknownログをLLMで解析（結果のみ表示、自動処理なし）
python3 src/llm_analyzer.py --db db/monitor.db --limit 10 --no-auto-add
```

### 8-2. 特定のログIDをLLMで解析

```bash
# 特定のログIDを解析（例: ログID 200）
python3 src/llm_analyzer.py --db db/monitor.db --log-id 200
```

### 8-3. LLMアナライザーの自動処理実行

```bash
# unknownログをLLMで解析し、自動的にパターン追加・アラート作成を行う
python3 src/llm_analyzer.py --db db/monitor.db --limit 10

# 特定のログIDを解析して自動処理
python3 src/llm_analyzer.py --db db/monitor.db --log-id 200 --auto-process
```

**確認ポイント:**
- LLM解析が正常に完了したか
- パターンが追加されたか（normalと判断された場合）
- アラートが作成されたか（abnormalと判断された場合）

### 8-4. LLM解析結果の確認

```bash
# LLM解析結果を確認
sqlite3 db/monitor.db "SELECT le.id, le.message, aa.response FROM log_entries le JOIN ai_analyses aa ON le.id = aa.log_id ORDER BY aa.created_at DESC LIMIT 10;"
```

---

## ステップ9: 統計情報とアラートの確認

### 9-1. 統計情報の確認

```bash
# 全体統計を確認
python3 src/cli_tools.py stats --db db/monitor.db
```

### 9-2. アラートの確認

```bash
# アラート一覧を確認
sqlite3 db/monitor.db "SELECT a.id, a.alert_type, a.status, le.id as log_id, le.classification, le.message FROM alerts a JOIN log_entries le ON a.log_id = le.id ORDER BY a.created_at DESC LIMIT 20;"
```

### 9-3. 分類別のログ数確認

```bash
# 分類別のログ数を確認
sqlite3 db/monitor.db "SELECT classification, COUNT(*) as count FROM log_entries GROUP BY classification ORDER BY count DESC;"

# abnormalログの詳細
sqlite3 db/monitor.db "SELECT id, ts, host, component, classification, severity, anomaly_reason FROM log_entries WHERE classification = 'abnormal' ORDER BY id DESC LIMIT 20;"
```

---

## ステップ10: 残りのログファイルの処理（172.20.224.103.log-20250714 ～ 172.20.224.116.log-20250714）

### 10-1. 各ログファイルの取り込み

```bash
# 103から116まで順番に取り込む
for i in {103..116}; do
  echo "Processing 172.20.224.$i.log-20250714..."
  python3 src/ingest.py log_flower/bootlog/172.20.224.$i.log-20250714 --db db/monitor.db -v
done
```

**注意:** 105と107は日付が異なる可能性があります。実際のファイル名を確認してください。

```bash
# 実際のファイル名を確認
ls -la log_flower/bootlog/172.20.224.*.log-*

# 105と107の実際のファイル名で取り込み
python3 src/ingest.py log_flower/bootlog/172.20.224.105.log-20251015 --db db/monitor.db -v
python3 src/ingest.py log_flower/bootlog/172.20.224.107.log-20250805 --db db/monitor.db -v
```

### 10-2. 各取り込み後の確認

各ファイル取り込み後に以下を確認：

```bash
# 統計情報を確認
python3 src/cli_tools.py stats --db db/monitor.db

# unknownログを確認
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 20

# abnormalログを確認
sqlite3 db/monitor.db "SELECT COUNT(*) FROM log_entries WHERE classification = 'abnormal';"
```

### 10-3. unknownログの処理

各取り込み後、unknownログに対して以下を実行：

**A. 手動パターン追加が可能な場合:**

```bash
# unknownログを確認
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 50

# パターンを追加（例）
python3 src/cli_tools.py add-pattern \
  "正規表現パターン" \
  "サンプルメッセージ" \
  --label normal \
  --severity info \
  --component kernel \
  --note "説明" \
  --db db/monitor.db

# ログをパターンに紐付け
python3 src/cli_tools.py map-log <LOG_ID> <PATTERN_ID> --db db/monitor.db
```

**B. LLMアナライザーを使用する場合:**

```bash
# unknownログをLLMで解析（自動処理あり）
python3 src/llm_analyzer.py --db db/monitor.db --limit 20
```

---

## ステップ11: 最終確認

### 11-1. 全体統計の確認

```bash
# 最終統計を確認
python3 src/cli_tools.py stats --db db/monitor.db
```

### 11-2. パターン数の確認

```bash
# パターン数を確認
sqlite3 db/monitor.db "SELECT label, COUNT(*) as count FROM regex_patterns GROUP BY label ORDER BY count DESC;"

# 手動パターンと自動パターンの数
sqlite3 db/monitor.db "SELECT COUNT(*) as manual_patterns FROM regex_patterns WHERE manual_regex_rule IS NOT NULL;"
sqlite3 db/monitor.db "SELECT COUNT(*) as auto_patterns FROM regex_patterns WHERE regex_rule IS NOT NULL;"
```

### 11-3. 閾値ルールの確認

```bash
# すべての閾値ルールを確認
sqlite3 db/monitor.db "SELECT pr.id, pr.pattern_id, pr.rule_type, pr.field_name, pr.op, pr.threshold_value1, pr.severity_if_match, rp.sample_message FROM pattern_rules pr JOIN regex_patterns rp ON pr.pattern_id = rp.id WHERE pr.is_active = 1;"
```

### 11-4. アラートの最終確認

```bash
# すべてのアラートを確認
sqlite3 db/monitor.db "SELECT a.id, a.alert_type, a.status, COUNT(*) as count FROM alerts a GROUP BY a.alert_type, a.status ORDER BY count DESC;"

# pending状態のアラートを確認
sqlite3 db/monitor.db "SELECT a.id, a.alert_type, le.id as log_id, le.classification, le.message FROM alerts a JOIN log_entries le ON a.log_id = le.id WHERE a.status = 'pending' ORDER BY a.created_at DESC LIMIT 20;"
```

---

## トラブルシューティング

### データベース接続エラー

```bash
# データベースファイルの権限を確認
ls -la db/monitor.db

# データベースの整合性を確認
sqlite3 db/monitor.db "PRAGMA integrity_check;"
```

### パターンがマッチしない

```bash
# パターンの詳細を確認
sqlite3 db/monitor.db "SELECT id, regex_rule, manual_regex_rule, sample_message FROM regex_patterns WHERE id = <PATTERN_ID>;"

# ログメッセージとパターンを手動で確認
python3 -c "
import re
pattern = '正規表現パターン'
message = 'ログメッセージ'
if re.search(pattern, message):
    print('Match!')
else:
    print('No match')
"
```

### LLMアナライザーが動作しない

```bash
# APIキーが設定されているか確認
echo $OPENAI_API_KEY

# .envファイルを確認
cat .env | grep OPENAI_API_KEY
```

---

## 補足: よく使うSQLクエリ

### ログエントリの詳細確認

```sql
-- 特定のログIDの詳細
SELECT id, ts, host, component, classification, severity, pattern_id, message 
FROM log_entries 
WHERE id = 1;

-- パターンに属するログ一覧
SELECT id, ts, host, component, classification, message 
FROM log_entries 
WHERE pattern_id = <PATTERN_ID> 
ORDER BY id DESC 
LIMIT 20;

-- パラメータが抽出されたログ
SELECT le.id, le.message, lp.param_name, lp.param_value_num, lp.param_value_text 
FROM log_entries le 
JOIN log_params lp ON le.id = lp.log_id 
WHERE lp.param_name = 'available_bandwidth' 
ORDER BY le.id DESC 
LIMIT 20;
```

### パターンの詳細確認

```sql
-- パターンの詳細
SELECT id, regex_rule, manual_regex_rule, sample_message, label, severity, total_count 
FROM regex_patterns 
WHERE id = <PATTERN_ID>;

-- ラベル別のパターン一覧
SELECT id, label, severity, sample_message 
FROM regex_patterns 
WHERE label = 'abnormal' 
ORDER BY total_count DESC 
LIMIT 20;
```

---

## まとめ

このフローに従って、各ステップを1つずつ実行し、期待通りの結果が得られるか確認してください。

各ステップで以下を確認することが重要です：
1. コマンドが正常に実行されたか
2. データベースに期待通りのデータが追加されたか
3. 分類（normal/abnormal/unknown）が正しく行われているか
4. パターンマッチングが正しく動作しているか
5. 閾値チェックが正しく動作しているか
6. LLMアナライザーが正しく動作しているか

