"""
インジェスト処理: ログファイルを取り込んでデータベースに保存
"""
import sys
import os
from datetime import datetime
from typing import Optional, Dict

# パスを追加してモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.log_parser import LogParser
from src.abstract_message import abstract_message, validate_pattern
from src.param_extractor import ParamExtractor
from src.anomaly_detector import AnomalyDetector


class LogIngester:
    """ログ取り込み処理を実行するクラス"""
    
    def __init__(self, db: Database):
        """
        Args:
            db: Databaseインスタンス
        """
        self.db = db
        self.parser = LogParser()
        self.param_extractor = ParamExtractor()
        self.anomaly_detector = AnomalyDetector(db)
    
    def ingest_file(self, file_path: str, verbose: bool = False):
        """
        ログファイルを取り込む
        
        Args:
            file_path: ログファイルのパス
            verbose: 詳細出力するかどうか
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        stats = {
            'total_lines': 0,
            'parsed_lines': 0,
            'new_patterns': 0,
            'existing_patterns': 0,
            'errors': 0
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    stats['total_lines'] += 1
                    
                    if verbose and line_num % 1000 == 0:
                        print(f"Processing line {line_num}...", file=sys.stderr)
                    
                    try:
                        # ログ行をパース
                        parsed = self.parser.parse_line(line)
                        #ts, host, component, message, raw_lineの４項目を表示
                        
                        # abstract_message でパターンを生成
                        #正規表現に変換
                        try:
                            regex_rule = abstract_message(parsed['message'])
                            
                            # パターンの検証（オプション、デバッグ用）
                            if not validate_pattern(regex_rule, parsed['message']):
                                if verbose:
                                    print(f"Warning: Pattern validation failed for line {line_num}", file=sys.stderr)
                        except Exception as e:
                            if verbose:
                                print(f"Error generating pattern for line {line_num}: {e}", file=sys.stderr)
                            regex_rule = None
                        
                        # パターンをデータベースから検索または作成
                        pattern_id = None
                        is_new_pattern = False
                        
                        if regex_rule:
                            # まず既存パターンを検索（regex_rule と manual_regex_rule の両方をチェック）
                            pattern_id, is_new_pattern = self._find_or_create_pattern(
                                cursor, regex_rule, parsed['message'], verbose
                            )
                            if pattern_id:
                                if is_new_pattern:
                                    stats['new_patterns'] += 1
                                else:
                                    stats['existing_patterns'] += 1
                        
                        # 手動パターンもチェック（元のメッセージに対して直接マッチング）
                        if not pattern_id or is_new_pattern:
                            manual_pattern_id = self._check_manual_patterns(cursor, parsed['message'])
                            if manual_pattern_id:
                                pattern_id = manual_pattern_id
                                is_new_pattern = False
                                stats['existing_patterns'] += 1
                        
                        # 既知か未知かを判断
                        is_known = 1 if pattern_id and not is_new_pattern else 0
                        
                        # パターンのラベルに基づいてclassificationを決定
                        # デフォルトは 'unknown'
                        classification = 'unknown'
                        severity = None
                        
                        # 既知ログ（is_known=1）の場合のみ、パターンのラベルを使用
                        if is_known == 1 and pattern_id:
                            cursor.execute("""
                                SELECT label, severity
                                FROM regex_patterns
                                WHERE id = ?
                            """, (pattern_id,))
                            pattern_row = cursor.fetchone()
                            if pattern_row:
                                classification = pattern_row['label']
                                severity = pattern_row['severity']
                                # パターンのラベルが 'unknown' の場合は 'normal' にする
                                if classification == 'unknown':
                                    classification = 'normal'
                        
                        # 未知ログ（is_known=0）の場合は常に 'unknown'
                        # （パターンが作成されても、まだ未知ログとして扱う）
                        
                        # log_entries に INSERT
                        cursor.execute("""
                            INSERT INTO log_entries
                            (ts, host, component, raw_line, message, pattern_id, is_known, classification, severity)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            parsed['ts'],
                            parsed['host'],
                            parsed['component'],
                            parsed['raw_line'],
                            parsed['message'],
                            pattern_id,
                            is_known,
                            classification,
                            severity
                        ))
                        
                        log_id = cursor.lastrowid
                        stats['parsed_lines'] += 1
                        
                        # パラメータ抽出（既知ログの場合）
                        if pattern_id and is_known:
                            # 使用する正規表現パターンを決定（regex_rule または manual_regex_rule）
                            cursor.execute("""
                                SELECT regex_rule, manual_regex_rule
                                FROM regex_patterns
                                WHERE id = ?
                            """, (pattern_id,))
                            pattern_row = cursor.fetchone()
                            if pattern_row:
                                # manual_regex_rule があればそれを使用、なければ regex_rule を使用
                                pattern_to_use = pattern_row['manual_regex_rule'] or pattern_row['regex_rule']
                                if pattern_to_use:
                                    self._extract_and_save_params(cursor, log_id, pattern_to_use, parsed['message'])
                            
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
                                    anomaly_info['classification'],
                                    anomaly_info['severity'],
                                    anomaly_info['anomaly_reason'],
                                    log_id
                                ))
                                classification = anomaly_info['classification']
                        
                        # abnormal または unknown の場合はアラートを生成
                        if classification in ('abnormal', 'unknown'):
                            self._create_alert(cursor, log_id, classification, parsed)
                        
                    except Exception as e:
                        stats['errors'] += 1
                        if verbose:
                            print(f"Error processing line {line_num}: {e}", file=sys.stderr)
                        continue
                    
                    # 定期的にコミット（パフォーマンス向上）
                    if line_num % 1000 == 0:
                        conn.commit()
            
            # 最終コミット
            conn.commit()
            
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            sys.exit(1)
        
        # 統計を表示
        print(f"Total lines: {stats['total_lines']}")
        print(f"Parsed lines: {stats['parsed_lines']}")
        print(f"New patterns: {stats['new_patterns']}")
        print(f"Existing patterns: {stats['existing_patterns']}")
        print(f"Errors: {stats['errors']}")
    
    def _find_or_create_pattern(self, cursor, regex_rule: str, sample_message: str, verbose: bool) -> tuple[Optional[int], bool]:
        """
        自動生成パターンを検索または作成（regex_rule のみをチェック）
        """
        return self._get_or_create_pattern(cursor, regex_rule, sample_message, verbose)
    
    def _check_manual_patterns(self, cursor, message: str) -> Optional[int]:
        """
        手動パターン（manual_regex_rule）をチェック
        元のメッセージに対して直接マッチング
        
        Args:
            cursor: データベースカーソル
            message: ログメッセージ
            
        Returns:
            マッチしたパターンID。マッチしない場合はNone
        """
        import re
        
        # すべての手動パターンを取得
        cursor.execute("""
            SELECT id, manual_regex_rule
            FROM regex_patterns
            WHERE manual_regex_rule IS NOT NULL
        """)
        
        for row in cursor.fetchall():
            try:
                pattern = re.compile(row['manual_regex_rule'])
                if pattern.search(message):  # search を使用（部分マッチ）
                    return row['id']
            except re.error:
                # 無効な正規表現はスキップ
                continue
        
        return None
    
    def _get_or_create_pattern(self, cursor, regex_rule: str, sample_message: str, verbose: bool) -> tuple[Optional[int], bool]:
        """
        パターンを取得または作成（自動生成パターン用）
        
        Args:
            cursor: データベースカーソル
            regex_rule: 正規表現パターン（自動生成）
            sample_message: サンプルメッセージ
            verbose: 詳細出力するかどうか
            
        Returns:
            (pattern_id, is_new_pattern) のタプル
            - pattern_id: パターンID（Noneの場合はエラー）
            - is_new_pattern: 新規作成された場合True
        """
        # 既存パターンを検索（regex_rule または manual_regex_rule の両方をチェック）
        cursor.execute("""
            SELECT id, total_count
            FROM regex_patterns
            WHERE regex_rule = ? OR manual_regex_rule = ?
        """, (regex_rule, regex_rule))
        
        row = cursor.fetchone()
        now = datetime.now()
        
        if row:
            # 既存パターン: カウントと最終観測時刻を更新
            pattern_id = row['id']
            new_count = row['total_count'] + 1
            cursor.execute("""
                UPDATE regex_patterns
                SET last_seen_at = ?,
                    total_count = ?,
                    updated_at = ?
                WHERE id = ?
            """, (now, new_count, now, pattern_id))
            return (pattern_id, False)
        
        # 新規パターン: 作成（自動生成なので regex_rule に格納、manual_regex_rule は NULL）
        # デフォルトは 'normal'（見たことがないログは後で 'unknown' に変更可能）
        cursor.execute("""
            INSERT INTO regex_patterns
            (regex_rule, manual_regex_rule, sample_message, label, severity, first_seen_at, last_seen_at, total_count)
            VALUES (?, NULL, ?, 'normal', NULL, ?, ?, 1)
        """, (regex_rule, sample_message, now, now))
        
        pattern_id = cursor.lastrowid
        if verbose:
            print(f"New pattern created: ID={pattern_id}, regex={regex_rule[:50]}...", file=sys.stderr)
        
        return (pattern_id, True)
    
    def _extract_and_save_params(self, cursor, log_id: int, regex_rule: str, message: str):
        """
        パラメータを抽出してlog_paramsテーブルに保存
        
        Args:
            cursor: データベースカーソル
            log_id: ログエントリのID
            regex_rule: 正規表現パターン
            message: ログメッセージ
        """
        params = self.param_extractor.extract_params(regex_rule, message)
        
        if not params:
            return
        
        for param_name, param_data in params.items():
            cursor.execute("""
                INSERT INTO log_params
                (log_id, param_name, param_value_num, param_value_text)
                VALUES (?, ?, ?, ?)
            """, (log_id, param_name, param_data['num'], param_data['text']))
    
    def _create_alert(self, cursor, log_id: int, alert_type: str, parsed: Dict):
        """
        アラートレコードを作成
        
        Args:
            cursor: データベースカーソル
            log_id: ログエントリのID
            alert_type: アラートタイプ（'abnormal' または 'unknown'）
            parsed: パース済みログ情報
        """
        cursor.execute("""
            INSERT INTO alerts
            (log_id, alert_type, channel, status)
            VALUES (?, ?, 'slack', 'pending')
        """, (log_id, alert_type))


def main():
    """コマンドラインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest log file into database')
    parser.add_argument('file_path', help='Path to log file')
    parser.add_argument('--db', default='db/monitor.db', help='Database path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    db = Database(args.db)
    ingester = LogIngester(db)
    
    try:
        ingester.ingest_file(args.file_path, verbose=args.verbose)
    finally:
        db.close()


if __name__ == '__main__':
    main()

