# よく使うSQLクエリ集
> このファイルで行うこと: デバッグや調査で頻出するSQLクエリ例をまとめます。

## 172.20.224.101由来の未知ログを取得

### 基本的なクエリ

```sql
-- 172.20.224.101由来の未知ログを取得
SELECT 
    id,
    ts,
    host,
    component,
    message,
    raw_line,
    is_known,
    classification,
    pattern_id
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
ORDER BY ts DESC;
```

### 件数のみ取得

```sql
-- 172.20.224.101由来の未知ログの件数
SELECT COUNT(*) as unknown_count
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0;
```

### コンポーネント別に集計

```sql
-- 172.20.224.101由来の未知ログをコンポーネント別に集計
SELECT 
    component,
    COUNT(*) as count
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
GROUP BY component
ORDER BY count DESC;
```

### 詳細情報を含むクエリ

```sql
-- 172.20.224.101由来の未知ログ（パターン情報も含む）
SELECT 
    l.id,
    l.ts,
    l.host,
    l.component,
    l.message,
    l.is_known,
    l.classification,
    l.pattern_id,
    p.regex_rule,
    p.sample_message,
    p.label as pattern_label
FROM log_entries l
LEFT JOIN regex_patterns p ON l.pattern_id = p.id
WHERE l.host = '172.20.224.101' 
  AND l.is_known = 0
ORDER BY l.ts DESC;
```

### 最新のN件を取得

```sql
-- 172.20.224.101由来の未知ログ（最新10件）
SELECT 
    id,
    ts,
    component,
    SUBSTR(message, 1, 100) as message_preview,
    is_known,
    classification
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
ORDER BY ts DESC
LIMIT 10;
```

### メッセージの一部を検索

```sql
-- 172.20.224.101由来の未知ログで、メッセージに特定の文字列を含むもの
SELECT 
    id,
    ts,
    component,
    message
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
  AND message LIKE '%error%'
ORDER BY ts DESC;
```

### 時間範囲で絞り込み

```sql
-- 172.20.224.101由来の未知ログ（直近24時間）
SELECT 
    id,
    ts,
    component,
    message
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
  AND ts >= datetime('now', '-24 hours')
ORDER BY ts DESC;
```

### CSV形式でエクスポート

```sql
-- 172.20.224.101由来の未知ログをCSV形式で出力
.mode csv
.headers on
.output unknown_logs_172.20.224.101.csv
SELECT 
    id,
    ts,
    host,
    component,
    message,
    raw_line,
    is_known,
    classification,
    pattern_id
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
ORDER BY ts DESC;
```

## その他の便利なクエリ

### すべての未知ログを取得

```sql
-- すべての未知ログ
SELECT 
    id,
    ts,
    host,
    component,
    message,
    is_known,
    classification
FROM log_entries
WHERE is_known = 0
ORDER BY ts DESC;
```

### ホスト別の未知ログ件数

```sql
-- ホスト別の未知ログ件数
SELECT 
    host,
    COUNT(*) as unknown_count,
    COUNT(*) * 100.0 / (SELECT COUNT(*) FROM log_entries WHERE host = le.host) as unknown_percentage
FROM log_entries le
WHERE is_known = 0
GROUP BY host
ORDER BY unknown_count DESC;
```

### 未知ログのパターン分布

```sql
-- 172.20.224.101由来の未知ログのパターン分布
SELECT 
    p.id as pattern_id,
    p.regex_rule,
    p.sample_message,
    COUNT(*) as log_count
FROM log_entries l
JOIN regex_patterns p ON l.pattern_id = p.id
WHERE l.host = '172.20.224.101' 
  AND l.is_known = 0
GROUP BY p.id
ORDER BY log_count DESC;
```

### 手動マッピングされていない未知ログ

```sql
-- 172.20.224.101由来の未知ログ（手動マッピングされていないもの）
SELECT 
    id,
    ts,
    component,
    message,
    is_manual_mapped
FROM log_entries
WHERE host = '172.20.224.101' 
  AND is_known = 0
  AND is_manual_mapped = 0
ORDER BY ts DESC;
```

