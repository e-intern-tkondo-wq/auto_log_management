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

### 1-3. 実行後の確認クエリ（DB初期状態）

```bash
# DBファイルが存在するかとサイズを確認
ls -lh db/monitor.db

# integrityチェック
sqlite3 db/monitor.db "PRAGMA integrity_check;"

# テーブル件数の初期値を確認（空かどうか）
sqlite3 db/monitor.db "SELECT name, (SELECT COUNT(*) FROM sqlite_master WHERE name = 'log_entries') AS has_log_entries FROM sqlite_master WHERE type='table' LIMIT 5;"
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

### 2-3. 実行後の確認クエリ（取り込み差分と直近ログ）

```bash
# 直近10件のログを確認（取り込み結果が載っているか）
sqlite3 db/monitor.db "SELECT id, host, classification, pattern_id, message FROM log_entries ORDER BY id DESC LIMIT 10;"

# 分類別件数の推移を確認
sqlite3 db/monitor.db "SELECT classification, COUNT(*) AS cnt FROM log_entries GROUP BY classification ORDER BY cnt DESC;"

# 新規パターン数（累計）を確認
sqlite3 db/monitor.db "SELECT COUNT(*) AS pattern_total FROM regex_patterns;"

# 取り込み対象ホストの件数を確認
sqlite3 db/monitor.db "SELECT host, COUNT(*) AS cnt FROM log_entries GROUP BY host ORDER BY cnt DESC LIMIT 5;"
```

---

## ステップ3: PCIe帯域幅パターンの追加

> **参考**: 他のパターンでも変数化を実行したい場合は、[パターン変数化ワークフローガイド](../docs/guides/PATTERN_VARIABILIZATION_WORKFLOW.md)を参照してください。一般的な変数化の手順（named capture groupの追加方法、パターン追加、閾値ルール設定など）を詳しく説明しています。

### 3-1. PCIe帯域幅パターンの追加

以下のコマンドでは、正規表現パターンにnamed capture group `(?P<available_bandwidth>\d+\.\d+)` を追加して、PCIe帯域幅の値を変数として抽出できるようにしています。

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
- パターンが正常に追加されたかどうか
- パターンIDをメモしておく
- コマンド出力に「Has parameters: Yes (available_bandwidth)」と表示されることを確認（named capture groupが正しく検出されている）

**注意:** `add-pattern`コマンド実行時に、正規表現パターンにnamed capture groupが含まれているかどうかを自動で検出し、`has_params`フラグが設定されます。

### 3-2. 追加したパターンIDの確認

```bash
# PCIe帯域幅パターンのIDを取得
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")
echo "Pattern ID: $PATTERN_ID"

# パターンの詳細情報を確認（has_paramsフラグも含む）
sqlite3 db/monitor.db "
SELECT 
    id,
    CASE WHEN manual_regex_rule IS NOT NULL THEN manual_regex_rule ELSE regex_rule END as pattern,
    sample_message,
    note,
    has_params,
    CASE WHEN has_params = 1 THEN 'Yes' ELSE 'No' END as has_parameters
FROM regex_patterns
WHERE id = $PATTERN_ID;
"
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

### 3-4. 実行後の確認クエリ（パターン紐付けとパラメータ抽出）

```bash
# 新パターンに紐付いたログ件数
sqlite3 db/monitor.db "SELECT pattern_id, COUNT(*) AS cnt FROM log_entries WHERE pattern_id = (SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1) GROUP BY pattern_id;"

# パターンのhas_paramsフラグを確認（パラメータ化されていることを確認）
sqlite3 db/monitor.db "SELECT id, has_params, CASE WHEN has_params = 1 THEN 'Yes' ELSE 'No' END as has_parameters FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;"

# 抽出されたパラメータの確認（available_bandwidth）
sqlite3 db/monitor.db "SELECT le.id, le.host, lp.param_value_num, le.classification FROM log_entries le JOIN log_params lp ON le.id = lp.log_id WHERE lp.param_name = 'available_bandwidth' ORDER BY le.id DESC LIMIT 10;"

# is_known の変化を確認
sqlite3 db/monitor.db "SELECT is_known, COUNT(*) AS cnt FROM log_entries GROUP BY is_known;"
```

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

### 4-5. 実行後の確認クエリ（閾値マッチ結果）

```bash
# 閾値違反でabnormalとなった件数
sqlite3 db/monitor.db "SELECT COUNT(*) FROM log_entries WHERE pattern_id = (SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1) AND classification = 'abnormal';"

# anomaly_reason がセットされたレコードを確認
sqlite3 db/monitor.db "SELECT id, severity, anomaly_reason, message FROM log_entries WHERE pattern_id = (SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1) AND anomaly_reason IS NOT NULL ORDER BY id DESC LIMIT 10;"

# 閾値ルールの有効/無効状態を確認
sqlite3 db/monitor.db "SELECT id, is_active, severity_if_match, created_at FROM pattern_rules WHERE pattern_id = (SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1);"
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

### 5-4. 実行後の確認クエリ（ラベル変更の影響範囲）

```bash
# パターン単位での分類内訳を確認
sqlite3 db/monitor.db "SELECT classification, COUNT(*) AS cnt FROM log_entries WHERE pattern_id = (SELECT pattern_id FROM log_entries WHERE id = 1) GROUP BY classification;"

