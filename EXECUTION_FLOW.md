# 動作確認フロー実行手順

このドキュメントでは、1-7のフローを順番に実行する手順を説明します。

## 前提条件

- データベース: `db/monitor.db`（デフォルト）
- ログファイル: `log_flower/bootlog/` 配下のログファイルを使用

---

## ステップ1: いくつかのファイルを入力にしてテンプレDBを作成する

初期のログファイルを取り込んで、パターン（テンプレート）をデータベースに作成します。

```bash
# 例: 1つのログファイルを取り込む
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v

# 複数のファイルを取り込む場合
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v
python3 src/ingest.py log_flower/bootlog/172.20.224.103.log-20250714 --db db/monitor.db -v
python3 src/ingest.py log_flower/bootlog/172.20.224.104.log-20250714 --db db/monitor.db -v
```

**処理内容**:
- ログファイルを読み込み、各行をパース
- `abstract_message()` で正規表現パターンを自動生成
- 既存パターンとマッチング、新規パターンは `regex_patterns` テーブルに登録
- ログエントリを `log_entries` テーブルに保存

**確認方法**:
```bash
# 統計情報を確認
python3 src/cli_tools.py stats --db db/monitor.db

# パターン数を確認（SQLiteで直接確認）
sqlite3 db/monitor.db "SELECT COUNT(*) FROM regex_patterns;"
```

---

## ステップ2: ログを実際に入れる

新しいログファイルを取り込んで、既存のパターンとマッチングするか確認します。

```bash
# 新しいログファイルを取り込む
python3 src/ingest.py log_flower/bootlog/172.20.224.105.log-20251015 --db db/monitor.db -v
```

**処理内容**:
- ログを取り込み、既存パターンとマッチング
- 既知ログ（`is_known=1`）と未知ログ（`is_known=0`）に分類

---

## ステップ3: ログが作ったテンプレの通りかどうか判断する

既知/未知の判定結果を確認します。

```bash
# 統計情報を確認（既知/未知の分布を確認）
python3 src/cli_tools.py stats --db db/monitor.db

# 未知パターンの一覧を表示
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 20

# SQLiteで直接確認
sqlite3 db/monitor.db "
SELECT 
    CASE WHEN is_known = 1 THEN '既知' ELSE '未知' END as status,
    COUNT(*) as count
FROM log_entries
GROUP BY is_known;
"
```

**判断基準**:
- `is_known = 1`: 既知ログ（テンプレートにマッチ）
- `is_known = 0`: 未知ログ（テンプレートにマッチしない）

---

## ステップ4: テンプレの通り（既知）であれば、まずそのテンプレがエラーなどの異常系のテンプレかどうかを判断する

既知ログのパターンが正常系か異常系かを確認・分類します。

```bash
# 既知パターンのラベルを確認
sqlite3 db/monitor.db "
SELECT 
    id,
    label,
    severity,
    sample_message,
    total_count
FROM regex_patterns
WHERE id IN (
    SELECT DISTINCT pattern_id 
    FROM log_entries 
    WHERE is_known = 1 AND pattern_id IS NOT NULL
)
ORDER BY total_count DESC
LIMIT 20;
"

#host 101以外のログ
SELECT 
    DISTINCT(r.id),
    r.label,
    r.severity,
    r.sample_message,
    r.total_count,
    l.host
FROM regex_patterns r
JOIN log_entries l ON l.pattern_id = r.id
WHERE r.id IN (
    SELECT DISTINCT pattern_id 
    FROM log_entries 
    WHERE is_known = 1 AND pattern_id IS NOT NULL
) AND l.host!="172.20.224.101"
ORDER BY total_count DESC
LIMIT 20;

# 特定のパターンの詳細を確認
sqlite3 db/monitor.db "
SELECT 
    id,
    regex_rule,
    manual_regex_rule,
    sample_message,
    label,
    severity,
    note
FROM regex_patterns
WHERE id = <pattern_id>;
"
```

**ラベルの意味**:
- `normal`: 正常系
- `abnormal`: 異常系（エラーなど）
- `unknown`: 未分類
- `ignore`: 無視（ノイズなど）

**ラベルの更新方法**:
```bash
# 正常系としてマーク
python3 src/cli_tools.py update-label <pattern_id> normal --severity info --note "正常ログ"

# 異常系としてマーク
python3 src/cli_tools.py update-label <pattern_id> abnormal --severity critical --note "エラーログ"
```

