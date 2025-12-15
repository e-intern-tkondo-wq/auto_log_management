# パターン変数化ワークフローガイド

> このファイルで行うこと: 既存の正規表現パターンに対して変数（named capture group）を導入する一般的な手順を説明します。

## 概要

正規表現パターンに**named capture group** `(?P<param_name>...)` を追加することで、ログからパラメータを抽出し、異常判定に活用できるようになります。

---

## 変数化の流れ（5ステップ）

### ステップ1: 変数化したいログメッセージを確認

まず、変数化したいログメッセージの実例を確認します。

```bash
# データベースから対象ログを確認
sqlite3 db/monitor.db "
SELECT id, message, classification, pattern_id
FROM log_entries
WHERE message LIKE '%対象キーワード%'
LIMIT 5;
"
```

または、実際のログファイルから確認します。

```bash
# ログファイルから該当メッセージを検索
grep -n "対象キーワード" log_flower/bootlog/*.log | head -5
```

**重要なポイント:**
- 変数化したい数値や文字列の部分を特定する
- 複数のサンプルを見て、パターンの変動部分を把握する

---

### ステップ2: 正規表現パターンにnamed capture groupを追加

既存の正規表現パターン（または新しいパターン）に対して、変数化したい部分を `(?P<param_name>...)` 形式のnamed capture groupに置き換えます。

#### 例1: 数値パラメータ（PCIe帯域幅）

**元のログメッセージ:**
```
[   19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth
```

**変数化前のパターン（抽象化されたもの）:**
```regex
\[\s+\d+\.\d+\]\s+pci\s+\S+:\s+\d+\.\d+\s+Gb/s\s+available\s+PCIe\s+bandwidth
```

**変数化後のパターン（named capture group追加）:**
```regex
\[\s+\d+\.\d+\]\s+pci\s+\S+:\s+(?P<available_bandwidth>\d+\.\d+)\s+Gb/s\s+available\s+PCIe\s+bandwidth
```

#### 例2: 整数パラメータ（GPU温度）

**元のログメッセージ:**
```
[    0.005840] GPU temp: 85°C
```

**変数化後のパターン:**
```regex
\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C
```

#### 例3: 複数パラメータ

**元のログメッセージ:**
```
[   10.123456] Memory usage: 8192 MB / 16384 MB (50%)
```

**変数化後のパターン:**
```regex
\[\s+\d+\.\d+\]\s+Memory\s+usage:\s+(?P<used_mb>\d+)\s+MB\s+/\s+(?P<total_mb>\d+)\s+MB\s+\((?P<percentage>\d+)%\)
```

**ポイント:**
- パラメータ名は分かりやすい名前を付ける（例: `temp`, `bandwidth`, `cpu_usage`）
- 数値パラメータの場合は、正規表現で数値パターンを指定（`\d+` または `\d+\.\d+`）
- 文字列パラメータの場合は、`(.+?)` や `\S+` など適切なパターンを使用

---

### ステップ3: `add-pattern`コマンドでパターンを追加

変数化した正規表現パターンを `add-pattern` コマンドで追加します。

```bash
python3 src/cli_tools.py add-pattern \
  "正規表現パターン（named capture group含む）" \
  "サンプルメッセージ" \
  --label normal \
  --severity info \
  --component コンポーネント名 \
  --note "パターンの説明（パラメータ: param_name）" \
  --db db/monitor.db
```

**具体例（PCIe帯域幅）:**
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
- `Has parameters: Yes` と表示されれば、named capture groupが正しく検出されている

**注意:** `add-pattern`コマンド実行時に、正規表現パターンにnamed capture groupが含まれているかどうかを自動で検出し、`has_params`フラグを設定します。コマンドの出力に「Has parameters: Yes (param_name1, param_name2, ...)」と表示されます。

---

### ステップ4: パターンIDを確認

追加したパターンのIDを確認します。また、パラメータ化されているかどうかは`has_params`カラムで確認できます。

