# 手動パターン機能の実装
> このファイルで行うこと: 手動パターン機能の背景・DB構造・動作を整理します。

## 概要

手動で作成した正規表現パターンと自動生成されたパターンを分離し、両方を参照して既知/未知を判断する機能を実装しました。

## データベーススキーマの変更

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

## 使用例

### 手動パターンの追加

```bash
# named capture groupを含む手動パターンを追加
python src/cli_tools.py add-pattern \
  "\[\s+(?P<timestamp>\d+\.\d+)\]\s+gran_size:\s+(?P<gran_size>\d+)(?P<gran_unit>[MG])" \
  "[    0.005840]  gran_size: 16M" \
  --label normal \
  --severity info \
  --note "GPU gran_size pattern with named capture groups"
```

### 未知ログからパターンを生成

```bash
# 未知ログから自動的にパターンを生成して追加
python src/cli_tools.py add-pattern-from-log 123 \
  --label normal \
  --severity info \
  --note "Pattern generated from unknown log"
```

## メリット

1. **柔軟性**: 手動でパターンを作成できるため、named capture group を含むパターンでパラメータ抽出が可能
2. **拡張性**: 自動生成パターンと手動パターンを分離することで、管理が容易
3. **既知/未知判定**: 両方のパターンを参照することで、より正確な既知/未知判定が可能

## 注意事項

- 手動パターンは元のメッセージに対して直接マッチングするため、`abstract_message()` で生成されるパターンとは異なる形式でもマッチ可能
- 手動パターンに named capture group を含めることで、パラメータ抽出が可能
- `regex_rule` と `manual_regex_rule` の両方が NULL になることはない（CHECK制約）

