#!/usr/bin/env python3
"""
完全一致のユニークなログエントリをデータベースに格納するスクリプト

172.20.224.101.log-20250714 から 172.20.224.116.log-20250714 まで
順番に処理し、完全一致するログエントリをユニークに格納し、出現回数をカウントする
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import Database


def store_unique_logs(log_dir: str = "log_flower/bootlog", db_path: str = "db/monitor.db"):
    """
    ログファイルから完全一致のユニークなログエントリをデータベースに格納
    
    Args:
        log_dir: ログファイルが格納されているディレクトリ
        db_path: データベースファイルのパス
    """
    db = Database(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # ログファイルのパス
    log_dir_path = Path(project_root) / log_dir
    
    # 101から116までのファイルを順番に処理
    file_numbers = range(101, 117)
    total_files = len(file_numbers)
    
    print(f"処理を開始します: {total_files}個のファイルを処理します")
    print("-" * 80)
    
    for idx, file_num in enumerate(file_numbers, 1):
        filename = f"172.20.224.{file_num}.log-20250714"
        file_path = log_dir_path / filename
        
        if not file_path.exists():
            print(f"[{idx}/{total_files}] ファイルが見つかりません: {filename}")
            continue
        
        print(f"[{idx}/{total_files}] 処理中: {filename}")
        
        # ファイルを読み込んで処理
        processed_count = 0
        new_count = 0
        updated_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    raw_line = line.rstrip('\n\r')
                    
                    # 空行はスキップ
                    if not raw_line.strip():
                        continue
                    
                    processed_count += 1
                    
                    # 既存のレコードを検索
                    cursor.execute(
                        "SELECT id, count, first_seen_at FROM unique_log_entries WHERE raw_line = ?",
                        (raw_line,)
                    )
                    existing = cursor.fetchone()
                    
                    now = datetime.now()
                    
                    if existing:
                        # 既存レコードを更新（カウントを増やし、last_seen_atとlast_seen_fileを更新）
                        new_count_value = existing['count'] + 1
                        cursor.execute(
                            """UPDATE unique_log_entries 
                               SET count = ?, 
                                   last_seen_at = ?, 
                                   last_seen_file = ?,
                                   updated_at = ?
                               WHERE id = ?""",
                            (new_count_value, now, filename, now, existing['id'])
                        )
                        updated_count += 1
                    else:
                        # 新規レコードを挿入
                        cursor.execute(
                            """INSERT INTO unique_log_entries 
                               (raw_line, count, first_seen_at, last_seen_at, first_seen_file, last_seen_file)
                               VALUES (?, 1, ?, ?, ?, ?)""",
                            (raw_line, now, now, filename, filename)
                        )
                        new_count += 1
                    
                    # 1000行ごとにコミット（パフォーマンス向上）
                    if processed_count % 1000 == 0:
                        conn.commit()
            
            # 最後にコミット
            conn.commit()
            
            print(f"  ✓ 処理完了: 総行数={processed_count}, 新規={new_count}, 更新={updated_count}")
            
        except Exception as e:
            print(f"  ✗ エラーが発生しました: {e}")
            conn.rollback()
            continue
    
    # 最終統計を表示
    cursor.execute("SELECT COUNT(*) as total, SUM(count) as total_count FROM unique_log_entries")
    stats = cursor.fetchone()
    
    print("-" * 80)
    print(f"処理完了!")
    print(f"ユニークなログエントリ数: {stats['total']}")
    print(f"総出現回数: {stats['total_count']}")
    
    db.close()


if __name__ == "__main__":
    store_unique_logs()

