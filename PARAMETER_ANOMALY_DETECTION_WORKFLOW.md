# パラメータ異常検知ワークフロー実践ガイド

> このファイルで行うこと: 正常ログに対するパラメータベースの異常検知の実装と実践手順を説明します。

## ワークフロー概要

1. **手動でパラメータ化を実装**: 特定のログに対してnamed capture groupを含むパターンを追加し、理想値を`pattern_rules`に定義
2. **パラメータ化の判断**: ログ取り込み時に、パターンにnamed capture groupが含まれているか判断
3. **パラメータ抽出**: named capture groupが含まれている場合、パラメータを抽出して`log_params`に保存
4. **異常判定**: `pattern_rules`と`log_params`を突合して異常を検知

---

## ステップ1: 手動でパラメータ化を実装

### 1-1: パターンにnamed capture groupを含めて追加

**例**: GPU温度ログ `[    0.005840] GPU temp: 85°C` をパラメータ化

```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C" \
  "[    0.005840] GPU temp: 85°C" \
  --label normal \
  --severity info \
  --component kernel \
  --note "GPU温度ログ（パラメータ: temp）"
```

**ポイント**:
- `(?P<temp>\d+)` がnamed capture groupで、`temp`パラメータを抽出
- `--label normal` で正常ログとして登録

### 1-2: 理想値（閾値ルール）を`pattern_rules`に追加

**例**: GPU温度が80°Cを超えた場合に異常とする

```bash
# まずパターンIDを確認
sqlite3 db/monitor.db "SELECT id, sample_message FROM regex_patterns WHERE sample_message LIKE '%GPU temp%';"

# パターンIDが100の場合
python3 scripts/add_threshold_rule.py \
  --pattern-id 100 \
  --rule-type threshold \
  --field-name temp \
  --op '>' \
  --threshold 80.0 \
  --severity critical \
  --message "GPU temp > 80°C"
```

**ポイント**:
- `--field-name temp`: `log_params`の`param_name`と一致させる
- `--op '>'`: 演算子（`>`, `<`, `>=`, `<=`, `==`, `!=`）
- `--threshold 80.0`: 閾値

---

## ステップ2: パラメータ化が実装されているか判断

### 実装状況

**`src/ingest.py`** の142-155行目で実装済み：

```python
# パラメータ抽出（既知ログの場合）
if pattern_id and is_known:
    # 使用する正規表現パターンを決定（regex_rule または manual_regex_rule）
    cursor.execute("""
        SELECT regex_rule, manual_regex_rule
        FROM regex_patterns
        WHERE id = ?
    """, (pattern_id,))
    pattern_row = cursor.fetchone()
    if pattern_row:
        # manual_regex_rule があればそれを使用、なければ regex_rule を使用
        pattern_to_use = pattern_row['manual_regex_rule'] or pattern_row['regex_rule']
        if pattern_to_use:
            # パラメータ抽出を実行（named capture groupがあれば抽出される）
            self._extract_and_save_params(cursor, log_id, pattern_to_use, parsed['message'])
```

**動作**:
- 既知ログ（`is_known=1`）の場合のみパラメータ抽出を実行
- `_extract_and_save_params()`がnamed capture groupを検出してパラメータを抽出
- named capture groupがない場合は何も抽出されない（正常形として扱われる）

---

## ステップ3: パラメータ化が実装されていない場合は正常形とする

### 実装状況

**`src/param_extractor.py`** で実装済み：

```python
def extract_params(self, regex_rule: str, message: str) -> Dict[str, any]:
    # named capture groupを抽出
    pattern = re.compile(regex_rule)
    match = pattern.fullmatch(message)
    
    if match:
        groups = match.groupdict()  # named capture groupがあれば抽出
        # パラメータがあればlog_paramsに保存、なければ空辞書を返す
```

**動作**:
- named capture groupがない場合、`groups`は空辞書になる
- `log_params`に何も保存されない
- 異常判定は実行されない（正常形として扱われる）

---

## ステップ4: パラメータ抽出と異常判定

### 実装状況

**`src/ingest.py`** の157-173行目で実装済み：

```python
# 異常判定を実行（既知ログの場合）
anomaly_info = self.anomaly_detector.check_anomaly(log_id, pattern_id)
if anomaly_info:
    # 異常が検知された場合、classificationを更新
    cursor.execute("""
        UPDATE log_entries
        SET classification = ?,
            severity = ?,
            anomaly_reason = ?
        WHERE id = ?
    """, (
        anomaly_info['classification'],  # 'abnormal'
        anomaly_info['severity'],
        anomaly_info['anomaly_reason'],
        log_id
    ))
```

**`src/anomaly_detector.py`** で実装済み：

```python
def check_anomaly(self, log_id: int, pattern_id: int):
    # 1. pattern_rulesからルールを取得
    # 2. log_paramsからパラメータ値を取得
    # 3. ルールとパラメータ値を比較
    # 4. 条件にマッチした場合、異常と判定
```

---

## 実践手順

### 準備: テスト用ログファイルの作成

```bash
# テスト用ログファイルを作成
cat > /tmp/test_gpu_temp.log << 'EOF'
Jul 14 11:20:17 172.20.224.102 kernel: [    0.005840] GPU temp: 75°C
Jul 14 11:20:18 172.20.224.102 kernel: [    0.005841] GPU temp: 85°C
Jul 14 11:20:19 172.20.224.102 kernel: [    0.005842] GPU temp: 90°C
EOF
```