---

## ステップ5': 閾値を手動で設定するコマンドをあらかじめ実行しておく

正常系のパターンに対して、閾値チェックのルールを設定します。

### 方法1: SQLiteで直接設定

```bash
sqlite3 db/monitor.db "
INSERT INTO pattern_rules (
    pattern_id,
    rule_type,
    field_name,
    op,
    threshold_value1,
    threshold_value2,
    severity_if_match,
    is_abnormal_if_match,
    message,
    is_active
) VALUES (
    <pattern_id>,           -- パターンID（例: 100）
    'threshold',           -- ルールタイプ: 'threshold', 'contains', 'regex'
    '<param_name>',        -- パラメータ名（例: 'temp', 'gran_size'）
    '>',                   -- 演算子: '>', '<', '>=', '<=', '==', '!=', 'between', 'not_between'
    <threshold_value>,     -- 閾値1（例: 80.0）
    NULL,                  -- 閾値2（'between' の場合のみ使用）
    'critical',           -- 異常時の重要度: 'info', 'warning', 'critical'
    1,                     -- 異常フラグ（1=異常, 0=正常）
    'GPU temp > 80°C',     -- 異常理由メッセージ
    1                      -- アクティブフラグ（1=有効, 0=無効）
);
"
```

### 方法2: スクリプトを使用（推奨）

`scripts/add_threshold_rule.py` を使用:

```bash
# 閾値チェック（温度が80度を超えた場合）
python3 scripts/add_threshold_rule.py \
    --pattern-id <pattern_id> \
    --rule-type threshold \
    --field-name temp \
    --op '>' \
    --threshold 80.0 \
    --severity critical \
    --message "GPU temp > 80°C"

# 文字列含有チェック（メッセージに "ERROR" が含まれる場合）
python3 scripts/add_threshold_rule.py \
    --pattern-id <pattern_id> \
    --rule-type contains \
    --threshold "ERROR" \
    --severity critical

# 正規表現チェック
python3 scripts/add_threshold_rule.py \
    --pattern-id <pattern_id> \
    --rule-type regex \
    --threshold ".*ERROR.*" \
    --severity warning
```

### ルールタイプの例

#### 1. 閾値チェック（threshold）

```sql
-- 例: 温度が80度を超えた場合に異常
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, is_abnormal_if_match, message
) VALUES (
    100, 'threshold', 'temp', '>',
    80.0, 'critical', 1, 'GPU temp > 80°C'
);
```

#### 2. 文字列含有チェック（contains）

```sql
-- 例: メッセージに "ERROR" が含まれる場合に異常
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, is_abnormal_if_match, message
) VALUES (
    100, 'contains', NULL, 'contains',
    'ERROR', 'critical', 1, 'Error message detected'
);
```

#### 3. 正規表現チェック（regex）

```sql
-- 例: メッセージが特定のパターンにマッチする場合に異常
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, is_abnormal_if_match, message
) VALUES (
    100, 'regex', NULL, 'matches',
    '.*ERROR.*', 'critical', 1, 'Error pattern matched'
);
```

**注意**: 閾値チェックを使用するには、パターンに **named capture group** が必要です。手動パターンを追加する際に `(?P<param_name>...)` 形式を使用してください。

### 方法3: 既存の自動生成パターンにnamed capture groupsを追加する手順

既存のログを取り込んだ際に、`abstract_message()` で自動生成されたパターンには named capture groups が含まれていません。閾値チェックを行うには、**named capture groups を含む手動パターンを追加**する必要があります。

#### ステップ1: 対象ログを確認

```bash
# 対象のログメッセージを確認
# 例: PCIe帯域幅ログ
# Jul 14 11:20:17 172.20.224.102 kernel: [   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)

# 既存の自動生成パターンを確認
sqlite3 db/monitor.db "
SELECT id, regex_rule, sample_message, total_count
FROM regex_patterns
WHERE sample_message LIKE '%available PCIe bandwidth%'
  AND regex_rule IS NOT NULL
  AND manual_regex_rule IS NULL
ORDER BY total_count DESC
LIMIT 5;
"
```

#### ステップ2: named capture groupsを含む手動パターンを追加