```bash
# パターンIDとパラメータ化フラグを取得
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%キーワード%' ORDER BY id DESC LIMIT 1;")
echo "Pattern ID: $PATTERN_ID"

# パターンの詳細情報を確認（has_paramsフラグも含む）
sqlite3 db/monitor.db "
SELECT 
    id, 
    sample_message, 
    note,
    has_params,
    CASE WHEN has_params = 1 THEN 'Yes' ELSE 'No' END as has_parameters
FROM regex_patterns
WHERE sample_message LIKE '%キーワード%'
ORDER BY id DESC
LIMIT 1;
"
```

**パターンの確認場所:**

1. **`regex_patterns`テーブル**: すべてのパターンが保存されています
   - `id`: パターンID
   - `manual_regex_rule`: 手動で追加した正規表現パターン
   - `regex_rule`: 自動生成された正規表現パターン
   - `has_params`: パラメータ化されているか（1=はい、0=いいえ）
   - `sample_message`: サンプルメッセージ
   - `label`: ラベル（normal, abnormal, unknown, ignore）
   - `severity`: 重要度
   - `note`: ノート

2. **`log_entries`テーブル**: ログエントリは`pattern_id`でパターンに紐付けられています
   ```sql
   SELECT 
       le.id,
       le.message,
       le.pattern_id,
       rp.has_params,
       rp.sample_message
   FROM log_entries le
   LEFT JOIN regex_patterns rp ON le.pattern_id = rp.id
   WHERE le.message LIKE '%キーワード%'
   LIMIT 10;
   ```

**`has_params`フラグの意味:**
- `has_params = 1`: パターンにnamed capture group `(?P<name>...)` が含まれている（パラメータ化済み）
- `has_params = 0`: パターンにnamed capture groupが含まれていない（パラメータ化されていない）

このフラグは`add-pattern`コマンド実行時に自動で設定されます。

---

### ステップ5（オプション）: 閾値ルールを追加

異常判定を行う場合は、`pattern_rules`テーブルに閾値ルールを追加します。

```bash
python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name パラメータ名 \
  --op 演算子 \
  --threshold 閾値 \
  --severity 重要度 \
  --message "異常理由メッセージ" \
  --db db/monitor.db
```

**具体例（PCIe帯域幅が50 Gb/s未満の場合に警告）:**
```bash
python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name available_bandwidth \
  --op '<' \
  --threshold 50.0 \
  --severity warning \
  --message "PCIe bandwidth < 50 Gb/s"
```

**演算子の選択肢:**
- `>`: より大きい
- `<`: より小さい
- `>=`: 以上
- `<=`: 以下
- `==`: 等しい
- `!=`: 等しくない
- `between`: 範囲内（`--threshold2` も必要）
- `not_between`: 範囲外（`--threshold2` も必要）

**重要度の選択肢:**
- `info`: 情報
- `warning`: 警告
- `critical`: 重大

---

### ステップ6（オプション）: 既存ログを再処理

既存のログエントリに対して新しいパターンを適用し、パラメータを抽出・異常判定を行う場合は、`reprocess-pattern`コマンドを使用します。

```bash
python3 src/cli_tools.py reprocess-pattern \
  $PATTERN_ID \
  --db db/monitor.db \
  -v
```

**動作:**
- すべてのログエントリに対して新しいパターンでマッチング
- マッチしたログからパラメータを抽出して `log_params` に保存
- `pattern_rules` のルールに基づいて異常判定を実行

---

## 実践例: 完全なワークフロー

### 例: CPU使用率ログの変数化

#### 1. ログメッセージの確認
```bash
grep "CPU usage" log_flower/bootlog/*.log | head -3
# 出力例:
# [   12.345678] CPU usage: 75.5%
```

#### 2. パターンにnamed capture groupを追加
```regex
\[\s+\d+\.\d+\]\s+CPU\s+usage:\s+(?P<cpu_usage>\d+\.\d+)%
```

#### 3. パターンを追加
```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+CPU\s+usage:\s+(?P<cpu_usage>\d+\.\d+)%" \
  "[   12.345678] CPU usage: 75.5%" \
  --label normal \
  --severity info \
  --component kernel \
  --note "CPU使用率ログ（パラメータ: cpu_usage）" \
  --db db/monitor.db
```

