# Label と Severity のカテゴリリファレンス

> このファイルで行うこと: `regex_patterns`テーブルの`label`と`severity`カラムで使用可能な値とその意味を説明します。

## `label`（ラベル）のカテゴリ

`label`はログパターンの分類を示します。以下の4つの値が使用可能です：

| 値 | 説明 | デフォルト | 使用例 |
|---|---|---|---|
| `normal` | 正常なログ（通常の動作を示すログ） | ✅ はい | 起動メッセージ、初期化完了メッセージなど |
| `abnormal` | 異常なログ（エラーや警告を示すログ） | ❌ | エラーメッセージ、異常検知ログなど |
| `unknown` | 未分類のログ（まだ分類されていない新しいパターン） | ❌ | 新しく出現したログパターン |
| `ignore` | 無視するログ（ノイズや不要なログ） | ❌ | デバッグログ、詳細ログなど |

### `label`の特徴

- **デフォルト値**: `normal`
- **必須**: はい（NOT NULL制約）
- **用途**: 
  - パターンにマッチしたログの`classification`フィールドがこの値に設定される
  - `normal`以外のラベルのパターンは、マッチしたログを自動的にその分類に設定する

### 使用例

```bash
# normal ラベルでパターンを追加
python3 src/cli_tools.py add-pattern \
  "パターン" \
  "サンプルメッセージ" \
  --label normal \
  --severity info

# abnormal ラベルでパターンを追加
python3 src/cli_tools.py add-pattern \
  "エラーパターン" \
  "エラーメッセージ" \
  --label abnormal \
  --severity critical

# ignore ラベルでパターンを追加（ノイズを無視）
python3 src/cli_tools.py add-pattern \
  "デバッグログパターン" \
  "デバッグメッセージ" \
  --label ignore \
  --severity info
```

---

## `severity`（重要度）のカテゴリ

`severity`はログパターンの重要度を示します。以下の4つの値が使用可能です：

| 値 | 説明 | 使用例 |
|---|---|---|
| `info` | 情報（一般的な情報メッセージ） | 起動完了、初期化完了など |
| `warning` | 警告（注意が必要だが緊急ではない） | 非推奨機能の使用、パフォーマンス低下など |
| `critical` | 重大（即座に対応が必要） | システムエラー、データ損失、セキュリティ侵害など |
| `unknown` | 不明（分類されていない場合） | 新しく出現したログで重要度が未確定の場合 |

### `severity`の特徴

- **デフォルト値**: `NULL`（未設定可）
- **必須**: いいえ（NULL許可）
- **用途**: 
  - パターンにマッチしたログの`severity`フィールドがこの値に設定される
  - `pattern_rules`の`severity_if_match`でも使用される（異常検知時の重要度）

### 注意事項

- `pattern_rules`テーブルの`severity_if_match`では、`info`、`warning`、`critical`のみが選択可能（`unknown`は使用不可）
- `regex_patterns`の`severity`では`unknown`も使用可能（未分類のログパターン用）

### 使用例

```bash
# info 重要度でパターンを追加
python3 src/cli_tools.py add-pattern \
  "パターン" \
  "サンプルメッセージ" \
  --label normal \
  --severity info

# warning 重要度でパターンを追加
python3 src/cli_tools.py add-pattern \
  "警告パターン" \
  "警告メッセージ" \
  --label abnormal \
  --severity warning

# critical 重要度でパターンを追加
python3 src/cli_tools.py add-pattern \
  "エラーパターン" \
  "エラーメッセージ" \
  --label abnormal \
  --severity critical
```

---

## `label`と`severity`の組み合わせ例

### 推奨される組み合わせ

| `label` | `severity` | 説明 | 使用例 |
|---|---|---|---|
| `normal` | `info` | 正常な情報ログ | 起動完了メッセージ |
| `normal` | `warning` | 正常だが注意が必要 | パフォーマンス低下の可能性 |
| `abnormal` | `warning` | 軽度の異常 | 非推奨機能の使用 |
| `abnormal` | `critical` | 重大な異常 | システムエラー、データ損失 |
| `unknown` | `unknown` | 未分類 | 新しく出現したログ |
| `ignore` | `info` | 無視するログ | デバッグログ、詳細ログ |

### 実際の使用例

```bash
# PCIe帯域幅ログ（正常ログ、情報レベル）
python3 src/cli_tools.py add-pattern \
  "パターン" \
  "サンプルメッセージ" \
  --label normal \
  --severity info \
  --note "PCIe帯域幅ログ"

# GPU温度エラー（異常ログ、重大レベル）
python3 src/cli_tools.py add-pattern \
  "パターン" \
  "サンプルメッセージ" \
  --label abnormal \
  --severity critical \
  --note "GPU温度エラー"

# デバッグログ（無視するログ、情報レベル）
python3 src/cli_tools.py add-pattern \
  "パターン" \
  "サンプルメッセージ" \
  --label ignore \
  --severity info \
  --note "デバッグログ（無視）"
```

---

## バリデーション

### `label`のバリデーション

`src/cli_tools.py`で以下のようにバリデーションが実装されています：

```python
if label not in ('normal', 'abnormal', 'unknown', 'ignore'):
    print(f"Error: Invalid label '{label}'. Must be one of: normal, abnormal, unknown, ignore")
    sys.exit(1)
```

### `severity`のバリデーション

`severity`はNULL許可のため、厳密なバリデーションは行われていませんが、以下の値を使用することが推奨されます：

- `info`
- `warning`
- `critical`
- `unknown`（`regex_patterns`のみ）

`pattern_rules.severity_if_match`では、`info`、`warning`、`critical`のみが選択可能です。

---

## データベースでの確認

### `label`の分布を確認

```sql
SELECT label, COUNT(*) as count
FROM regex_patterns
GROUP BY label
ORDER BY count DESC;
```

### `severity`の分布を確認

```sql
SELECT severity, COUNT(*) as count
FROM regex_patterns
WHERE severity IS NOT NULL
GROUP BY severity
ORDER BY count DESC;
```

### `label`と`severity`の組み合わせを確認

```sql
SELECT 
    label,
    severity,
    COUNT(*) as count
FROM regex_patterns
GROUP BY label, severity
ORDER BY label, severity;
```

---

## まとめ

| 項目 | カテゴリ | 値 | 必須 | デフォルト |
|---|---|---|---|---|
| `label` | 4つ | `normal`, `abnormal`, `unknown`, `ignore` | ✅ はい | `normal` |
| `severity` | 4つ | `info`, `warning`, `critical`, `unknown` | ❌ いいえ | `NULL` |

**重要なポイント**:
- `label`はログパターンの**分類**を表す
- `severity`はログパターンの**重要度**を表す
- `label = 'normal'`でも`severity = 'critical'`の組み合わせは可能（例：重要な正常ログ）
- `label = 'abnormal'`のパターンは、マッチしたログを自動的に`abnormal`に分類する