自動生成パターンをベースに、**数値部分を named capture groups に置き換えた手動パターン**を追加します。

```bash
# 手動パターンを追加（named capture groupsを含む）
python3 src/cli_tools.py add-pattern \
    "\[\s+\d+\.\d+\]\s+pci\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<available_bandwidth>\d+\.?\d*)\s+Gb/s\s+available\s+PCIe\s+bandwidth,\s+limited\s+by\s+(?P<limited_by_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\s+at\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s+\(capable\s+of\s+(?P<capable_bandwidth>\d+\.?\d*)\s+Gb/s\s+with\s+(?P<capable_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\)" \
    "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)" \
    --label normal \
    --severity info \
    --component kernel \
    --note "PCIe帯域幅ログ（available_bandwidth, limited_by_speed, capable_bandwidth, capable_speedを抽出可能）" \
    --db db/monitor.db
```

**ポイント**:
- `\d+\.?\d*` → `(?P<available_bandwidth>\d+\.?\d*)` のように、数値部分を named capture group に置き換える
- 抽出したいパラメータごとに `(?P<param_name>pattern)` 形式で定義
- 手動パターンは `manual_regex_rule` カラムに保存され、自動生成パターンより優先される

#### ステップ3: パターンIDを確認

```bash
# 追加したパターンのIDを確認
PATTERN_ID=$(sqlite3 db/monitor.db "
SELECT id FROM regex_patterns
WHERE manual_regex_rule LIKE '%available_bandwidth%'
ORDER BY id DESC
LIMIT 1;
")
echo "パターンID: $PATTERN_ID"
```

#### ステップ4: 閾値ルールを設定（add_threshold_rule.py を使用）

```bash
# ルール1: available_bandwidth <= 50.0 Gb/s の場合に warning
python3 scripts/add_threshold_rule.py \
    --pattern-id $PATTERN_ID \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 50.0 \
    --severity warning \
    --message "PCIe available bandwidth <= 50 Gb/s (性能低下の可能性)" \
    --db db/monitor.db

# ルール2: available_bandwidth <= 30.0 Gb/s の場合に critical
python3 scripts/add_threshold_rule.py \
    --pattern-id $PATTERN_ID \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 30.0 \
    --severity critical \
    --message "PCIe available bandwidth <= 30 Gb/s (重大な性能低下)" \
    --db db/monitor.db
```

#### ステップ5: 実装状況の確認

```bash
# 設定状況を確認
python3 scripts/check_pcie_threshold_status.py --db db/monitor.db
```

または、手動で確認:

```bash
# 1. パターンの確認
sqlite3 db/monitor.db "
SELECT 
    id,
    manual_regex_rule,
    sample_message,
    label,
    severity
FROM regex_patterns
WHERE manual_regex_rule LIKE '%available_bandwidth%'
ORDER BY id DESC
LIMIT 1;
"

# 2. 閾値ルールの確認
sqlite3 db/monitor.db "
SELECT 
    pr.id,
    pr.rule_type,
    pr.field_name,
    pr.op,
    pr.threshold_value1,
    pr.severity_if_match,
    pr.message,
    pr.is_active
FROM pattern_rules pr
WHERE pr.pattern_id = $PATTERN_ID
ORDER BY pr.id;
"

# 3. ログ取り込み後の確認（ログを取り込んだ後）
sqlite3 db/monitor.db "
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
WHERE le.pattern_id = $PATTERN_ID
ORDER BY le.ts DESC
LIMIT 10;
"
```

#### ステップ6: ログを取り込んで動作確認

```bash
# ログを取り込む（手動パターンが優先的にマッチする）
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v

# 異常判定の結果を確認
sqlite3 db/monitor.db "
SELECT 
    le.id,
    le.ts,
    le.host,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    lp.param_value_num as available_bandwidth
FROM log_entries le
LEFT JOIN log_params lp ON le.id = lp.log_id AND lp.param_name = 'available_bandwidth'
WHERE le.pattern_id = $PATTERN_ID
  AND le.classification = 'abnormal'
ORDER BY le.ts DESC
LIMIT 10;
"
```

**期待される動作**:
- `available_bandwidth <= 50.0 Gb/s` の場合 → `classification = 'abnormal'`, `severity = 'warning'`
- `available_bandwidth <= 30.0 Gb/s` の場合 → `classification = 'abnormal'`, `severity = 'critical'`