# 異常化したログのサンプルを確認
sqlite3 db/monitor.db "SELECT id, host, severity, message FROM log_entries WHERE pattern_id = (SELECT pattern_id FROM log_entries WHERE id = 1) ORDER BY id DESC LIMIT 10;"
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

### 6-5. 実行後の確認クエリ（ホスト別増分とabnormal詳細）

```bash
# 102ホストの取り込み件数（累計）
sqlite3 db/monitor.db "SELECT COUNT(*) FROM log_entries WHERE host = '172.20.224.102';"

# 直近のabnormalログを確認
sqlite3 db/monitor.db "SELECT id, ts, host, component, severity, anomaly_reason FROM log_entries WHERE classification = 'abnormal' ORDER BY id DESC LIMIT 15;"

# unknown件数の推移確認
sqlite3 db/monitor.db "SELECT COUNT(*) AS unknown_cnt FROM log_entries WHERE classification = 'unknown';"
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

**確認ポイント:**
- パターンが正常に追加されたか
- コマンド出力で「Has parameters: No」と表示されることを確認（このパターンはnamed capture groupを使用していないため）

### 7-3. 追加したパターンにunknownログを紐付け

```bash
# 追加したパターンIDを取得
#ここのLIKE内の内容を決めるのが重要 　
# パターンIDを取得（既に追加済みのixgbeパターンを利用）

# このパターンにマッチするunknownログのみを抽出して確認
# （単純なLIKEだと過剰マッチするため、安全にフィルタする）
python3 scripts/filter_unknown_logs.py \
  --regex "\[\s+\d+\.\d+\]\s+ixgbe\s+([0-9a-fA-F]+:[0-9a-fA-F]+:[0-9a-fA-F]+\.\d+):\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})" \
  --db db/monitor.db \
  --limit 1000000

# 上で確認したIDのみを手動で紐付け（例: ログID 100 をパターンに紐付け）
python3 src/cli_tools.py map-log 100 $IXGBE_PATTERN_ID --db db/monitor.db
```

**注意:** 複数のログを紐付ける場合は、各ログIDに対して `map-log` コマンドを実行する必要があります。

### 7-4. 実行後の確認クエリ（紐付け結果の反映）

```bash
# 手動で紐付けたパターンの分類内訳
sqlite3 db/monitor.db "SELECT classification, COUNT(*) AS cnt FROM log_entries WHERE pattern_id = $IXGBE_PATTERN_ID GROUP BY classification;"

# パターンのhas_paramsフラグを確認
sqlite3 db/monitor.db "SELECT id, has_params, CASE WHEN has_params = 1 THEN 'Yes' ELSE 'No' END as has_parameters FROM regex_patterns WHERE id = $IXGBE_PATTERN_ID;"

# unknown がどれだけ減ったか確認
sqlite3 db/monitor.db "SELECT COUNT(*) AS unknown_cnt FROM log_entries WHERE classification = 'unknown';"

# 直近のパターン紐付けログを確認
sqlite3 db/monitor.db "SELECT id, host, component, message FROM log_entries WHERE pattern_id = $IXGBE_PATTERN_ID ORDER BY id DESC LIMIT 10;"
```

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

### 8-5. 実行後の確認クエリ（LLM処理の成果確認）

```bash
# LLMでauto追加されたパターン数
sqlite3 db/monitor.db "SELECT COUNT(*) FROM regex_patterns WHERE created_by_ai = 1;"

# LLMでabnormalと判定されたログを確認
sqlite3 db/monitor.db "SELECT le.id, le.host, le.classification, le.severity, le.message FROM log_entries le JOIN ai_analyses aa ON le.id = aa.log_id WHERE le.classification = 'abnormal' ORDER BY aa.created_at DESC LIMIT 10;"

# LLM処理済みのunknown残件を確認
sqlite3 db/monitor.db "SELECT COUNT(*) AS remaining_unknown FROM log_entries WHERE classification = 'unknown';"
```

---

## ステップ9: 統計情報とアラートの確認

### 9-1. 統計情報の確認

```bash
# 全体統計を確認
python3 src/cli_tools.py stats --db db/monitor.db
```

### 9-2. アラートの確認（リアルタイム閲覧サーバ）

#### 9-2-1. サーバ起動
```bash
# 簡易アラート閲覧サーバを起動（デフォルト: http://127.0.0.1:8000/view）
python3 scripts/alerts_server.py --db db/monitor.db --host 0.0.0.0 --port 8000
```

#### 9-2-2. ブラウザで確認
- ブラウザで `http://localhost:8000/view` を開く（5秒ごとに自動更新）
- APIで確認する場合: `http://localhost:8000/alerts?limit=50`（JSON）

#### 9-2-3. CLIで確認（補助）
```bash
# アラート一覧（直近20件）
sqlite3 db/monitor.db "SELECT a.id, a.alert_type, a.status, le.id as log_id, le.classification, le.message FROM alerts a JOIN log_entries le ON a.log_id = le.id ORDER BY a.created_at DESC LIMIT 20;"
```