### ステップ1: パターンとルールの追加

```bash
# 1. パターンを追加（named capture group含む）
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C" \
  "[    0.005840] GPU temp: 75°C" \
  --label normal \
  --severity info \
  --component kernel \
  --note "GPU温度ログ（パラメータ: temp）"

# 2. パターンIDを確認
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%GPU temp%' ORDER BY id DESC LIMIT 1;")
echo "Pattern ID: $PATTERN_ID"

# 3. 閾値ルールを追加（80°Cを超えた場合に異常）
python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name temp \
  --op '>' \
  --threshold 80.0 \
  --severity critical \
  --message "GPU temp > 80°C"
```

### ステップ2: ログを取り込む

```bash
# ログファイルを取り込む
python3 src/ingest.py /tmp/test_gpu_temp.log --db db/monitor.db -v
```

### ステップ3: 結果を確認

```bash
# 1. パラメータが正しく抽出されているか確認
sqlite3 db/monitor.db "
SELECT 
    le.id as log_id,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    lp.param_name,
    lp.param_value_num
FROM log_entries le
LEFT JOIN log_params lp ON le.id = lp.log_id
WHERE le.message LIKE '%GPU temp%'
ORDER BY le.id;
"

# 2. 異常判定の結果を確認
sqlite3 db/monitor.db "
SELECT 
    id,
    message,
    classification,
    severity,
    anomaly_reason
FROM log_entries
WHERE message LIKE '%GPU temp%'
ORDER BY id;
"
```

**期待される結果**:
- `temp=75`: `classification='normal'`（閾値以下）
- `temp=85`: `classification='abnormal'`, `severity='critical'`, `anomaly_reason='GPU temp > 80°C'`
- `temp=90`: `classification='abnormal'`, `severity='critical'`, `anomaly_reason='GPU temp > 80°C'`

---

## 実装の詳細

### パラメータ抽出の流れ

```
ログ取り込み
    ↓
パターンマッチング（既知ログ）
    ↓
pattern_to_use を取得（manual_regex_rule または regex_rule）
    ↓
_extract_and_save_params() を実行
    ├─ named capture group がある → パラメータ抽出 → log_params に保存
    └─ named capture group がない → 何も抽出されない（正常形）
    ↓
AnomalyDetector.check_anomaly() を実行
    ├─ pattern_rules からルールを取得
    ├─ log_params からパラメータ値を取得
    └─ ルールを評価
        ├─ 条件にマッチ → classification='abnormal'
        └─ 条件にマッチしない → classification='normal'（変更なし）
```

### パラメータ化の判断ロジック

**実装箇所**: `src/ingest.py` の `_extract_and_save_params()` メソッド

```python
def _extract_and_save_params(self, cursor, log_id: int, regex_rule: str, message: str):
    extractor = ParamExtractor()
    params = extractor.extract_params(regex_rule, message)
    
    # named capture groupがあればパラメータが抽出される
    # なければ空辞書が返される
    for param_name, param_data in params.items():
        # log_paramsに保存
        cursor.execute("""
            INSERT INTO log_params
            (log_id, param_name, param_value_num, param_value_text)
            VALUES (?, ?, ?, ?)
        """, (log_id, param_name, param_data['num'], param_data['text']))
```

**判断基準**:
- `params`が空辞書 → パラメータ化されていない（正常形）
- `params`に要素がある → パラメータ化されている（異常判定を実行）

---

## 使用例: PCIe帯域幅の監視

### 1. パターン追加

```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+pci\s+\S+:\s+(?P<available_bandwidth>\d+\.\d+)\s+Gb/s\s+available\s+PCIe\s+bandwidth" \
  "[ 19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth" \
  --label normal \
  --severity info \
  --component kernel \
  --note "PCIe帯域幅ログ（パラメータ: available_bandwidth）"
```

### 2. 閾値ルール追加

```bash
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%PCIe bandwidth%' ORDER BY id DESC LIMIT 1;")

python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name available_bandwidth \
  --op '<' \
  --threshold 50.0 \
  --severity warning \
  --message "PCIe bandwidth < 50 Gb/s"
```

### 3. ログ取り込みと確認

```bash
# ログを取り込む
python3 src/ingest.py <log_file> --db db/monitor.db

# 結果を確認
sqlite3 db/monitor.db "
SELECT 
    le.id,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    lp.param_name,
    lp.param_value_num
FROM log_entries le
LEFT JOIN log_params lp ON le.id = lp.log_id
WHERE le.message LIKE '%PCIe bandwidth%'
ORDER BY le.id;
"
```

---

## まとめ

### 実装済みの機能

✅ **パラメータ抽出**: named capture groupから自動抽出  
✅ **パラメータ保存**: `log_params`テーブルに自動保存  
✅ **異常判定**: `pattern_rules`と`log_params`を突合して自動判定  
✅ **パラメータ化の判断**: named capture groupの有無で自動判断  

### 手動で行うこと

1. **パターン追加**: named capture groupを含むパターンを手動で追加
2. **ルール定義**: `pattern_rules`に閾値ルールを手動で追加

### 自動で行われること

1. **パラメータ抽出**: ログ取り込み時に自動実行
2. **異常判定**: ログ取り込み時に自動実行
3. **classification更新**: 異常検知時に自動更新