#### 完全な実行例（コピー&ペースト用）

```bash
# === PCIe帯域幅ログの閾値設定（完全版） ===

# 1. 手動パターンを追加
python3 src/cli_tools.py add-pattern \
    "\[\s+\d+\.\d+\]\s+pci\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<available_bandwidth>\d+\.?\d*)\s+Gb/s\s+available\s+PCIe\s+bandwidth,\s+limited\s+by\s+(?P<limited_by_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\s+at\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]\s+\(capable\s+of\s+(?P<capable_bandwidth>\d+\.?\d*)\s+Gb/s\s+with\s+(?P<capable_speed>\d+\.?\d*)\s+GT/s\s+PCIe\s+x\d+\s+link\)" \
    "[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)" \
    --label normal \
    --severity info \
    --component kernel \
    --note "PCIe帯域幅ログ（available_bandwidth, limited_by_speed, capable_bandwidth, capable_speedを抽出可能）" \
    --db db/monitor.db

# 2. パターンIDを取得
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE manual_regex_rule LIKE '%available_bandwidth%' ORDER BY id DESC LIMIT 1;")
echo "パターンID: $PATTERN_ID"

# 3. 閾値ルール1を追加（available_bandwidth <= 50.0 Gb/s → warning）
python3 scripts/add_threshold_rule.py \
    --pattern-id $PATTERN_ID \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 50.0 \
    --severity warning \
    --message "PCIe available bandwidth <= 50 Gb/s (性能低下の可能性)" \
    --db db/monitor.db

# 4. 閾値ルール2を追加（available_bandwidth <= 30.0 Gb/s → critical）
python3 scripts/add_threshold_rule.py \
    --pattern-id $PATTERN_ID \
    --rule-type threshold \
    --field-name available_bandwidth \
    --op '<=' \
    --threshold 30.0 \
    --severity critical \
    --message "PCIe available bandwidth <= 30 Gb/s (重大な性能低下)" \
    --db db/monitor.db

# 5. 設定状況を確認
python3 scripts/check_pcie_threshold_status.py --db db/monitor.db

# 6. ログを取り込む（オプション: 既に取り込まれている場合は不要）
# python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v

# 7. 異常判定の結果を確認
sqlite3 db/monitor.db "
SELECT 
    le.id,
    le.ts,
    le.host,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    lp.param_value_num as available_bandwidth
FROM log_entries le
LEFT JOIN log_params lp ON le.id = lp.log_id AND lp.param_name = 'available_bandwidth'
WHERE le.pattern_id = $PATTERN_ID
ORDER BY le.ts DESC
LIMIT 10;
"
```

### 方法4: PCIe帯域幅ログの例（一括設定スクリプト）

上記の手順を一括で実行するスクリプトも用意されています:

```bash
# 方法A: Pythonスクリプト（add_threshold_rule.py を使用）
python3 scripts/setup_pcie_threshold.py --db db/monitor.db

# 方法B: シェルスクリプト（add_threshold_rule.py を使用）
bash scripts/setup_pcie_threshold.sh db/monitor.db
```

これらのスクリプトは以下を自動実行します:
1. named capture groups を含む手動パターンを追加
2. `add_threshold_rule.py` を使用して閾値ルールを設定

このスクリプトは以下を実行します:
1. PCIe帯域幅ログのパターンを追加（named capture groupを含む）
   - `available_bandwidth`: 利用可能な帯域幅 (Gb/s)
   - `limited_by_speed`: 制限されている速度 (GT/s)
   - `capable_bandwidth`: 可能な最大帯域幅 (Gb/s)
   - `capable_speed`: 可能な最大速度 (GT/s)
2. 閾値ルールを設定:
   - `available_bandwidth <= 50.0 Gb/s` → `warning`
   - `available_bandwidth <= 30.0 Gb/s` → `critical`

**設定状況の確認**:
```bash
# 設定状況を確認
python3 scripts/check_pcie_threshold_status.py --db db/monitor.db
```

このスクリプトは以下を確認します:
- パターンが正しく登録されているか
- 閾値ルールが正しく設定されているか
- ログが取り込まれているか
- パラメータが抽出されているか
- 異常判定が実行されているか

