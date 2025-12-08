"""
LLM解析: 未知ログをLLMで解析して異常判定・パターン追加
"""
import sys
import os
import json
from typing import Dict, Optional, List
from datetime import datetime

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.cli_tools import add_pattern

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class LLMAnalyzer:
    """LLMを使用してログを解析するクラス"""
    
    def __init__(self, db: Database, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Args:
            db: Databaseインスタンス
            api_key: OpenAI APIキー（Noneの場合は環境変数から取得）
            model: 使用するモデル名
        """
        self.db = db
        self.model = model
        
        # APIキーの取得
        if api_key:
            self.api_key = api_key
        else:
            # 環境変数から取得
            self.api_key = os.getenv('OPENAI_API_KEY')
            if not self.api_key:
                # .envファイルから読み込む
                self.api_key = self._load_env_file()
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable or create .env file.")
        
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        self.client = OpenAI(api_key=self.api_key)
    
    def _load_env_file(self) -> Optional[str]:
        """
        .envファイルからAPIキーを読み込む
        
        Returns:
            APIキー（見つからない場合はNone）
        """
        # プロジェクトルートの .env ファイルを探す
        current_dir = os.path.dirname(os.path.dirname(__file__))
        env_path = os.path.join(current_dir, '.env')
        
        if not os.path.exists(env_path):
            return None
        
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # コメント行と空行をスキップ
                    if not line or line.startswith('#'):
                        continue
                    # KEY=VALUE 形式をパース
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # クォートを削除
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        if key == 'OPENAI_API_KEY' and value:
                            return value
        except Exception as e:
            print(f"Warning: Failed to read .env file: {e}", file=sys.stderr)
        
        return None
    
    def analyze_log(self, log_id: int, log_entry: Dict) -> Dict:
        """
        単一のログエントリをLLMで解析
        
        Args:
            log_id: ログエントリのID
            log_entry: ログエントリ情報（message, host, component等）
            
        Returns:
            解析結果:
            {
                'is_abnormal': bool,
                'label': 'normal' | 'abnormal' | 'unknown',
                'severity': 'info' | 'warning' | 'critical',
                'reason': str,
                'pattern_suggestion': str (optional),
                'response': str
            }
        """
        prompt = self._create_prompt(log_entry)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a log analysis expert. Analyze system logs and determine if they are normal or abnormal. Provide your analysis in JSON format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            response_text = response.choices[0].message.content
            result = json.loads(response_text)
            
            # 解析結果をデータベースに保存
            self._save_analysis(log_id, prompt, response_text)
            
            return {
                'is_abnormal': result.get('is_abnormal', False),
                'label': result.get('label', 'unknown'),
                'severity': result.get('severity', 'unknown'),
                'reason': result.get('reason', ''),
                'pattern_suggestion': result.get('pattern_suggestion', ''),
                'response': response_text
            }
            
        except Exception as e:
            print(f"Error analyzing log {log_id} with LLM: {e}", file=sys.stderr)
            # エラー情報を保存
            self._save_analysis(log_id, prompt, f"Error: {str(e)}")
            return {
                'is_abnormal': False,
                'label': 'unknown',
                'severity': 'unknown',
                'reason': f'LLM analysis failed: {str(e)}',
                'pattern_suggestion': '',
                'response': ''
            }
    
    def _create_prompt(self, log_entry: Dict) -> str:
        """
        LLMへのプロンプトを作成
        
        Args:
            log_entry: ログエントリ情報
            
        Returns:
            プロンプト文字列
        """
        prompt = f"""Analyze the following system log entry and determine if it indicates an abnormal condition.

Log Information:
- Timestamp: {log_entry.get('ts', 'N/A')}
- Host: {log_entry.get('host', 'N/A')}
- Component: {log_entry.get('component', 'N/A')}
- Message: {log_entry.get('message', 'N/A')}

Please provide your analysis in JSON format with the following structure:
{{
    "is_abnormal": true/false,
    "label": "normal" or "abnormal" or "unknown",
    "severity": "info" or "warning" or "critical" or "unknown",
    "reason": "Brief explanation of your judgment",
    "pattern_suggestion": "Regular expression pattern suggestion if this is a normal log that should be added to the pattern database (optional)"
}}

Guidelines:
- "normal": Regular operational logs (e.g., initialization, status updates)
- "abnormal": Error logs, warnings that indicate problems, or logs that require attention
- "unknown": Logs that cannot be clearly classified

If the log is normal and should be added to the pattern database, provide a regex pattern suggestion in "pattern_suggestion".
"""
        return prompt
    
    def _save_analysis(self, log_id: int, prompt: str, response: str):
        """
        解析結果を ai_analyses テーブルに保存
        
        Args:
            log_id: ログエントリのID
            prompt: プロンプト
            response: LLMのレスポンス
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_analyses
            (log_id, prompt, response, model_name)
            VALUES (?, ?, ?, ?)
        """, (log_id, prompt, response, self.model))
        
        conn.commit()
    
    def process_unknown_logs(self, limit: int = 10, auto_add_pattern: bool = True) -> Dict:
        """
        未知ログを一括でLLM解析
        
        Args:
            limit: 処理するログ数の上限
            auto_add_pattern: LLMが正常と判断した場合に自動でパターンを追加するか
            
        Returns:
            処理結果:
            {
                'processed': int,
                'abnormal': int,
                'normal': int,
                'unknown': int,
                'patterns_added': int,
                'alerts_created': int
            }
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 未知ログを取得（まだLLM解析されていないもの）
        cursor.execute("""
            SELECT le.id, le.ts, le.host, le.component, le.message, le.raw_line
            FROM log_entries le
            LEFT JOIN ai_analyses aa ON le.id = aa.log_id
            WHERE le.is_known = 0
              AND aa.id IS NULL
            ORDER BY le.ts DESC
            LIMIT ?
        """, (limit,))
        
        unknown_logs = cursor.fetchall()
        
        if not unknown_logs:
            print("No unknown logs to process")
            return {
                'processed': 0,
                'abnormal': 0,
                'normal': 0,
                'unknown': 0,
                'patterns_added': 0,
                'alerts_created': 0
            }
        
        print(f"Processing {len(unknown_logs)} unknown logs with LLM...")
        
        stats = {
            'processed': 0,
            'abnormal': 0,
            'normal': 0,
            'unknown': 0,
            'patterns_added': 0,
            'alerts_created': 0
        }
        
        for log_row in unknown_logs:
            log_id = log_row['id']
            log_entry = {
                'ts': log_row['ts'],
                'host': log_row['host'],
                'component': log_row['component'],
                'message': log_row['message'],
                'raw_line': log_row['raw_line']
            }
            
            # LLMで解析
            result = self.analyze_log(log_id, log_entry)
            stats['processed'] += 1
            
            # 結果に基づいて処理
            if result['label'] == 'abnormal':
                stats['abnormal'] += 1
                # アラートを作成
                self._create_alert(log_id, 'abnormal')
                stats['alerts_created'] += 1
                
                # log_entries を更新
                cursor.execute("""
                    UPDATE log_entries
                    SET classification = ?,
                        severity = ?,
                        anomaly_reason = ?
                    WHERE id = ?
                """, (result['label'], result['severity'], result['reason'], log_id))
                
            elif result['label'] == 'normal' and auto_add_pattern:
                stats['normal'] += 1
                
                # パターンを追加
                if result.get('pattern_suggestion'):
                    try:
                        # LLMが提案したパターンを使用（手動パターンとして追加）
                        pattern_id = add_pattern(
                            db_path=self.db.db_path,
                            regex_rule=result['pattern_suggestion'],
                            sample_message=log_entry['message'],
                            label='normal',
                            severity=result['severity'] if result['severity'] != 'unknown' else 'info',
                            component=log_entry.get('component'),
                            note=f"LLM自動追加: {result['reason']}",
                            update_existing=False
                        )
                        
                        # ログエントリをパターンに紐付け
                        cursor.execute("""
                            UPDATE log_entries
                            SET pattern_id = ?,
                                is_known = 1,
                                is_manual_mapped = 1,
                                classification = ?,
                                severity = ?
                            WHERE id = ?
                        """, (pattern_id, result['label'], result['severity'], log_id))
                        
                        stats['patterns_added'] += 1
                        print(f"  ✅ Log {log_id}: Added pattern {pattern_id} (normal)")
                    except Exception as e:
                        print(f"  ⚠️  Log {log_id}: Failed to add pattern: {e}", file=sys.stderr)
                else:
                    # パターン提案がない場合は abstract_message() で生成
                    from src.abstract_message import abstract_message
                    try:
                        regex_rule = abstract_message(log_entry['message'])
                        # 自動生成パターンを使用（regex_rule に格納される）
                        pattern_id = add_pattern(
                            db_path=self.db.db_path,
                            regex_rule=regex_rule,
                            sample_message=log_entry['message'],
                            label='normal',
                            severity=result['severity'] if result['severity'] != 'unknown' else 'info',
                            component=log_entry.get('component'),
                            note=f"LLM自動追加（自動生成パターン）: {result['reason']}",
                            update_existing=False
                        )
                        
                        cursor.execute("""
                            UPDATE log_entries
                            SET pattern_id = ?,
                                is_known = 1,
                                is_manual_mapped = 1,
                                classification = ?,
                                severity = ?
                            WHERE id = ?
                        """, (pattern_id, result['label'], result['severity'], log_id))
                        
                        stats['patterns_added'] += 1
                        print(f"  ✅ Log {log_id}: Added pattern {pattern_id} (normal, auto-generated)")
                    except Exception as e:
                        print(f"  ⚠️  Log {log_id}: Failed to add pattern: {e}", file=sys.stderr)
            else:
                stats['unknown'] += 1
                print(f"  ℹ️  Log {log_id}: Classified as {result['label']}")
            
            conn.commit()
        
        print(f"\nProcessing complete:")
        print(f"  Processed: {stats['processed']}")
        print(f"  Abnormal: {stats['abnormal']}")
        print(f"  Normal: {stats['normal']}")
        print(f"  Unknown: {stats['unknown']}")
        print(f"  Patterns added: {stats['patterns_added']}")
        print(f"  Alerts created: {stats['alerts_created']}")
        
        return stats
    
    def _create_alert(self, log_id: int, alert_type: str):
        """
        アラートレコードを作成
        
        Args:
            log_id: ログエントリのID
            alert_type: アラートタイプ（'abnormal' または 'unknown'）
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO alerts
            (log_id, alert_type, channel, status)
            VALUES (?, ?, 'slack', 'pending')
        """, (log_id, alert_type))


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze unknown logs with LLM')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    parser.add_argument('--api-key', help='OpenAI API key (or set OPENAI_API_KEY env var or .env file)')
    parser.add_argument('--model', default='gpt-4o-mini', help='Model name (default: gpt-4o-mini)')
    parser.add_argument('--limit', type=int, default=10, help='Number of logs to process')
    parser.add_argument('--no-auto-add', action='store_true', help='Do not automatically add patterns for normal logs')
    parser.add_argument('--log-id', type=int, help='Analyze specific log ID')
    
    args = parser.parse_args()
    
    db = Database(args.db)
    
    try:
        analyzer = LLMAnalyzer(db, api_key=args.api_key, model=args.model)
        
        if args.log_id:
            # 特定のログを解析
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, ts, host, component, message, raw_line
                FROM log_entries
                WHERE id = ?
            """, (args.log_id,))
            
            log_row = cursor.fetchone()
            if not log_row:
                print(f"Error: Log {args.log_id} not found")
                sys.exit(1)
            
            log_entry = {
                'ts': log_row['ts'],
                'host': log_row['host'],
                'component': log_row['component'],
                'message': log_row['message'],
                'raw_line': log_row['raw_line']
            }
            
            result = analyzer.analyze_log(args.log_id, log_entry)
            print(f"\nAnalysis result for log {args.log_id}:")
            print(f"  Label: {result['label']}")
            print(f"  Severity: {result['severity']}")
            print(f"  Is abnormal: {result['is_abnormal']}")
            print(f"  Reason: {result['reason']}")
            if result.get('pattern_suggestion'):
                print(f"  Pattern suggestion: {result['pattern_suggestion']}")
        else:
            # 未知ログを一括処理
            analyzer.process_unknown_logs(
                limit=args.limit,
                auto_add_pattern=not args.no_auto_add
            )
    
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Install openai package: pip install openai", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    main()

