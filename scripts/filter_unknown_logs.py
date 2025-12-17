#!/usr/bin/env python3
"""
未知ログを正規表現でフィルタして表示する簡易ツール

使い方:
  python3 scripts/filter_unknown_logs.py --regex "<pattern>" --db db/monitor.db --limit 500

特徴:
- Pythonのre.searchで部分一致を確認
- マッチしたログIDとメッセージを表示
"""
import argparse
import re
import sqlite3
import sys


def filter_unknown_logs(db_path: str, regex_rule: str, limit: int = 1000000):
    try:
        pattern = re.compile(regex_rule)
    except re.error as e:
        print(f"Error: invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, message
        FROM log_entries
        WHERE classification = 'unknown'
        ORDER BY id
        LIMIT ?
        """,
        (limit,),
    )

    rows = cursor.fetchall()
    matched = 0
    for row in rows:
        m = pattern.search(row["message"])
        if m:
            matched += 1
            groups = "\t".join(m.groups()) if m.groups() else ""
            msg_head = row["message"][:160]
            print(f"{row['id']}\t{groups}\t{msg_head}")

    print(f"\nMatched {matched} of {len(rows)} checked (limit={limit})")
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Filter unknown logs by regex and list candidates for manual mapping"
    )
    parser.add_argument("--db", default="db/monitor.db", help="Database path")
    parser.add_argument("--regex", required=True, help="Regex used to search messages")
    parser.add_argument("--limit", type=int, default=100000000, help="Rows to scan (default: 200)")
    args = parser.parse_args()

    filter_unknown_logs(args.db, args.regex, args.limit)


if __name__ == "__main__":
    main()

