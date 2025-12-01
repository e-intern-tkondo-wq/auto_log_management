# is_known フラグの決定システム
> このファイルで行うこと: `is_known` 判定ロジックと関連テーブル更新の流れを説明します。

## データベース

### テーブル: `log_entries`

`is_known` フラグは **`log_entries` テーブル**に格納されています。

```sql
CREATE TABLE log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts DATETIME NOT NULL,
    host TEXT,
    component TEXT,
    raw_line TEXT NOT NULL,
    message TEXT NOT NULL,
    pattern_id INTEGER,                    -- パターンID（外部キー）
    is_known INTEGER DEFAULT 0,            -- ← 既知/未知フラグ
    is_manual_mapped INTEGER DEFAULT 0,
    classification TEXT DEFAULT 'normal',
    severity TEXT,
    anomaly_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
)
```

- **カラム名**: `is_known`
- **型**: `INTEGER`
- **デフォルト値**: `0` (未知)
- **値の意味**:
  - `0`: 未知ログ（新規パターン）
  - `1`: 既知ログ（既存パターンにマッチ）

## 決定システム

### 決定ロジック（`src/ingest.py`）

`is_known` フラグは、ログインジェスト時に以下のロジックで決定されます：

```python
# 1. ログメッセージからパターンを生成
regex_rule = abstract_message(parsed['message'])

# 2. 既存パターンを検索
pattern_id, is_new_pattern = self._find_or_create_pattern(
    cursor, regex_rule, parsed['message'], verbose
)

# 3. 手動パターンもチェック（元のメッセージに対して直接マッチング）
if not pattern_id or is_new_pattern:
    manual_pattern_id = self._check_manual_patterns(cursor, parsed['message'])
    if manual_pattern_id:
        pattern_id = manual_pattern_id
        is_new_pattern = False

# 4. is_known フラグを決定
is_known = 1 if pattern_id and not is_new_pattern else 0
```

### 決定フロー

```
ログメッセージ
    ↓
abstract_message() でパターン生成
    ↓
┌─────────────────────────────────────┐
│ regex_patterns テーブルで検索        │
├─────────────────────────────────────┤
│ 1. regex_rule で検索                │
│    （自動生成パターン）              │
│                                     │
│ 2. manual_regex_rule で検索        │
│    （手動パターン、元のメッセージに  │
│     対して直接マッチング）           │
└─────────────────────────────────────┘
    ↓
既存パターンが見つかった？
    ├─ YES → pattern_id を設定
    │        is_new_pattern = False
    │        is_known = 1  ← 既知ログ
    │
    └─ NO  → regex_patterns に新規レコード追加
              pattern_id を設定
              is_new_pattern = True
              is_known = 0  ← 未知ログ
```

### 決定式

```python
is_known = 1 if pattern_id and not is_new_pattern else 0
```

**条件**:
- `pattern_id` が存在する **かつ**
- `is_new_pattern` が `False` の場合
  → `is_known = 1` (既知ログ)

それ以外の場合
  → `is_known = 0` (未知ログ)

## パターン検索の詳細

### 1. 自動生成パターンの検索

```python
def _find_or_create_pattern(self, cursor, regex_rule: str, sample_message: str, verbose: bool):
    # regex_rule と manual_regex_rule の両方をチェック
    cursor.execute("""
        SELECT id, total_count
        FROM regex_patterns
        WHERE regex_rule = ? OR manual_regex_rule = ?
    """, (regex_rule, regex_rule))
    
    row = cursor.fetchone()
    if row:
        # 既存パターン: カウントを更新
        return (row['id'], False)  # is_new_pattern = False
    else:
        # 新規パターン: 作成
        cursor.execute("""
            INSERT INTO regex_patterns
            (regex_rule, manual_regex_rule, sample_message, ...)
            VALUES (?, NULL, ?, ...)
        """, (regex_rule, sample_message, ...))
        return (cursor.lastrowid, True)  # is_new_pattern = True
```

### 2. 手動パターンの検索

```python
def _check_manual_patterns(self, cursor, message: str):
    # すべての手動パターンを取得
    cursor.execute("""
        SELECT id, manual_regex_rule
        FROM regex_patterns
        WHERE manual_regex_rule IS NOT NULL
    """)
    
    for row in cursor.fetchall():
        pattern = re.compile(row['manual_regex_rule'])
        if pattern.search(message):  # 元のメッセージに対して直接マッチング
            return row['id']
    
    return None
```

## データベースでの確認

### is_known フラグの分布

```sql
-- 既知/未知ログの件数
SELECT 
    is_known,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM log_entries), 2) as percentage
FROM log_entries
GROUP BY is_known;
```

### 既知ログの確認

```sql
-- 既知ログの一覧
SELECT 
    l.id,
    l.host,
    l.component,
    l.is_known,
    l.classification,
    p.regex_rule,
    p.manual_regex_rule,
    p.label as pattern_label
FROM log_entries l
JOIN regex_patterns p ON l.pattern_id = p.id
WHERE l.is_known = 1
LIMIT 10;
```

### 未知ログの確認

```sql
-- 未知ログの一覧
SELECT 
    l.id,
    l.host,
    l.component,
    l.is_known,
    l.classification,
    l.message
FROM log_entries l
WHERE l.is_known = 0
LIMIT 10;
```

## 重要なポイント

1. **`is_known` は `log_entries` テーブルに格納**
   - 各ログエントリごとに個別に設定される

2. **決定タイミング**
   - ログインジェスト時（`ingest.py` の `ingest_file()` メソッド内）

3. **決定基準**
   - `regex_patterns` テーブルに既存パターンが存在するかどうか
   - 自動生成パターン（`regex_rule`）と手動パターン（`manual_regex_rule`）の両方をチェック

4. **パターンマッチング**
   - 自動生成パターン: `abstract_message()` で生成したパターンと比較
   - 手動パターン: 元のメッセージに対して直接マッチング

5. **更新タイミング**
   - ログインジェスト時に一度だけ設定される
   - 後から手動でマッピングした場合は `is_manual_mapped` フラグも `1` になる

