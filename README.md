# ログ監視システム（パターン学習型）
> このファイルで行うこと: プロジェクト全体の概要・構成・利用方法を説明します。

GPUサーバなどのログ（syslog形式）を対象に、パターン学習型の死活・異常検知システムを構築します。

## システム概要

- 各ログ行を `abstract_message()` で正規表現パターンに変換
- パターン単位で `normal` / `abnormal` / `unknown` / `ignore` をラベル付け
  - **`normal`**: 普通のログ（デフォルト）
  - **`unknown`**: 見たことがないログ
  - **`abnormal`**: 見たことがあるが危険なログ
- `abnormal` / `unknown` に分類されたログを Slack に通知
- 既知ログの異常検知（パラメータ抽出とルールベース判定）
- 未知ログの手動マッピング機能

## アーキテクチャ

```
ログファイル
    ↓
[log_parser.py] syslog形式のパース
    ↓
[abstract_message.py] 正規表現パターン生成
    ↓
[ingest.py] パターンマッチング・既知/未知判定
    ↓
[param_extractor.py] パラメータ抽出（既知ログのみ）
    ↓
[anomaly_detector.py] 異常判定（既知ログのみ）
    ↓
[slack_notifier.py] 通知送信
    ↓
SQLite DB (database.py)
```

## コードファイル一覧と機能

### コア機能

#### `src/abstract_message.py`
**機能**: ログメッセージを正規表現パターンに変換

- **`abstract_message(message: str) -> str`**
  - ログメッセージを構造だけを残した正規表現パターンに変換
  - 変換ルール:
    - `0x` から始まる16進数 → `0x[0-9A-Fa-f]+`
    - それ以外の10進数 → `\d+`
    - 連続する空白類（スペース/タブなど） → `\s+`
    - その他の文字は `re.escape()` でリテラルにする
  - 同じ構造のログが同じパターンに集約される

- **`validate_pattern(pattern: str, original_message: str) -> bool`**
  - 生成されたパターンが元のメッセージにマッチするか検証

**使用例**:
```python
from src.abstract_message import abstract_message
pattern = abstract_message("[    0.005840]  gran_size: 16M")
# 結果: "\[\s+\d+\.\d+\]\s+gran_size:\s+\d+M"
```

---

#### `src/log_parser.py`
**機能**: syslog形式のログファイルを解析

- **`LogParser` クラス**
  - syslog形式のログ行を構造化データに変換

- **`parse_line(line: str) -> Dict`**
  - 1行のログを解析して以下の項目を抽出:
    - `ts`: 日時（年を補完してDATETIMEに変換）
    - `host`: ホスト名/IP
    - `component`: コンポーネント名（例: "kernel"）
    - `message`: メッセージ本体
    - `raw_line`: 元の1行テキスト
  - パースできない場合はフォールバック処理

**使用例**:
```python
from src.log_parser import LogParser
parser = LogParser()
parsed = parser.parse_line("Jul 14 11:20:17 172.20.224.102 kernel: [    0.005840] message")
# 結果: {'ts': datetime(...), 'host': '172.20.224.102', 'component': 'kernel', ...}
```

---

#### `src/database.py`
**機能**: SQLiteデータベースの管理とスキーマ定義

- **`Database` クラス**
  - SQLiteデータベースの初期化と接続管理

- **テーブル定義**:
  - **`regex_patterns`**: パターンマスタ
    - `id`, `regex_rule`, `sample_message`, `label`, `severity`, `note`
    - `first_seen_at`, `last_seen_at`, `total_count`
  - **`log_entries`**: ログ本体
    - `id`, `ts`, `host`, `component`, `raw_line`, `message`
    - `pattern_id`, `is_known`, `is_manual_mapped`
    - `classification`, `severity`, `anomaly_reason`
  - **`log_params`**: パラメータ抽出結果
    - `id`, `log_id`, `param_name`, `param_value_num`, `param_value_text`
  - **`pattern_rules`**: 異常判定ルール
    - `id`, `pattern_id`, `rule_type`, `field_name`, `op`
    - `threshold_value1`, `threshold_value2`, `severity_if_match`
  - **`alerts`**: 通知履歴
    - `id`, `log_id`, `alert_type`, `channel`, `status`, `message`, `sent_at`
  - **`ai_analyses`**: AI解析結果（将来拡張用）
    - `id`, `log_id`, `prompt`, `response`, `model_name`

**使用例**:
```python
from src.database import Database
db = Database("db/monitor.db")
conn = db.get_connection()
# データベース操作...
db.close()
```

---

#### `src/ingest.py`
**機能**: ログファイルの取り込み処理（メイン処理フロー）

- **`LogIngester` クラス**
  - ログファイルを読み込んでデータベースに保存