**使用例**:
```bash
# 1. 閾値設定
python3 scripts/setup_pcie_bandwidth_threshold.py

# 2. ログを取り込む
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714

# 3. 設定状況を確認
python3 scripts/check_pcie_threshold_status.py
```

---

## ステップ5: 正常系のテンプレであった場合、閾値のデータを参照し、異常かどうか判断する

正常系のパターンに対して、閾値チェックが実行されているか確認します。

```bash
# 異常判定が実行されたログを確認
sqlite3 db/monitor.db "
SELECT 
    le.id,
    le.ts,
    le.host,
    le.component,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    rp.id as pattern_id,
    rp.sample_message
FROM log_entries le
JOIN regex_patterns rp ON le.pattern_id = rp.id
WHERE le.classification = 'abnormal'
  AND rp.label = 'normal'
ORDER BY le.ts DESC
LIMIT 20;
"

# パラメータ抽出結果を確認
sqlite3 db/monitor.db "
SELECT 
    lp.log_id,
    lp.param_name,
    lp.param_value_num,
    lp.param_value_text
FROM log_params lp
JOIN log_entries le ON lp.log_id = le.id
WHERE le.pattern_id = <pattern_id>
ORDER BY lp.log_id DESC
LIMIT 20;
"
```

**処理内容**:
- 既知ログ（`is_known=1`）で、パターンのラベルが `normal` の場合
- `AnomalyDetector.check_anomaly()` が自動実行される
- `pattern_rules` テーブルのルールを評価
- 閾値を超えた場合、`classification = 'abnormal'` に更新

**PCIe帯域幅ログの例**:
```bash
# 1. 閾値設定（既に実行済みの場合）
python3 scripts/setup_pcie_bandwidth_threshold.py

# 2. ログを取り込む（PCIe帯域幅ログを含むファイル）
python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714

# 3. 異常判定の確認
python3 scripts/check_pcie_threshold_status.py

# 4. 異常ログの詳細確認
sqlite3 db/monitor.db "
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
JOIN log_params lp ON le.id = lp.log_id
WHERE le.pattern_id = 1819
  AND le.classification = 'abnormal'
ORDER BY le.ts DESC;
"
```

**期待される動作**:
- `available_bandwidth <= 50.0 Gb/s` の場合 → `classification = 'abnormal'`, `severity = 'warning'`
- `available_bandwidth <= 30.0 Gb/s` の場合 → `classification = 'abnormal'`, `severity = 'critical'`

---

## ステップ6: テンプレに合わないログ（未知）であった場合、まずpython3 src/cli_tools.py add-patternを実行するなどして手動対応できるものは手動でテンプレを作ってアップデートする

未知ログを手動でパターン化します。

### 6-1: 未知パターンの確認

```bash
# 未知パターンの一覧を表示
python3 src/cli_tools.py show-unknown --db db/monitor.db --limit 20

# 特定の未知ログの詳細を確認
sqlite3 db/monitor.db "
SELECT 
    id,
    ts,
    host,
    component,
    message,
    raw_line
FROM log_entries
WHERE is_known = 0
ORDER BY ts DESC
LIMIT 20;
"
```

### 6-2: 手動パターンの追加

#### 方法A: 正規表現パターンを直接指定

```bash
python3 src/cli_tools.py add-pattern \
    "<正規表現パターン>" \
    "<サンプルメッセージ>" \
    --label normal \
    --severity info \
    --component kernel \
    --note "説明"
```

**例**:
```bash
python3 src/cli_tools.py add-pattern \
    "\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C" \
    "[    0.005840] GPU temp: 75°C" \
    --label normal \
    --severity info \
    --component kernel \
    --note "GPU温度ログ（パラメータ抽出可能）"
```

#### 方法B: 未知ログから自動生成

```bash
# 未知ログのIDを指定してパターンを生成
python3 src/cli_tools.py add-pattern-from-log <log_id> \
    --label normal \
    --severity info \
    --note "未知ログから生成"
```

**例**:
```bash
# まず未知ログのIDを確認
sqlite3 db/monitor.db "SELECT id, message FROM log_entries WHERE is_known = 0 LIMIT 1;"

# ログID 123 からパターンを生成
python3 src/cli_tools.py add-pattern-from-log 123 \
    --label normal \
    --severity info \
    --note "自動生成パターン"
```

