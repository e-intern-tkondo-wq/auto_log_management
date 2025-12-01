"""
Slack通知: アラートをSlackに送信
"""
import requests
import json
import sys
import os
from datetime import datetime
from typing import Optional

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


class SlackNotifier:
    """Slack通知を送信するクラス"""
    
    def __init__(self, webhook_url: Optional[str] = None, db: Optional[Database] = None):
        """
        Args:
            webhook_url: Slack Incoming Webhook URL
            db: Databaseインスタンス（通知履歴を記録するため）
        """
        self.webhook_url = webhook_url
        self.db = db
    
    def send_alert(self, log_id: int, alert_type: str, log_entry: dict) -> bool:
        """
        アラートをSlackに送信
        
        Args:
            log_id: ログエントリのID
            alert_type: アラートタイプ（'abnormal' または 'unknown'）
            log_entry: ログエントリ情報（ts, host, component, message, classification, severity等）
            
        Returns:
            送信成功の場合True
        """
        if not self.webhook_url:
            print("Warning: Slack webhook URL not configured", file=__import__('sys').stderr)
            return False
        
        # メッセージ本文を作成
        message_text = self._format_message(log_id, alert_type, log_entry)
        
        # Slackペイロード
        payload = {
            "text": f"🚨 Log Alert: {alert_type.upper()}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message_text
                    }
                }
            ]
        }
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            response.raise_for_status()
            
            # データベースに送信成功を記録
            if self.db:
                self._update_alert_status(log_id, 'sent', message_text)
            
            return True
            
        except Exception as e:
            print(f"Error sending Slack notification: {e}", file=__import__('sys').stderr)
            
            # データベースに送信失敗を記録
            if self.db:
                self._update_alert_status(log_id, 'failed', None, str(e))
            
            return False
    
    def _format_message(self, log_id: int, alert_type: str, log_entry: dict) -> str:
        """
        通知メッセージをフォーマット
        
        Args:
            log_id: ログエントリのID
            alert_type: アラートタイプ
            log_entry: ログエントリ情報
            
        Returns:
            フォーマット済みメッセージ
        """
        lines = [
            f"*Alert Type:* {alert_type}",
            f"*Log ID:* {log_id}",
            f"*Timestamp:* {log_entry.get('ts', 'N/A')}",
            f"*Host:* {log_entry.get('host', 'N/A')}",
            f"*Component:* {log_entry.get('component', 'N/A')}",
            f"*Classification:* {log_entry.get('classification', 'N/A')}",
        ]
        
        if log_entry.get('severity'):
            lines.append(f"*Severity:* {log_entry['severity']}")
        
        if log_entry.get('anomaly_reason'):
            lines.append(f"*Reason:* {log_entry['anomaly_reason']}")
        
        lines.append("")
        lines.append("*Message:*")
        lines.append(f"```{log_entry.get('message', 'N/A')[:500]}```")
        
        lines.append("")
        lines.append("*Raw Line:*")
        lines.append(f"```{log_entry.get('raw_line', 'N/A')[:500]}```")
        
        return "\n".join(lines)
    
    def _update_alert_status(self, log_id: int, status: str, message: Optional[str] = None, error: Optional[str] = None):
        """
        アラートのステータスを更新
        
        Args:
            log_id: ログエントリのID
            status: ステータス（'sent' または 'failed'）
            message: 送信したメッセージ（送信成功時）
            error: エラーメッセージ（送信失敗時）
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if status == 'sent':
            cursor.execute("""
                UPDATE alerts
                SET status = ?,
                    message = ?,
                    sent_at = ?
                WHERE log_id = ? AND status = 'pending'
            """, (status, message, datetime.now(), log_id))
        else:  # failed
            cursor.execute("""
                UPDATE alerts
                SET status = ?,
                    message = ?
                WHERE log_id = ? AND status = 'pending'
            """, (status, error, log_id))
        
        conn.commit()
    
    def process_pending_alerts(self):
        """
        保留中のアラートを処理してSlackに送信
        """
        if not self.db:
            print("Error: Database not configured", file=__import__('sys').stderr)
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 保留中のアラートを取得
        cursor.execute("""
            SELECT a.id, a.log_id, a.alert_type,
                   l.ts, l.host, l.component, l.message, l.raw_line,
                   l.classification, l.severity, l.anomaly_reason
            FROM alerts a
            JOIN log_entries l ON a.log_id = l.id
            WHERE a.status = 'pending'
            ORDER BY a.created_at
        """)
        
        alerts = cursor.fetchall()
        
        if not alerts:
            print("No pending alerts")
            return
        
        print(f"Processing {len(alerts)} pending alerts...")
        
        for alert in alerts:
            log_entry = {
                'ts': alert['ts'],
                'host': alert['host'],
                'component': alert['component'],
                'message': alert['message'],
                'raw_line': alert['raw_line'],
                'classification': alert['classification'],
                'severity': alert['severity'],
                'anomaly_reason': alert['anomaly_reason']
            }
            
            self.send_alert(alert['log_id'], alert['alert_type'], log_entry)


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='Send pending alerts to Slack')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    parser.add_argument('--webhook-url', help='Slack webhook URL (or set SLACK_WEBHOOK_URL env var)')
    
    args = parser.parse_args()
    
    webhook_url = args.webhook_url or os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        print("Error: Slack webhook URL not provided", file=__import__('sys').stderr)
        print("Use --webhook-url or set SLACK_WEBHOOK_URL environment variable", file=__import__('sys').stderr)
        sys.exit(1)
    
    db = Database(args.db)
    notifier = SlackNotifier(webhook_url, db)
    
    try:
        notifier.process_pending_alerts()
    finally:
        db.close()


if __name__ == '__main__':
    import sys
    main()