- **`ingest_file(file_path: str, verbose: bool = False)`**
  - ログファイルを1行ずつ読み込み
  - 各ログ行に対して以下を実行:
    1. `LogParser` でパース
    2. `abstract_message()` でパターン生成
    3. `regex_patterns` テーブルから既存パターンを検索
    4. 既存パターンが見つかった場合:
       - `is_known = 1` を設定
       - `pattern_id` を設定
       - パラメータ抽出を実行（`ParamExtractor`）
       - 異常判定を実行（`AnomalyDetector`）
    5. 新規パターンの場合:
       - `regex_patterns` に新規登録
       - `is_known = 0` を設定
    6. `log_entries` にINSERT
    7. `classification` が `abnormal` または `unknown` の場合、アラートを生成

- **`_get_or_create_pattern()`**
  - パターンを取得または作成
  - 既存パターンの場合は `total_count` と `last_seen_at` を更新

- **`_extract_and_save_params()`**
  - パラメータを抽出して `log_params` テーブルに保存

- **`_create_alert()`**
  - アラートレコードを `alerts` テーブルに作成

**使用例**:
```bash
python src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714 --db db/monitor.db -v
```

---

#### `src/param_extractor.py`
**機能**: ログメッセージからパラメータを抽出

- **`ParamExtractor` クラス**
  - 正規表現パターンから named capture group を抽出

- **`extract_params(regex_rule: str, message: str) -> Dict`**
  - 正規表現パターンとメッセージからパラメータを抽出
  - named capture group がある場合、パラメータ名と値を取得
  - 数値に変換可能な場合は数値として、そうでない場合はテキストとして保存
  - 返り値: `{param_name: {'num': value_num, 'text': value_text}, ...}`

**使用例**:
```python
from src.param_extractor import ParamExtractor
extractor = ParamExtractor()
# パターンに (?P<temp>\d+) が含まれている場合
params = extractor.extract_params(pattern, message)
# 結果: {'temp': {'num': 85.5, 'text': '85.5'}}
```

**注意**: 現在の `abstract_message()` で生成されるパターンには named capture group は含まれません。パラメータ抽出を利用する場合は、事前に登録されたパターン（手動で named capture group を含む）が必要です。

---

#### `src/anomaly_detector.py`
**機能**: ルールベースの異常検知

- **`AnomalyDetector` クラス**
  - 既知ログに対して異常判定を実行

- **`check_anomaly(log_id: int, pattern_id: int) -> Optional[Dict]`**
  - ログエントリに対して異常判定を実行
  - `pattern_rules` テーブルから該当パターンのルールを取得
  - ルールタイプに応じて評価:
    - **`threshold`**: パラメータ値のしきい値チェック
      - `op`: `>`, `<`, `>=`, `<=`, `==`, `!=`, `between`, `not_between`
    - **`contains`**: メッセージまたはパラメータに特定の文字列が含まれるか
    - **`regex`**: 正規表現マッチング
  - 異常が検知された場合、以下の情報を返す:
    ```python
    {
        'is_abnormal': True,
        'classification': 'abnormal',
        'severity': 'critical',
        'anomaly_reason': 'GPU temp > 85'
    }
    ```

- **`_evaluate_rule()`**
  - 個別のルールを評価

**使用例**:
```python
from src.anomaly_detector import AnomalyDetector
detector = AnomalyDetector(db)
anomaly_info = detector.check_anomaly(log_id, pattern_id)
if anomaly_info:
    # 異常が検知された
    print(f"Anomaly: {anomaly_info['anomaly_reason']}")
```

**注意**: `pattern_rules` テーブルにルールを定義する必要があります。

---

#### `src/slack_notifier.py`
**機能**: Slack通知の送信

- **`SlackNotifier` クラス**
  - 保留中のアラートをSlackに送信

- **`send_alert(log_id: int, alert_type: str, log_entry: dict) -> bool`**
  - アラートをSlackに送信
  - Slack Incoming Webhook を使用
  - 送信成功時: `alerts.status = 'sent'`, `sent_at` を記録
  - 送信失敗時: `alerts.status = 'failed'` を記録

- **`process_pending_alerts()`**
  - 保留中（`status='pending'`）のアラートを取得して送信
  - 各アラートに対して `send_alert()` を実行

- **`_format_message()`**
  - 通知メッセージをフォーマット
  - 含まれる情報: severity, classification, host, ts, component, message, raw_line, log_id

**使用例**:
```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
python src/slack_notifier.py --db db/monitor.db
```

---

#### `src/cli_tools.py`
**機能**: コマンドラインインターフェースツール

- **`show_unknown_patterns(db_path: str, limit: int = 100)`**
  - 未知パターン（`label='unknown'`）の一覧を表示
  - `total_count` の降順でソート
  - 表示内容: ID, カウント, 最初/最後の観測時刻, 正規表現パターン, サンプルメッセージ

