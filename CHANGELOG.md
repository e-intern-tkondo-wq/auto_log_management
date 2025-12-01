# 変更履歴

## 2025-11-30: 既知フラグ、パラメータ抽出、手動マッピング機能の実装

### 追加機能

1. **既知判定フラグ (`is_known`)**
   - `log_entries` テーブルに `is_known` カラムを追加
   - 既知パターンにマッチしたログは自動的に `is_known=1` に設定
   - 新規パターンの場合は `is_known=0` に設定

2. **パラメータ抽出機能**
   - `log_params` テーブルを追加
   - `ParamExtractor` クラスを実装
   - 正規表現パターンから named capture group を抽出してパラメータを保存
   - 数値パラメータとテキストパラメータの両方をサポート

3. **手動マッピングフラグ (`is_manual_mapped`)**
   - `log_entries` テーブルに `is_manual_mapped` カラムを追加
   - 未知ログを既知パターンに手動で紐付ける機能を実装
   - `cli_tools.py map-log` コマンドを追加

4. **異常判定ルールテーブル (`pattern_rules`)**
   - `pattern_rules` テーブルを追加
   - パターンごとの異常判定ルールを定義可能
   - インジェスト時に既知ログに対して自動的に異常判定を実行

### データベーススキーマ変更

#### `log_entries` テーブル
- `is_known` (INTEGER DEFAULT 0) - 既知判定フラグ
- `is_manual_mapped` (INTEGER DEFAULT 0) - 手動マッピングフラグ

#### 新規テーブル: `log_params`
- `id` (INTEGER PK)
- `log_id` (INTEGER FK → log_entries.id)
- `param_name` (TEXT NOT NULL)
- `param_value_num` (REAL)
- `param_value_text` (TEXT)
- `created_at` (DATETIME)

#### 新規テーブル: `pattern_rules`
- `id` (INTEGER PK)
- `pattern_id` (INTEGER FK → regex_patterns.id)
- `rule_type` (TEXT NOT NULL)
- `field_name` (TEXT)
- `op` (TEXT NOT NULL)
- `threshold_value1`, `threshold_value2` (REAL)
- `severity_if_match` (TEXT NOT NULL)
- `is_abnormal_if_match` (INTEGER DEFAULT 1)
- `message` (TEXT)
- `is_active` (INTEGER DEFAULT 1)
- `created_at`, `updated_at` (DATETIME)

### 新規ファイル

- `src/param_extractor.py` - パラメータ抽出機能

### 更新されたファイル

- `src/database.py` - スキーマ拡張
- `src/ingest.py` - 既知フラグ設定、パラメータ抽出、異常判定の自動実行
- `src/cli_tools.py` - `map-log` コマンド追加

### 使用方法

#### 手動マッピング
```bash
# 未知ログを既知パターンに紐付ける
python src/cli_tools.py map-log <log_id> <pattern_id>
```

#### パラメータ抽出
- インジェスト時に自動的に実行されます
- 既知ログ（`is_known=1`）の場合、パラメータが抽出されて `log_params` テーブルに保存されます

#### 異常判定
- インジェスト時に既知ログに対して自動的に実行されます
- `pattern_rules` テーブルにルールを定義することで、パラメータ値に基づく異常判定が可能です

