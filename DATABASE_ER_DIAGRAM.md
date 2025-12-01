# データベース ER図
> このファイルで行うこと: SQLiteスキーマとテーブル間リレーションを一覧化します。

## テーブル一覧と関連性

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         regex_patterns                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│     regex_rule            TEXT UNIQUE (NULL可)                          │
│     manual_regex_rule     TEXT UNIQUE (NULL可)                          │
│     sample_message        TEXT NOT NULL                                 │
│     label                 TEXT NOT NULL DEFAULT 'unknown'                │
│     severity              TEXT                                           │
│     note                  TEXT                                           │
│     first_seen_at         DATETIME NOT NULL                              │
│     last_seen_at          DATETIME NOT NULL                             │
│     total_count           INTEGER NOT NULL DEFAULT 1                     │
│     created_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
│     updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP            │
│                                                                           │
│ CHECK: (regex_rule IS NOT NULL AND manual_regex_rule IS NULL) OR         │
│        (regex_rule IS NULL AND manual_regex_rule IS NOT NULL)            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              │ 1
                              │
                              │
                              │ FK: pattern_id
                              │
                              │ N
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         log_entries                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                       │
│     ts                    DATETIME NOT NULL                             │
│     host                  TEXT                                          │
│     component             TEXT                                           │
│     raw_line              TEXT NOT NULL                                  │
│     message               TEXT NOT NULL                                  │
│ FK  pattern_id            INTEGER → regex_patterns.id                    │
│     is_known              INTEGER DEFAULT 0                              │
│     is_manual_mapped      INTEGER DEFAULT 0                              │
│     classification        TEXT DEFAULT 'unknown'                         │
│     severity              TEXT                                           │
│     anomaly_reason        TEXT                                           │
│     created_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
│     updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              │ 1
                              │
                              │
                              │ FK: log_id
                              │
                              │ N
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         log_params                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│ FK  log_id                INTEGER NOT NULL → log_entries.id              │
│     param_name            TEXT NOT NULL                                  │
│     param_value_num       REAL                                           │
│     param_value_text      TEXT                                           │
│     created_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         regex_patterns                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│     ... (上記参照)                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              │ 1
                              │
                              │
                              │ FK: pattern_id
                              │
                              │ N
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         pattern_rules                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│ FK  pattern_id            INTEGER NOT NULL → regex_patterns.id           │
│     rule_type             TEXT NOT NULL                                  │
│     field_name            TEXT                                           │
│     op                    TEXT NOT NULL                                  │
│     threshold_value1      REAL                                           │
│     threshold_value2      REAL                                           │
│     severity_if_match     TEXT NOT NULL                                  │
│     is_abnormal_if_match  INTEGER DEFAULT 1                              │
│     message               TEXT                                           │
│     is_active             INTEGER DEFAULT 1                              │
│     created_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
│     updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         log_entries                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│     ... (上記参照)                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              │ 1
                              │
                              │
                              │ FK: log_id
                              │
                              │ N
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         alerts                                           │
├─────────────────────────────────────────────────────────────────────────┤
│ PK  id                    INTEGER                                        │
│ FK  log_id                INTEGER NOT NULL → log_entries.id             │
│     alert_type            TEXT NOT NULL                                  │
│     channel               TEXT NOT NULL                                  │
│     status                TEXT NOT NULL                                  │
│     message               TEXT                                           │
│     created_at            DATETIME DEFAULT CURRENT_TIMESTAMP             │
│     sent_at               DATETIME                                       │
│     resolved_at           DATETIME                                       │
└─────────────────────────────────────────────────────────────────────────┘

```

## テーブル間の関係

### 1. regex_patterns (パターンマスタ)
- **役割**: ログパターンの定義を保持
- **特徴**:
  - `regex_rule`: 自動生成された正規表現パターン（`abstract_message()` の出力）
  - `manual_regex_rule`: 手動で作成した正規表現パターン
  - どちらか一方のみが NULL でない（CHECK制約）
- **関連**:
  - `log_entries` と 1対多の関係（`pattern_id`）
  - `pattern_rules` と 1対多の関係（`pattern_id`）

### 2. log_entries (ログ本体)
- **役割**: 実際のログエントリを保存
- **特徴**:
  - `is_known`: 既知ログかどうか（0=未知, 1=既知）
  - `is_manual_mapped`: 手動でマッピングされたかどうか
  - `classification`: 分類（normal/abnormal/unknown/ignore）
- **関連**:
  - `regex_patterns` と多対1の関係（`pattern_id`）
  - `log_params` と 1対多の関係（`log_id`）
  - `alerts` と 1対多の関係（`log_id`）
  - `ai_analyses` と 1対多の関係（`log_id`）

### 3. log_params (パラメータ抽出結果)
- **役割**: ログから抽出したパラメータ値を保存
- **特徴**:
  - `param_value_num`: 数値として保存可能な場合
  - `param_value_text`: テキストとして保存
- **関連**:
  - `log_entries` と多対1の関係（`log_id`）

### 4. pattern_rules (異常判定ルール)
- **役割**: パターンごとの異常判定ルールを定義
- **特徴**:
  - `rule_type`: ルールタイプ（threshold, contains など）
  - `op`: 演算子（>, <, ==, between, contains など）
  - `is_active`: ルールが有効かどうか
- **関連**:
  - `regex_patterns` と多対1の関係（`pattern_id`）

### 5. alerts (通知履歴)
- **役割**: Slack等に送った通知の履歴を保存
- **特徴**:
  - `status`: ステータス（pending/sent/failed/resolved）
  - `alert_type`: アラートタイプ（abnormal/unknown）
- **関連**:
  - `log_entries` と多対1の関係（`log_id`）


## データフロー

### ログインジェスト時の処理フロー

```
1. ログファイル読み込み
   ↓
