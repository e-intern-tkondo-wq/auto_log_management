# アラート送信テスト結果

> このファイルで行うこと: 異常検知時のアラート送信機能の動作確認結果を記録します。

## テスト日時

2025年12月XX日

## テスト内容

### テスト対象

- **異常ログ**: GPU温度が80°Cを超えたログ（temp=85°C, 90°C）
- **閾値ルール**: `temp > 80.0` → `severity='critical'`

### テスト1: アラートの作成確認

#### 確認クエリ

```sql
SELECT 
    le.id as log_id,
    le.message,
    le.classification,
    le.severity,
    le.anomaly_reason,
    a.id as alert_id,
    a.alert_type,
    a.status
FROM log_entries le
LEFT JOIN alerts a ON le.id = a.log_id
WHERE le.classification = 'abnormal'
ORDER BY le.id DESC;
```

#### 結果

✅ **アラートが正しく作成されています**

- 異常ログ（temp=85°C, 90°C）に対して`alerts`テーブルにレコードが作成された
- `alert_type='abnormal'`
- `status='pending'`（送信待ち）

### テスト2: アラート送信機能のテスト

#### テスト方法

```bash
# テスト用エンドポイント（httpbin.org）を使用
python3 src/slack_notifier.py \
  --db db/monitor.db \
  --webhook-url https://httpbin.org/post
```

#### 送信されるペイロード

```json
{
  "text": "🚨 Log Alert: ABNORMAL",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Alert Type:* abnormal\n*Log ID:* 39343\n*Timestamp:* 2025-07-14 11:20:18\n*Host:* 172.20.224.102\n*Component:* kernel\n*Classification:* abnormal\n*Severity:* critical\n\n*Reason:*\n```GPU temp > 80°C```\n\n*Message:*\n```[    0.005841] GPU temp: 85°C```\n\n*Raw Line:*\n```Jul 14 11:20:18 172.20.224.102 kernel: [    0.005841] GPU temp: 85°C```"
      }
    }
  ]
}
```

#### 結果

✅ **POSTリクエストが正常に送信されました**

- HTTPステータスコード: 200 OK
- ペイロードが正しくフォーマットされている
- アラート情報（Log ID, Timestamp, Host, Component, Classification, Severity, Reason, Message）がすべて含まれている

### テスト3: アラート送信後の状態確認

#### 確認クエリ

```sql
SELECT 
    a.id,
    a.log_id,
    a.alert_type,
    a.status,
    a.sent_at,
    le.message,
    le.classification
FROM alerts a
JOIN log_entries le ON a.log_id = le.id
WHERE le.message LIKE '%GPU temp%'
ORDER BY a.id DESC;
```

#### 結果

✅ **アラート送信後に`status`が`'sent'`に更新されました**

- `status='sent'`
- `sent_at`に送信時刻が記録された

---

## 動作確認のまとめ

### ✅ アラート作成

- **実装箇所**: `src/ingest.py` の178-180行目
- **動作**: `classification='abnormal'`または`'unknown'`の場合、`alerts`テーブルに`status='pending'`でレコードを作成
- **確認結果**: ✅ 正常に動作

### ✅ アラート送信

- **実装箇所**: `src/slack_notifier.py`
- **動作**: `process_pending_alerts()`で保留中のアラートを取得し、`send_alert()`でPOST送信
- **確認結果**: ✅ 正常に動作

### ✅ 送信後の状態更新

- **実装箇所**: `src/slack_notifier.py` の`_update_alert_status()`メソッド
- **動作**: 送信成功時に`status='sent'`、失敗時に`status='failed'`に更新
- **確認結果**: ✅ 正常に動作

---

## 実際のSlack Webhook URLでの使用

### セットアップ

```bash
# .envファイルに追加
echo "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL" >> .env

# または環境変数で設定
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 実行

```bash
# 保留中のアラートを送信
python3 src/slack_notifier.py --db db/monitor.db

# または環境変数から読み込む
python3 src/slack_notifier.py --db db/monitor.db
```

### 定期実行

```bash
# cronで定期実行（例: 5分ごと）
*/5 * * * * cd /path/to/final_creation && python3 src/slack_notifier.py --db db/monitor.db
```

---

## テスト結果の詳細

### テストログ

| log_id | message | classification | severity | anomaly_reason | alert_id | alert_type | status |
|--------|---------|---------------|----------|----------------|----------|------------|--------|
| 39343 | GPU temp: 85°C | abnormal | critical | GPU temp > 80°C | 1895 | abnormal | pending → sent |
| 39344 | GPU temp: 90°C | abnormal | critical | GPU temp > 80°C | 1896 | abnormal | pending → sent |

### POSTリクエストの詳細

- **URL**: `https://httpbin.org/post`（テスト用）
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`
- **Status Code**: 200 OK
- **Response**: 送信されたペイロードが返される

---

## 結論

✅ **アラート送信機能は正常に動作しています**

1. ✅ 異常ログが登録されると、`alerts`テーブルに`status='pending'`でレコードが作成される
2. ✅ `slack_notifier.py`で保留中のアラートを取得し、POST送信できる
3. ✅ 送信成功時に`status='sent'`に更新される
4. ✅ ペイロードに必要な情報（Log ID, Timestamp, Host, Component, Classification, Severity, Reason, Message）がすべて含まれている

実際のSlack Webhook URLを設定すれば、すぐに使用できます。