- **`show_stats(db_path: str)`**
  - 統計情報を表示
  - ログエントリの総数、パターン数
  - 分類別の件数（classification distribution）
  - ラベル別のパターン数（label distribution）
  - アラートステータス別の件数
  - 直近24時間の異常/未知ログ件数

- **`update_pattern_label(db_path: str, pattern_id: int, label: str, severity: str = None, note: str = None)`**
  - パターンのラベルを更新
  - 更新可能なラベル: `normal`, `abnormal`, `unknown`, `ignore`
  - 該当パターンに属する既存ログエントリの `classification` も自動更新

- **`map_unknown_log_to_pattern(db_path: str, log_id: int, pattern_id: int)`**
  - 未知ログを既知パターンに手動で紐付ける
  - `is_known = 1`, `is_manual_mapped = 1` を設定
  - パターンの `label` と `severity` をログエントリに反映

**使用例**:
```bash
# 未知パターンの表示
python src/cli_tools.py show-unknown --limit 10

# 統計情報の表示
python src/cli_tools.py stats

# パターンラベルの更新
python src/cli_tools.py update-label 1 normal --severity info --note "正常ログ"

# 未知ログを既知パターンに紐付け
python src/cli_tools.py map-log 123 45
```

---

### 補助モジュール（将来拡張用）

#### `src/pattern_matcher.py`
**機能**: パターンマッチング機能（将来拡張用）

- **`PatternMatcher` クラス**
  - ログメッセージにマッチするパターンを検索
  - コンポーネントベースのフィルタリング機能
  - パターンキャッシュ機能

**注意**: 現在は `ingest.py` で直接パターンマッチングを行っているため、このモジュールは未使用です。将来的に `component` ベースのパターン検索を実装する際に使用可能です。

---

## データベース構造

### `regex_patterns`（パターンマスタ）
- `id`: パターンID
- `regex_rule`: `abstract_message()` で生成された正規表現パターン（UNIQUE）
- `sample_message`: 最初に観測した代表メッセージ
- `label`: `unknown` | `normal` | `abnormal` | `ignore`
- `severity`: `info` | `warning` | `critical` | `unknown`
- `note`: ノート（説明など）
- `first_seen_at`, `last_seen_at`: 観測時刻
- `total_count`: このパターンに属するログ行数

### `log_entries`（ログ本体）
- `id`: ログエントリID
- `ts`: タイムスタンプ
- `host`: ホスト名/IP
- `component`: コンポーネント名（例: "kernel"）
- `raw_line`: 元のログ行全体
- `message`: メッセージ本体
- `pattern_id`: 紐づくパターンID（FK）
- `is_known`: 既知判定フラグ（0/1）
- `is_manual_mapped`: 手動マッピングフラグ（0/1）
- `classification`: `normal` | `abnormal` | `unknown` | `ignore`
- `severity`: 重要度
- `anomaly_reason`: 異常理由

### `log_params`（パラメータ抽出結果）
- `id`: パラメータID
- `log_id`: ログエントリID（FK）
- `param_name`: パラメータ名
- `param_value_num`: 数値値
- `param_value_text`: テキスト値

### `pattern_rules`（異常判定ルール）
- `id`: ルールID
- `pattern_id`: パターンID（FK）
- `rule_type`: `threshold` | `contains` | `regex`
- `field_name`: パラメータ名（オプション）
- `op`: 演算子（`>`, `<`, `==`, `between` など）
- `threshold_value1`, `threshold_value2`: しきい値
- `severity_if_match`: マッチ時の重要度
- `is_abnormal_if_match`: 異常フラグ（0/1）
- `message`: 異常理由テキスト
- `is_active`: アクティブフラグ（0/1）

### `alerts`（通知履歴）
- `id`: アラートID
- `log_id`: ログエントリID（FK）
- `alert_type`: `abnormal` | `unknown`
- `channel`: `slack`
- `status`: `pending` | `sent` | `failed`
- `message`: 送信した通知本文
- `sent_at`: 送信成功時刻

## 使用方法

### 1. ログ取り込み

```bash
python src/ingest.py <log_file_path> [--db db/monitor.db] [-v]
```

**処理内容**:
- ログファイルを読み込み
- パターン生成・マッチング
- 既知ログのパラメータ抽出・異常判定
- データベースに保存

**出力例**:
```
Total lines: 4376
Parsed lines: 4376
New patterns: 1726
Existing patterns: 2650
Errors: 0
```

### 2. 統計情報の確認

```bash
python src/cli_tools.py stats [--db db/monitor.db]
```

**表示内容**:
- ログエントリの総数
- パターン数
- 分類別の件数
- ラベル別のパターン数
- アラートステータス別の件数
- 直近24時間の異常/未知ログ件数

