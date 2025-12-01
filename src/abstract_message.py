"""
abstract_message: ログメッセージを正規表現パターンに変換
この設定が全体のファイルにおいて正規表現のルールを決定する重要な部分
"""
import re


def abstract_message(message: str) -> str:
    """
    ログメッセージを構造だけを残した正規表現パターンに変換
    
    変換ルール:
    - 0x から始まる16進数 → 0x[0-9A-Fa-f]+
    - それ以外の10進数 → \d+
    - 連続する空白類（スペース/タブなど） → \s+
    - その他の文字は re.escape() でリテラルにする
    
    Args:
        message: 元のログメッセージ
        
    Returns:
        正規表現パターン文字列
    """
    # 16進数を先に処理して、エスケープ対象から除外
    parts = []
    last_end = 0
    
    # 0xから始まる16進数をまず検索
    # これをやらないと0xが\d+xのようになってしまう
    for match in re.finditer(r'0x[0-9A-Fa-f]+', message, flags=re.IGNORECASE):
        # マッチ前の部分を処理
        if match.start() > last_end:
            part = message[last_end:match.start()]
            # 意図しない空白などのエスケープを防ぐためにプレースホルダーを使って置換
            part = re.sub(r'\s+', '___WS___', part)
            # 意図しない数字のエスケープを防ぐためにプレースホルダーを使って置換
            part = re.sub(r'\d+', '___NUM___', part)
            # エスケープコマンドを使って特殊文字をエスケープ
            part = re.escape(part)
            # プレースホルダーを正規表現パターンに戻す
            part = part.replace('___WS___', r'\s+').replace('___NUM___', r'\d+')
            # エスケープされたパターンを正規表現パターンに戻す
            part = part.replace(r'\\d\\+', r'\d+').replace(r'\\s\\+', r'\s+')
            parts.append(part)
        
        # 16進数部分はそのまま正規表現パターンとして追加
        parts.append(r'0x[0-9A-Fa-f]+')
        last_end = match.end()
    
    # 残りの部分を処理
    if last_end < len(message):
        part = message[last_end:]
        part = re.sub(r'\s+', '___WS___', part)
        part = re.sub(r'\d+', '___NUM___', part)
        part = re.escape(part)
        part = part.replace('___WS___', r'\s+').replace('___NUM___', r'\d+')
        part = part.replace(r'\\d\\+', r'\d+').replace(r'\\s\\+', r'\s+')
        parts.append(part)
    
    return ''.join(parts)


def validate_pattern(pattern: str, original_message: str) -> bool:
    """
    生成されたパターンが元のメッセージにマッチするか検証
    
    Args:
        pattern: 生成された正規表現パターン
        original_message: 元のメッセージ
        
    Returns:
        マッチする場合True
    """
    try:
        regex = re.compile(pattern)
        return bool(regex.fullmatch(original_message))
    except re.error:
        return False

