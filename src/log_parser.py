"""
ログパーサー: syslog形式のログファイルを解析
bootlog形式のテキストログ1行を
日時（datetime）、ホスト名/IP、コンポーネント名、メッセージ本体に分解して辞書にしてくれる「ログパーサー」
"""
import re
from datetime import datetime
from typing import Optional, Dict


class LogParser:
    """syslog形式のログを解析するクラス"""
    
    # syslog形式の正規表現パターン
    # 例: "Jul 14 11:20:17 172.20.224.102 kernel: [    0.005840] message..."
    SYSLOG_PATTERN = re.compile(
        r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'  # 日時部分
        r'(\S+)\s+'                                    # ホスト名/IP
        r'(\S+?):\s+'                                  # コンポーネント（プロセス名）
        r'(.*)$'                                       # メッセージ本体
    )
    
    def __init__(self, default_year: Optional[int] = None):
        """
        Args:
            default_year: ログに年が含まれない場合のデフォルト年
                         指定しない場合は現在の年を使用
        年末とかの場合は要検討
        """
        if default_year is None:
            default_year = datetime.now().year
        self.default_year = default_year
    
    def parse_line(self, line: str) -> Dict[str, any]:
        """
        1行のログを解析して構造化データに変換
        
        Args:
            line: ログの1行
            
        Returns:
            解析結果の辞書
            {
                'ts': datetime,
                'host': str or None,
                'component': str or None,
                'message': str,
                'raw_line': str
            }
        """
        line = line.strip()
        if not line:
            return {
                'ts': datetime.now(),
                'host': None,
                'component': None,
                'message': line,
                'raw_line': line
            }
        
        match = self.SYSLOG_PATTERN.match(line)
        if not match:
            # パターンにマッチしない場合は、可能な限り解析を試みる
            return {
                'ts': datetime.now(),
                'host': None,
                'component': None,
                'message': line,
                'raw_line': line
            }
        
        ts_str, host, component, message = match.groups()
        
        # 日時をパース（年を補完）
        ts = self._parse_timestamp(ts_str)
        if ts is None:
            ts = datetime.now()
        
        return {
            'ts': ts,
            'host': host,
            'component': component,
            'message': message,
            'raw_line': line
        }
    
    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """
        syslog形式のタイムスタンプをdatetimeに変換
        
        Args:
            ts_str: "Jul 14 11:20:17" 形式の文字列
            
        Returns:
            datetimeオブジェクト。パースに失敗した場合はNone
        """
        # 月名のマッピング
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
            'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        try:
            # "Jul 14 11:20:17" をパース
            parts = ts_str.split()
            if len(parts) != 3:
                return None
            
            month_name = parts[0]
            day = int(parts[1])
            time_str = parts[2]
            
            month = month_map.get(month_name)
            if month is None:
                return None
            
            # 時刻をパース
            time_parts = time_str.split(':')
            if len(time_parts) != 3:
                return None
            
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            second = int(time_parts[2])
            
            return datetime(
                year=self.default_year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second
            )
        except (ValueError, IndexError):
            return None