### 3. 未知パターンの確認

```bash
python src/cli_tools.py show-unknown [--limit 100] [--db db/monitor.db]
```

**表示内容**:
- 未知パターンの一覧（頻出順）
- 各パターンの正規表現とサンプルメッセージ

### 4. パターンラベルの更新

```bash
# 正常ログとしてマーク
python src/cli_tools.py update-label <pattern_id> normal --severity info

# 異常ログとしてマーク
python src/cli_tools.py update-label <pattern_id> abnormal --severity critical --note "GPU温度異常"
```

**効果**:
- パターンのラベルが更新される
- 該当パターンに属する既存・今後のログの `classification` が自動更新される

### 5. 未知ログの手動マッピング

```bash
python src/cli_tools.py map-log <log_id> <pattern_id> [--db db/monitor.db]
```

**効果**:
- 未知ログが既知パターンに紐付けられる
- `is_known = 1`, `is_manual_mapped = 1` が設定される
- パターンの `label` と `severity` がログエントリに反映される

### 6. Slack通知送信

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
python src/slack_notifier.py [--db db/monitor.db] [--webhook-url <url>]
```

**処理内容**:
- 保留中（`status='pending'`）のアラートを取得
- 各アラートをSlackに送信
- 送信結果を `alerts` テーブルに記録

## 設定

### データベースパス
デフォルト: `db/monitor.db`

各コマンドで `--db` オプションで指定可能。

### Slack Webhook URL
環境変数 `SLACK_WEBHOOK_URL` を設定するか、`--webhook-url` オプションで指定。

## 依存パッケージ

```bash
pip install requests
```

## 使用例

### 基本的な使用フロー

```bash
# 1. ログファイルを取り込む
python src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714

# 2. 統計情報を確認
python src/cli_tools.py stats

# 3. 未知パターンを確認（頻出順）
python src/cli_tools.py show-unknown --limit 10

# 4. パターンをラベル付け
# 正常ログとしてマーク
python src/cli_tools.py update-label 98 normal --severity info

# 異常ログとしてマーク
python src/cli_tools.py update-label 351 abnormal --severity warning --note "PCI bridge window warning"

# 5. ラベル更新後、該当ログのclassificationが自動更新される
python src/cli_tools.py stats

# 6. 未知ログを既知パターンに紐付け
python src/cli_tools.py map-log 123 45

# 7. アラートをSlackに送信（webhook URLが必要）
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
python src/slack_notifier.py
```

## 異常判定ルールの設定

`pattern_rules` テーブルにルールを追加することで、既知ログに対して異常判定を実行できます。

**例**: GPU温度が85度を超えた場合に異常とする

```sql
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, is_abnormal_if_match, message
) VALUES (
    1, 'threshold', 'temp', '>',
    85.0, 'critical', 1, 'GPU temp > 85'
);
```

**ルールタイプ**:
- `threshold`: パラメータ値のしきい値チェック
- `contains`: メッセージまたはパラメータに特定の文字列が含まれるか
- `regex`: 正規表現マッチング

## 注意事項

- `abstract_message()` は機械的にパターンを生成します
- 手書きの正規表現パターンは使用しません（パターンは自動生成）
- パターンのラベルは人間が判断して設定します
- ラベルを更新すると、そのパターンに属する既存・今後のログの `classification` が自動更新されます
- パラメータ抽出を利用する場合は、事前に登録されたパターン（named capture group を含む）が必要です
- 異常判定を利用する場合は、`pattern_rules` テーブルにルールを定義する必要があります

## テスト

大量ログのテスト:
```bash
# 複数のログファイルを結合
cat log_flower/bootlog/*.log > logs/input/big.log

# 取り込み
python src/ingest.py logs/input/big.log -v
```

## ファイル構成

```
final_creation/
├── src/
│   ├── abstract_message.py    # 正規表現パターン生成
│   ├── database.py            # データベース管理
│   ├── log_parser.py          # ログパーサー
│   ├── ingest.py              # インジェスト処理（メイン）
│   ├── param_extractor.py     # パラメータ抽出
│   ├── anomaly_detector.py    # 異常検知
│   ├── slack_notifier.py      # Slack通知
│   ├── cli_tools.py           # CLIツール
│   └── pattern_matcher.py     # パターンマッチング（将来拡張用）
├── db/
│   └── monitor.db             # SQLiteデータベース
├── log_flower/
│   └── bootlog/               # サンプルログファイル
├── README.md                  # このファイル
├── CHANGELOG.md               # 変更履歴
├── IMPLEMENTATION_STATUS.md   # 実装状況
├── PROGRESS_REPORT.md         # 進捗レポート
└── requirements.txt           # 依存パッケージ
```

## ライセンス

（プロジェクトのライセンスを記載）
