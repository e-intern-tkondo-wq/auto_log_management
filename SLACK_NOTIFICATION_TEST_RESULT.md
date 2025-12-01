# Slack通知テスト結果
> このファイルで行うこと: Slack通知のテスト環境・結果・ペイロード例を記録します。

## テスト環境

- **テスト用エンドポイント**: https://httpbin.org/post
- **仮想環境**: `venv/` を作成して `requests` をインストール
- **テストスクリプト**: `test_slack_notifier.py`

## テスト結果

### ✅ POSTリクエストは正常に送信されました

**Status Code**: 200 OK

### 送信されるペイロードの構造

```json
{
  "text": "🚨 Log Alert: UNKNOWN",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Alert Type:* unknown\n*Log ID:* 1\n*Timestamp:* 2025-07-14 11:20:03\n*Host:* 172.20.224.101\n*Component:* kernel\n*Classification:* unknown\n*Severity:* unknown\n\n*Message:*\n```[ログメッセージ]```\n\n*Raw Line:*\n```[元のログ行]```"
      }
    }
  ]
}
```

### メッセージ本文の内容

- **Alert Type**: `unknown` または `abnormal`
- **Log ID**: ログエントリのID（データベースで詳細を引ける）
- **Timestamp**: ログのタイムスタンプ
- **Host**: ホスト名/IP
- **Component**: コンポーネント名（例: "kernel"）
- **Classification**: `normal` / `abnormal` / `unknown` / `ignore`
- **Severity**: `info` / `warning` / `critical` / `unknown`
- **Reason**: 異常理由（異常ログの場合）
- **Message**: ログメッセージ本体（最大500文字）
- **Raw Line**: 元のログ行全体（最大500文字）

### HTTPリクエスト情報

- **URL**: `<Slack Webhook URL>`
- **Method**: `POST`
- **Headers**: 
  - `Content-Type: application/json`
- **Body**: 上記のJSONペイロード

## 確認事項

✅ **ペイロード構造**: Slack Block Kit形式で正しくフォーマットされている
✅ **メッセージ内容**: 必要な情報（severity, classification, host, ts, component, message, log_id）がすべて含まれている
✅ **POSTリクエスト**: 正常に送信され、httpbin.orgから200 OKが返されている
✅ **JSON形式**: 正しいJSON形式で送信されている

## 実際のSlack Webhook URLでの使用

実際のSlack Webhook URLを使用する場合：

```bash
# 環境変数で設定
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# またはコマンドライン引数で指定
python src/slack_notifier.py --webhook-url https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## テストスクリプトの使用方法

```bash
# 仮想環境を有効化
source venv/bin/activate

# テスト実行（httpbin.orgを使用）
python test_slack_notifier.py --limit 3
```

## 結論

`slack_notifier.py` は正常に動作しており、適切なPOSTリクエストが送信されています。

- ✅ ペイロード構造は正しい
- ✅ メッセージ内容は完全
- ✅ HTTPリクエストは正常に送信される
- ✅ Slack Block Kit形式に準拠している

実際のSlack Webhook URLに置き換えることで、Slackに通知を送信できます。