#### 4. パターンIDを確認
```bash
PATTERN_ID=$(sqlite3 db/monitor.db "SELECT id FROM regex_patterns WHERE sample_message LIKE '%CPU usage%' ORDER BY id DESC LIMIT 1;")
echo "Pattern ID: $PATTERN_ID"
```

#### 5. 閾値ルールを追加（CPU使用率が90%を超えた場合に警告）
```bash
python3 scripts/add_threshold_rule.py \
  --pattern-id $PATTERN_ID \
  --rule-type threshold \
  --field-name cpu_usage \
  --op '>' \
  --threshold 90.0 \
  --severity warning \
  --message "CPU usage > 90%"
```

#### 6. 既存ログを再処理
```bash
python3 src/cli_tools.py reprocess-pattern $PATTERN_ID --db db/monitor.db -v
```

#### 7. 結果を確認
```bash
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
WHERE le.message LIKE '%CPU usage%'
ORDER BY le.id;
"
```

---

## よくある質問（FAQ）

### Q1: 既存のパターンにnamed capture groupを追加したい場合は？

**A:** 既存のパターンを更新する場合は、`add-pattern`コマンドに `--update` フラグを追加します。ただし、`manual_regex_rule`にしか保存されないため、既存の自動生成パターン（`regex_rule`）を更新することはできません。

新しいパターンとして追加し、既存ログを `reprocess-pattern` で再処理することをおすすめします。

### Q2: 複数のパラメータを抽出する場合の注意点は？

**A:** 各named capture groupに異なる名前を付けてください。同じパラメータ名が複数ある場合、後からマッチした値で上書きされます。

```regex
# 良い例: 異なる名前
(?P<used>\d+)\s+/\s+(?P<total>\d+)

# 悪い例: 同じ名前（上書きされる）
(?P<value>\d+)\s+/\s+(?P<value>\d+)
```

### Q3: 文字列パラメータを抽出したい場合は？

**A:** `(.+?)` や `\S+` などのパターンを使用します。ただし、異常判定は主に数値パラメータを対象としているため、文字列パラメータの場合は `pattern_rules` で `contains` や `regex` タイプのルールを使用します。

```regex
# 文字列パラメータの例
Device\s+name:\s+(?P<device_name>\S+)
```

### Q4: パラメータ化されているパターン一覧を確認するには？

**A:** `has_params = 1`のパターンを確認します。

```bash
sqlite3 db/monitor.db "
SELECT 
    id,
    CASE WHEN manual_regex_rule IS NOT NULL THEN manual_regex_rule ELSE regex_rule END as pattern,
    sample_message,
    note,
    has_params
FROM regex_patterns
WHERE has_params = 1
ORDER BY id DESC;
"
```

### Q5: パラメータ抽出が正しく動作しているか確認するには？

**A:** 以下のSQLクエリで確認できます。

```bash
sqlite3 db/monitor.db "
SELECT 
    le.id,
    le.message,
    lp.param_name,
    lp.param_value_num,
    lp.param_value_text
FROM log_entries le
JOIN log_params lp ON le.id = lp.log_id
WHERE le.pattern_id = $PATTERN_ID
LIMIT 10;
"
```

### Q6: パターンにマッチしないログがある場合は？

**A:** 正規表現パターンを確認してください。エスケープが必要な文字（`[`, `]`, `.`, `+`, `*` など）が正しくエスケープされているか確認します。

また、`reprocess-pattern` コマンドの `-v` フラグを使用すると、どのログがマッチしたかを詳細に確認できます。

---

## まとめ

変数化の一般的な流れ:

1. ✅ **ログメッセージの確認**: 変数化したい部分を特定
2. ✅ **正規表現の作成**: named capture group `(?P<param_name>...)` を追加
3. ✅ **パターンの追加**: `add-pattern` コマンドで追加
4. ✅ **パターンIDの確認**: 後続のステップで使用
5. ✅ **閾値ルールの追加（オプション）**: 異常判定ルールを定義
6. ✅ **既存ログの再処理（オプション）**: `reprocess-pattern` で再処理

このワークフローに従うことで、どの正規表現パターンに対しても変数化を実装できます。