2. ログ行をパース（log_parser.py）
   ↓
3. abstract_message() でパターン生成
   ↓
4. regex_patterns テーブルで既存パターンを検索
   ├─ regex_rule で検索
   └─ manual_regex_rule で検索（元のメッセージに対して直接マッチング）
   ↓
5. 既存パターンが見つかった場合
   ├─ pattern_id を設定
   ├─ is_known = 1
   └─ log_entries に INSERT
   ↓
6. 新規パターンの場合
   ├─ regex_patterns に新規レコード追加（regex_rule に格納）
   ├─ pattern_id を設定
   ├─ is_known = 0
   └─ log_entries に INSERT
   ↓
7. 既知ログの場合
   ├─ log_params にパラメータ抽出結果を保存
   ├─ pattern_rules を評価して異常判定
   └─ 異常の場合は classification を更新
   ↓
8. abnormal または unknown の場合
   └─ alerts にレコード追加
```

## インデックス

### regex_patterns
- `idx_regex_patterns_regex_rule`: `regex_rule` (UNIQUE, WHERE regex_rule IS NOT NULL)
- `idx_regex_patterns_manual_regex_rule`: `manual_regex_rule` (UNIQUE, WHERE manual_regex_rule IS NOT NULL)
- `idx_regex_patterns_label`: `label`

### log_entries
- `idx_log_entries_ts`: `ts`
- `idx_log_entries_pattern_id`: `pattern_id`
- `idx_log_entries_classification`: `classification`
- `idx_log_entries_is_known`: `is_known`
- `idx_log_entries_is_manual_mapped`: `is_manual_mapped`

### log_params
- `idx_log_params_log_id`: `log_id`

### pattern_rules
- `idx_pattern_rules_pattern_id`: `pattern_id`
- `idx_pattern_rules_is_active`: `is_active`

### alerts
- `idx_alerts_status`: `status`
- `idx_alerts_log_id`: `log_id`

## 制約

### CHECK制約
- `regex_patterns`: `(regex_rule IS NOT NULL AND manual_regex_rule IS NULL) OR (regex_rule IS NULL AND manual_regex_rule IS NOT NULL)`

### 外部キー制約
- `log_entries.pattern_id` → `regex_patterns.id`
- `log_params.log_id` → `log_entries.id`
- `pattern_rules.pattern_id` → `regex_patterns.id`
- `alerts.log_id` → `log_entries.id`
- `ai_analyses.log_id` → `log_entries.id`

## 統計情報

現在のデータベース状態:
- `regex_patterns`: 1,812件（自動パターン: 1,809件、手動パターン: 3件）
- `log_entries`: 26,210件
- `log_params`: 0件（named capture groupを含むパターンが必要）
- `pattern_rules`: 1件（ルールが1件定義済み）
- `alerts`: 25,314件（pending状態）

## テーブル間の関係図（簡易版）

```
regex_patterns (1) ──────< (N) log_entries
     │                          │
     │                          ├──< (N) log_params
     │                          │
     │                          ├──< (N) alerts
     │                          │
     └──< (N) pattern_rules
```

### 関係の説明

1. **regex_patterns ↔ log_entries**: 1対多
   - 1つのパターンに複数のログエントリが紐付く
   - `log_entries.pattern_id` → `regex_patterns.id`

2. **log_entries ↔ log_params**: 1対多
   - 1つのログエントリから複数のパラメータを抽出可能
   - `log_params.log_id` → `log_entries.id`

3. **log_entries ↔ alerts**: 1対多
   - 1つのログエントリに対して複数のアラートを生成可能（再送など）
   - `alerts.log_id` → `log_entries.id`

4. **regex_patterns ↔ pattern_rules**: 1対多
   - 1つのパターンに対して複数の異常判定ルールを定義可能
   - `pattern_rules.pattern_id` → `regex_patterns.id`