### 6-3: 既存の未知ログを既知パターンに紐付け

```bash
# 未知ログを既知パターンに紐付け
python3 src/cli_tools.py map-log <log_id> <pattern_id> --db db/monitor.db
```

**例**:
```bash
# ログID 123 をパターンID 45 に紐付け
python3 src/cli_tools.py map-log 123 45 --db db/monitor.db
```

### 6-4: パターン追加後の確認

```bash
# パターンが正しく追加されたか確認
sqlite3 db/monitor.db "
SELECT 
    id,
    regex_rule,
    manual_regex_rule,
    sample_message,
    label,
    severity
FROM regex_patterns
WHERE manual_regex_rule IS NOT NULL
ORDER BY id DESC
LIMIT 10;
"

# 未知ログが減ったか確認
python3 src/cli_tools.py stats --db db/monitor.db
```

---

## ステップ7: 手動でテンプレ化できないような突発的なログについて、LLMにコピーペーストしてログを解析してもらう

手動でパターン化できない未知ログをLLMに解析してもらいます。

### 7-1: 解析対象のログを抽出

```bash
# 未知ログを抽出（CSV形式で出力）
sqlite3 -header -csv db/monitor.db "
SELECT 
    id,
    ts,
    host,
    component,
    message,
    raw_line
FROM log_entries
WHERE is_known = 0
ORDER BY ts DESC
LIMIT 10;
" > unknown_logs.csv

# または、特定のログを表示
sqlite3 db/monitor.db "
SELECT 
    id,
    ts,
    host,
    component,
    message,
    raw_line
FROM log_entries
WHERE id = <log_id>;
"
```

### 7-2: LLMに解析を依頼

抽出したログをLLMにコピーペーストして、以下を依頼:
- ログの意味の説明
- 正常系か異常系かの判断
- 正規表現パターンの提案（必要に応じて）

### 7-3: LLMの解析結果を反映

LLMから得られた情報を基に、手動でパターンを追加:

```bash
# LLMが提案した正規表現パターンを使用
python3 src/cli_tools.py add-pattern \
    "<LLMが提案した正規表現>" \
    "<ログメッセージ>" \
    --label <normal|abnormal> \
    --severity <info|warning|critical> \
    --note "<LLMの解析結果>"
```

---

## 全体フローの確認コマンド

各ステップの実行後、以下のコマンドで全体の状態を確認できます:

```bash
# 統計情報の確認
python3 src/cli_tools.py stats --db db/monitor.db

# 既知/未知の分布
sqlite3 db/monitor.db "
SELECT 
    CASE WHEN is_known = 1 THEN '既知' ELSE '未知' END as status,
    COUNT(*) as count
FROM log_entries
GROUP BY is_known;
"

# 分類別の分布
sqlite3 db/monitor.db "
SELECT 
    classification,
    COUNT(*) as count
FROM log_entries
GROUP BY classification
ORDER BY count DESC;
"

# パターンラベルの分布
sqlite3 db/monitor.db "
SELECT 
    label,
    COUNT(*) as count
FROM regex_patterns
GROUP BY label
ORDER BY count DESC;
"

# 異常判定ルールの一覧
sqlite3 db/monitor.db "
SELECT 
    pr.id,
    pr.pattern_id,
    rp.sample_message,
    pr.rule_type,
    pr.field_name,
    pr.op,
    pr.threshold_value1,
    pr.severity_if_match,
    pr.message
FROM pattern_rules pr
JOIN regex_patterns rp ON pr.pattern_id = rp.id
WHERE pr.is_active = 1
ORDER BY pr.id DESC;
"
```

---

## トラブルシューティング

### パターンがマッチしない

- 手動パターンは `manual_regex_rule` に保存される
- `ingest.py` の `_check_manual_patterns()` でマッチングされる
- 正規表現のエスケープを確認（`\s`, `\d`, `\.` など）

### 閾値チェックが動作しない

- パターンに named capture group `(?P<name>...)` が含まれているか確認
- `log_params` テーブルにパラメータが抽出されているか確認
- `pattern_rules` テーブルにルールが正しく登録されているか確認
- `is_active = 1` になっているか確認

### 未知ログが減らない

- 手動パターンを追加した後、再度ログを取り込む必要がある
- または `map-log` コマンドで既存の未知ログを既知パターンに紐付ける
