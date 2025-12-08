# 手動パターン追加ガイド
> このファイルで行うこと: 手動パターン登録とnamed capture活用の手順を解説します。

## 概要

手動で作成した正規表現パターンと自動生成されたパターンを分離し、両方を参照して既知/未知を判断する機能です。

## データベーススキーマ

### `regex_patterns` テーブル

- **`regex_rule`**: 自動生成された正規表現パターン（`abstract_message()` の出力）
- **`manual_regex_rule`**: 手動で作成した正規表現パターン
- **制約**: `regex_rule` と `manual_regex_rule` のどちらか一方のみが NULL でない（CHECK制約）

## 動作ロジック

### 1. パターンの追加

#### 自動生成パターン
- `abstract_message()` で生成されたパターンは `regex_rule` に格納
- `manual_regex_rule` は NULL

#### 手動パターン
- `add-pattern` コマンドで追加されたパターンは `manual_regex_rule` に格納
- `regex_rule` は NULL

### 2. 既知/未知判定

新しいログエントリが来た時に、以下の順序で既知/未知を判断します：

1. **自動生成パターンのチェック**
   - `abstract_message()` でパターンを生成
   - `regex_patterns.regex_rule` と比較
   - マッチした場合 → 既知ログ

2. **手動パターンのチェック**
   - 元のメッセージに対して `manual_regex_rule` を直接マッチング
   - マッチした場合 → 既知ログ

3. **どちらにもマッチしない場合**
   - 新規パターンとして `regex_rule` に追加
   - 未知ログとして分類

### 3. パラメータ抽出

既知ログの場合、パラメータ抽出に使用するパターンは：
- `manual_regex_rule` が存在する場合はそれを使用
- 存在しない場合は `regex_rule` を使用

これにより、手動パターンに named capture group を含めることで、パラメータ抽出が可能になります。

---

## エラーの原因

以前発生していた `NOT NULL constraint failed: regex_patterns.regex_rule` エラーは、**既存のデータベースで `regex_rule` カラムに `NOT NULL` 制約が残っていた**ことが原因でした。

### 解決方法

`src/database.py` の `_init_database()` メソッドに自動マイグレーション機能を追加しました。データベースを開く際に、必要に応じて自動的にスキーマが更新されます。

## 手動パターンの追加方法

### 1. 基本的な追加コマンド

```bash
python src/cli_tools.py add-pattern \
  "<正規表現パターン>" \
  "<サンプルメッセージ>" \
  --label <normal|abnormal|unknown|ignore> \
  --severity <info|warning|critical|unknown> \
  --component <kernel|nvidia|systemd等> \
  --note "<説明>"
```

### 2. 16進数MACアドレスのパターン例

#### Kernel command line の BOOTIF

```bash
python src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+Kernel\s+command\s+line:.*?BOOTIF=(?P<mac>[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})" \
  "[    6.295533] Kernel command line: BOOT_IMAGE=(tftp)/category/vmlinuz.dgx-h200 nouveau.modeset=0 nvme_core.multipath=n console=tty0 rw BOOTIF=01-c4-70-bd-d9-66-e1 ip=172.20.224.112:172.20.224.14:0xac14e001:0xffffff00" \
  --label normal \
  --severity info \
  --component kernel \
  --note "Kernel command line with MAC address (BOOTIF)"
```

#### ixgbe のMACアドレス

```bash
python src/cli_tools.py add-pattern \
  "\[\s*\d+\.\d+\]\s+ixgbe\s+[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]:\s+(?P<mac>[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5})" \
  "[   26.570212] ixgbe 0000:0b:00.0: 5c:ff:35:fe:22:6d" \
  --label normal \
  --severity info \
  --note "ixgbe MAC address pattern"
```

### 3. 正規表現パターンの書き方のコツ

#### 16進数の表現

- **16進数2桁**: `[0-9A-Fa-f]{2}`
- **16進数4桁**: `[0-9A-Fa-f]{4}`
- **16進数可変長**: `[0-9A-Fa-f]+`

#### MACアドレスの表現

- **ハイフン区切り（例: 01-c4-70-bd-d9-66-e1）**:
  ```regex
  [0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5}
  ```

- **コロン区切り（例: 5c:ff:35:fe:22:6d）**:
  ```regex
  [0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}
  ```

#### Named Capture Group の使用

パラメータ抽出を行う場合は、`(?P<name>pattern)` 形式を使用：

```regex
(?P<mac>[0-9A-Fa-f]{2}(?:-[0-9A-Fa-f]{2}){5})
```

これにより、`mac` という名前でMACアドレスを抽出できます。

### 4. パターンの確認

追加したパターンが正しく動作するか確認：

```bash
# 手動パターンの一覧
sqlite3 db/monitor.db "SELECT id, manual_regex_rule, sample_message, label FROM regex_patterns WHERE manual_regex_rule IS NOT NULL ORDER BY id DESC;"

# 特定のパターンのテスト
python3 -c "
from src.database import Database
from src.ingest import LogIngester

db = Database('db/monitor.db')
ingester = LogIngester(db)

test_log = 'Jul 14 11:20:04 172.20.224.112 kernel: [    6.295533] Kernel command line: ...'
parsed = ingester.parser.parse_line(test_log)
conn = db.get_connection()
cursor = conn.cursor()
manual_id = ingester._check_manual_patterns(cursor, parsed['message'])

if manual_id:
    print(f'✅ Matched pattern ID: {manual_id}')
else:
    print('❌ No match')
"
```

### 5. 未知ログからパターンを生成

未知ログから自動的にパターンを生成して追加：

```bash
python src/cli_tools.py add-pattern-from-log <log_id> \
  --label normal \
  --severity info \
  --note "Pattern generated from unknown log"
```

## ベストプラクティス

1. **柔軟なパターン**: 完全一致ではなく、重要な部分だけをマッチさせる
   - ❌ 悪い例: すべての文字をエスケープして完全一致を要求
   - ✅ 良い例: `.*?` を使って柔軟にマッチ

2. **Named Capture Group の活用**: パラメータ抽出が必要な場合は必ず使用
   - 例: `(?P<mac>...)`, `(?P<timestamp>...)`, `(?P<temp>...)`

3. **サンプルメッセージ**: 実際のログメッセージを使用
   - パターンの意図が明確になる
   - デバッグ時に役立つ

4. **適切なラベル付け**: 
   - `normal`: 正常なログ
   - `abnormal`: 異常・エラーログ
   - `unknown`: まだ判断していない
   - `ignore`: ノイズ・監視不要

5. **コンポーネント指定**: 可能な限り `--component` を指定
   - パターンの適用範囲が明確になる

## トラブルシューティング

### エラー: `NOT NULL constraint failed`

- **原因**: データベースのマイグレーションが未完了
- **解決**: `Database` クラスを初期化すると自動的にマイグレーションが実行されます

### パターンがマッチしない

- 正規表現のエスケープを確認（`\s`, `\d`, `\.` など）
- `search()` を使用しているため、部分マッチでも動作するはず
- テスト用のPythonスクリプトでパターンを確認

### パラメータが抽出されない

- Named capture group `(?P<name>...)` が正しく記述されているか確認
- パターンがメッセージに完全にマッチしているか確認