### 9-3. 分類別のログ数確認

```bash
# 分類別のログ数を確認
sqlite3 db/monitor.db "SELECT classification, COUNT(*) as count FROM log_entries GROUP BY classification ORDER BY count DESC;"

# abnormalログの詳細
sqlite3 db/monitor.db "SELECT id, ts, host, component, classification, severity, anomaly_reason FROM log_entries WHERE classification = 'abnormal' ORDER BY id DESC LIMIT 20;"
```

### 9-4. 実行後の確認クエリ（アラートと統計のスナップショット）

```bash
# アラートステータス別件数
sqlite3 db/monitor.db "SELECT status, COUNT(*) FROM alerts GROUP BY status;"

# 直近のアラートと紐付くログの概要
sqlite3 db/monitor.db "SELECT a.id AS alert_id, a.alert_type, a.status, le.id AS log_id, le.classification, le.severity FROM alerts a JOIN log_entries le ON a.log_id = le.id ORDER BY a.created_at DESC LIMIT 10;"

# 総ログ件数とパターン件数のスナップショット
sqlite3 db/monitor.db "SELECT (SELECT COUNT(*) FROM log_entries) AS log_total, (SELECT COUNT(*) FROM regex_patterns) AS pattern_total;"
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

# パターン追加時の確認: コマンド出力で「Has parameters: Yes」または「Has parameters: No」が表示されることを確認
# パターンIDとhas_paramsフラグを確認
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%キーワード%' ORDER BY id DESC LIMIT 1;")
sqlite3 db/monitor.db "SELECT id, has_params FROM regex_patterns WHERE id = $PATTERN_ID;"

# ログをパターンに紐付け
python3 src/cli_tools.py map-log <LOG_ID> <PATTERN_ID> --db db/monitor.db
```

**B. LLMアナライザーを使用する場合:**

```bash
# unknownログをLLMで解析（自動処理あり）
python3 src/llm_analyzer.py --db db/monitor.db --limit 20
```

### 10-4. 実行後の確認クエリ（バッチ取り込み後の整合性）

```bash
# ホスト別件数を確認（103〜116の取り込み状況）
sqlite3 db/monitor.db "SELECT host, COUNT(*) AS cnt FROM log_entries WHERE host LIKE '172.20.224.%' GROUP BY host ORDER BY host;"

# unknown・abnormalの現在値
sqlite3 db/monitor.db "SELECT classification, COUNT(*) AS cnt FROM log_entries GROUP BY classification;"

# 直近20件で未分類が紛れていないか確認
sqlite3 db/monitor.db "SELECT id, host, classification, message FROM log_entries ORDER BY id DESC LIMIT 20;"
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

### 11-5. 実行後の確認クエリ（最終スナップショット）

```bash
# 全体サマリ（ログ総数・パターン総数・unknown残数）
sqlite3 db/monitor.db "SELECT (SELECT COUNT(*) FROM log_entries) AS log_total, (SELECT COUNT(*) FROM regex_patterns) AS pattern_total, (SELECT COUNT(*) FROM log_entries WHERE classification = 'unknown') AS unknown_remaining;"

# 異常ログの主要項目を最終確認
sqlite3 db/monitor.db "SELECT id, ts, host, component, severity, anomaly_reason FROM log_entries WHERE classification = 'abnormal' ORDER BY id DESC LIMIT 15;"
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
# パターンの詳細を確認（has_paramsフラグも含む）
sqlite3 db/monitor.db "SELECT id, regex_rule, manual_regex_rule, sample_message, has_params FROM regex_patterns WHERE id = <PATTERN_ID>;"

# パラメータ化されているかどうかも確認
sqlite3 db/monitor.db "
SELECT 
    id,
    CASE WHEN manual_regex_rule IS NOT NULL THEN manual_regex_rule ELSE regex_rule END as pattern,
    has_params,
    CASE WHEN has_params = 1 THEN 'Yes (parameterized)' ELSE 'No' END as parameter_status
FROM regex_patterns 
WHERE id = <PATTERN_ID>;
"

# ログメッセージとパターンを手動で確認
python3 -c "
import re
pattern = '正規表現パターン'
message = 'ログメッセージ'
if re.search(pattern, message):
    print('Match!')
    # named capture groupがあれば抽出
    match = re.search(pattern, message)
    if match:
        groups = match.groupdict()
        if groups:
            print(f'Extracted parameters: {groups}')
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
-- パターンの詳細（has_paramsフラグも含む）
SELECT id, regex_rule, manual_regex_rule, sample_message, label, severity, has_params, total_count 
FROM regex_patterns 
WHERE id = <PATTERN_ID>;

-- ラベル別のパターン一覧
SELECT id, label, severity, has_params, sample_message 
FROM regex_patterns 
WHERE label = 'abnormal' 
ORDER BY total_count DESC 
LIMIT 20;

-- パラメータ化されているパターンの一覧
SELECT id, sample_message, note, has_params
FROM regex_patterns
WHERE has_params = 1
ORDER BY id DESC;
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
