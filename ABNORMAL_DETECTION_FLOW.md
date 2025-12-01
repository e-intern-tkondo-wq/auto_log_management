# 異常判定のフローとデータベース反映
> このファイルで行うこと: 異常判定処理の分岐とDB反映内容を整理します。

## ラベルの定義

- **`normal`**: 普通のログ（デフォルト）
- **`unknown`**: 見たことがないログ
- **`abnormal`**: 見たことがあるが危険なログ
- **`ignore`**: 無視するログ（ノイズなど）

## 異常判定の2つのパターン

### パターン1: 正規表現そのものがエラーを表す場合

**テーブル**: `regex_patterns`  
**カラム**: `label = 'abnormal'`

#### 処理フロー

```
ログメッセージ
    ↓
パターンマッチング
    ↓
regex_patterns テーブルから label を取得
    ↓
label = 'abnormal' の場合
    ↓
log_entries.classification = 'abnormal'
log_entries.severity = regex_patterns.severity
```

#### コード実装（`src/ingest.py`）

```python
# パターンのラベルに基づいてclassificationを決定
if pattern_id:
    cursor.execute("""
        SELECT label, severity
        FROM regex_patterns
        WHERE id = ?
    """, (pattern_id,))
    pattern_row = cursor.fetchone()
    if pattern_row:
        classification = pattern_row['label']  # 'abnormal' の場合
        severity = pattern_row['severity']
```

#### データベース反映

- **`regex_patterns.label`**: `'abnormal'` に設定されている
- **`log_entries.classification`**: `'abnormal'` に設定される
- **`log_entries.severity`**: `regex_patterns.severity` の値が設定される
- **`log_entries.anomaly_reason`**: `NULL`（パターン自体が異常なので理由は不要）

#### 使用例

```sql
-- 異常パターンを定義
UPDATE regex_patterns
SET label = 'abnormal',
    severity = 'critical'
WHERE id = 100;

-- このパターンにマッチしたログは自動的に異常と判定される
-- log_entries.classification = 'abnormal'
-- log_entries.severity = 'critical'
```

---

### パターン2: 閾値チェックで異常と判断された場合

**テーブル**: `log_entries`（更新される）  
**参照テーブル**: `pattern_rules`, `log_params`

#### 処理フロー

```
既知ログ（is_known = 1）
    ↓
パラメータ抽出 → log_params に保存
    ↓
AnomalyDetector.check_anomaly()
    ├─ pattern_rules からルールを取得
    ├─ log_params からパラメータ値を取得
    └─ ルールを評価
    ↓
異常と判定された場合
    ↓
log_entries テーブルを UPDATE
    ├─ classification = 'abnormal'
    ├─ severity = pattern_rules.severity_if_match
    └─ anomaly_reason = pattern_rules.message
```

#### コード実装（`src/ingest.py`）

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
        anomaly_info['severity'],        # pattern_rules.severity_if_match
        anomaly_info['anomaly_reason'],  # pattern_rules.message
        log_id
    ))
```

#### データベース反映

- **`log_entries.classification`**: `'abnormal'` に更新される
- **`log_entries.severity`**: `pattern_rules.severity_if_match` の値が設定される
- **`log_entries.anomaly_reason`**: `pattern_rules.message` の値が設定される（例: "GPU temp > 80°C"）

#### 使用例

```sql
-- ルールを定義
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, message
)
VALUES (
    100, 'threshold', 'temp', '>',
    80.0, 'critical', 'GPU temp > 80°C'
);

-- 異常と判定された場合、log_entries が更新される
-- UPDATE log_entries
-- SET classification = 'abnormal',
--     severity = 'critical',
--     anomaly_reason = 'GPU temp > 80°C'
-- WHERE id = 123;
```

---

## まとめ

### パターン1: 正規表現そのものがエラー

| 項目 | 値 |
|------|-----|
| **判定テーブル** | `regex_patterns` |
| **判定カラム** | `label = 'abnormal'` |
| **反映テーブル** | `log_entries` |
| **反映カラム** | `classification = 'abnormal'`, `severity = regex_patterns.severity` |
| **anomaly_reason** | `NULL`（パターン自体が異常） |

### パターン2: 閾値チェックで異常

| 項目 | 値 |
|------|-----|
| **判定テーブル** | `pattern_rules` + `log_params` |
| **判定ロジック** | `AnomalyDetector.check_anomaly()` |
| **反映テーブル** | `log_entries` |
| **反映カラム** | `classification = 'abnormal'`, `severity = pattern_rules.severity_if_match`, `anomaly_reason = pattern_rules.message` |

### 重要なポイント

1. **両方とも `log_entries` テーブルに反映される**
   - `classification = 'abnormal'`
   - `severity` が設定される
   - `anomaly_reason` はパターン2のみ設定される

2. **判定タイミング**
   - パターン1: ログインジェスト時（パターンマッチング時）
   - パターン2: ログインジェスト時（既知ログの場合のみ）

3. **判定の優先順位**
   - パターン1の判定が先に実行される
   - その後、パターン2の閾値チェックが実行される
   - パターン2で異常と判定された場合、パターン1の結果を上書きする

