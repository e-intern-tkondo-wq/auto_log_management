"""
パラメータ抽出: 正規表現パターンからnamed capture groupを抽出
"""
import re
from typing import Dict, Optional


class ParamExtractor:
    """ログメッセージからパラメータを抽出するクラス"""
    
    def extract_params(self, regex_rule: str, message: str) -> Dict[str, any]:
        """
        正規表現パターンとメッセージからパラメータを抽出
        
        Args:
            regex_rule: 正規表現パターン（abstract_message()の出力）
            message: 元のログメッセージ
            
        Returns:
            パラメータ名 -> 値の辞書。パラメータがない場合は空辞書
        """
        params = {}
        
        try:
            # 正規表現をコンパイル
            pattern = re.compile(regex_rule)
            # searchを使用（部分マッチを許可）- メッセージの後ろに追加テキストがある場合に対応
            match = pattern.search(message)
            
            if match:
                # named capture groupを取得
                groups = match.groupdict()
                
                for param_name, param_value in groups.items():
                    if param_value is not None:
                        # 数値に変換可能かチェック
                        param_value_num = None
                        param_value_text = str(param_value)
                        
                        try:
                            # 数値として解釈を試みる
                            if isinstance(param_value, (int, float)):
                                param_value_num = float(param_value)
                            else:
                                # 文字列から数値を抽出（例: "16M" -> 16, "85.5" -> 85.5）
                                # 先頭の数値部分を抽出
                                num_match = re.match(r'^([+-]?\d+\.?\d*)', str(param_value))
                                if num_match:
                                    param_value_num = float(num_match.group(1))
                        except (ValueError, TypeError):
                            pass
                        
                        params[param_name] = {
                            'num': param_value_num,
                            'text': param_value_text
                        }
        except re.error:
            # 無効な正規表現の場合は空辞書を返す
            pass
        
        return params
    
    def extract_params_from_named_groups(self, regex_rule: str, message: str) -> Dict[str, any]:
        """
        正規表現パターンにnamed capture groupが含まれている場合にパラメータを抽出
        
        注意: abstract_message()で生成されたパターンには通常named capture groupは含まれないため、
        このメソッドは事前に登録されたパターン（手動でnamed capture groupを含む）に対して使用する
        
        Args:
            regex_rule: 正規表現パターン（named capture groupを含む可能性がある）
            message: 元のログメッセージ
            
        Returns:
            パラメータ名 -> 値の辞書
        """
        return self.extract_params(regex_rule, message)

