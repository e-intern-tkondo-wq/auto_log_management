# データベース状態レポート
> このファイルで行うこと: `db/monitor.db` の最新統計・スキーマ・今後のTODOをまとめます。

## データベースファイル

- **`db/monitor.db`**: メインデータベース（SQLite）

## テーブル一覧

1. **`regex_patterns`** - パターンマスタ
2. **`log_entries`** - ログ本体
3. **`log_params`** - パラメータ抽出結果
4. **`pattern_rules`** - 異常判定ルール
5. **`alerts`** - 通知履歴
6. **`ai_analyses`** - （未実装: 現在テーブルなし／将来拡張用）

## データ統計

### ログエントリ（log_entries）

- **総ログ数**: 34,911件
- **既知ログ**: 33,041件 (94.6%)
- **未知ログ**: 1,870件 (5.4%)
- **分類内訳**:
  - `unknown`: 34,895件
  - `abnormal`: 8件
  - `normal`: 8件
- **ユニークホスト数**: 8件
  - 172.20.224.101 / 102 / 103 / 104 / 105 / 108 / 109 / 110

### パターン（regex_patterns）

- **総パターン数**: 1,871個
- **未知パターン**: 1,868個 (99.8%)
- **正常パターン**: 2個
- **異常パターン**: 1個
- **無視パターン**: 0個

### パラメータ（log_params）

- **総パラメータ数**: 0件
- **理由**: `abstract_message()` で生成されるパターンには named capture group が含まれないため

### 異常判定ルール（pattern_rules）

- **総ルール数**: 6件
- **内訳**: すべて `threshold` タイプ（PCIe帯域幅など）

### アラート（alerts）

- **総アラート数**: 34,908件
- **ステータス内訳**:
  - `pending`: 34,908件
  - `sent`: 0件
  - `failed`: 0件

### AI解析（ai_analyses）

- **テーブル状態**: まだ作成されていません（設計上のプレースホルダ）
- **総解析数**: 0件

## テーブル構造

### regex_patterns

```sql
CREATE TABLE regex_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regex_rule TEXT UNIQUE,
    manual_regex_rule TEXT UNIQUE,
    sample_message TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT 'normal',
    severity TEXT,
    note TEXT,
    first_seen_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL,
    total_count INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (regex_rule IS NOT NULL AND manual_regex_rule IS NULL) OR
        (regex_rule IS NULL AND manual_regex_rule IS NOT NULL)
    )
)
```

### log_entries

```sql
CREATE TABLE log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME NOT NULL,
    host TEXT,
    component TEXT,
    raw_line TEXT NOT NULL,
    message TEXT NOT NULL,
    pattern_id INTEGER,
    is_known INTEGER DEFAULT 0,
    is_manual_mapped INTEGER DEFAULT 0,
    classification TEXT DEFAULT 'normal',
    severity TEXT,
    anomaly_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
)
```

### log_params

```sql
CREATE TABLE log_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    param_name TEXT NOT NULL,
    param_value_num REAL,
    param_value_text TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_id) REFERENCES log_entries(id)
)
```

### pattern_rules

```sql
CREATE TABLE pattern_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id INTEGER NOT NULL,
    rule_type TEXT NOT NULL,
    field_name TEXT,
    op TEXT NOT NULL,
    threshold_value1 REAL,
    threshold_value2 REAL,
    severity_if_match TEXT NOT NULL,
    is_abnormal_if_match INTEGER DEFAULT 1,
    message TEXT,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
)
```

### alerts

```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    alert_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,
    resolved_at DATETIME,
    FOREIGN KEY (log_id) REFERENCES log_entries(id)
)
```

## インデックス

- `idx_regex_patterns_regex_rule` - regex_patterns.regex_rule
- `idx_regex_patterns_label` - regex_patterns.label
- `idx_log_entries_ts` - log_entries.ts
- `idx_log_entries_pattern_id` - log_entries.pattern_id
- `idx_log_entries_classification` - log_entries.classification
- `idx_log_entries_is_known` - log_entries.is_known
- `idx_log_entries_is_manual_mapped` - log_entries.is_manual_mapped
- `idx_log_params_log_id` - log_params.log_id
- `idx_pattern_rules_pattern_id` - pattern_rules.pattern_id
- `idx_pattern_rules_is_active` - pattern_rules.is_active
- `idx_alerts_status` - alerts.status
- `idx_alerts_log_id` - alerts.log_id
- （`ai_analyses` 用のインデックスは未作成）

## 処理済みファイル

- `172.20.224.102.log-20250714` (最初のファイル)
- `172.20.224.101.log-20250714` (2番目のファイル)
- `172.20.224.103.log-20250714` (3番目のファイル)

## 次のステップ

1. **パターンのラベル付け**: 未知パターンを `normal` / `abnormal` / `ignore` に分類
2. **異常判定ルールの定義**: `pattern_rules` テーブルにルールを追加
3. **Slack通知の送信**: 保留中のアラートをSlackに送信
4. **未知ログの手動マッピング**: 既知パターンに紐付け

