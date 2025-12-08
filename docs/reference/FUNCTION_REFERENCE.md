# 実行関数群リファレンス

> このファイルで行うこと: ワークフローで使用する主要な関数・コマンドをまとめます。

## カテゴリ別関数一覧

### 1. ログ取り込み

#### `src/ingest.py`
- **`LogIngester.ingest_file(file_path, verbose=False)`**
  - ログファイルを取り込んでデータベースに保存
  - パターン生成・マッチング・既知/未知判定・異常判定を自動実行
  - **使用例**: `python3 src/ingest.py log_flower/bootlog/172.20.224.102.log-20250714`

#### `src/log_parser.py`
- **`LogParser.parse_line(line)`**
  - syslog形式の1行をパース
  - 戻り値: `{'ts': datetime, 'host': str, 'component': str, 'message': str, 'raw_line': str}`

#### `src/abstract_message.py`
- **`abstract_message(message)`**
  - ログメッセージを正規表現パターンに変換
  - 戻り値: 正規表現パターン文字列

---

### 2. パターン管理

#### `src/cli_tools.py`
- **`add_pattern(db_path, regex_rule, sample_message, label='normal', severity=None, component=None, note=None, update_existing=False)`**
  - 手動で正規表現パターンを追加
  - **CLI**: `python3 src/cli_tools.py add-pattern "<正規表現>" "<サンプル>" --label normal`

- **`add_pattern_from_log(db_path, log_id, label='normal', severity=None, note=None)`**
  - 未知ログから正規表現パターンを生成して追加
  - **CLI**: `python3 src/cli_tools.py add-pattern-from-log <log_id> --label normal`

- **`update_pattern_label(db_path, pattern_id, label, severity=None, note=None)`**
  - パターンのラベルを更新（normal/abnormal/unknown/ignore）
  - **CLI**: `python3 src/cli_tools.py update-label <pattern_id> normal --severity info`

- **`map_unknown_log_to_pattern(db_path, log_id, pattern_id)`**
  - 未知ログを既知パターンに手動で紐付ける
  - **CLI**: `python3 src/cli_tools.py map-log <log_id> <pattern_id>`

- **`show_unknown_patterns(db_path, limit=100)`**
  - 未知パターンの一覧を表示
  - **CLI**: `python3 src/cli_tools.py show-unknown --limit 20`

- **`show_stats(db_path)`**
  - 統計情報を表示
  - **CLI**: `python3 src/cli_tools.py stats`

---

### 3. 異常判定

#### `src/anomaly_detector.py`
- **`AnomalyDetector.check_anomaly(log_id, pattern_id)`**
  - ログエントリに対して異常判定を実行
  - `pattern_rules` と `log_params` を参照して閾値チェック
  - 戻り値: `{'classification': 'abnormal', 'severity': str, 'anomaly_reason': str}` または `None`

- **`AnomalyDetector._evaluate_rule(rule, message, params)`**
  - 個別のルールを評価（threshold/contains/regex）

#### `src/param_extractor.py`
- **`ParamExtractor.extract_params(regex_rule, message)`**
  - 正規表現パターンから named capture group を抽出
  - 戻り値: `{param_name: {'num': float, 'text': str}, ...}`

---

### 4. 閾値ルール管理

#### `scripts/add_threshold_rule.py`
- **`add_threshold_rule(db_path, pattern_id, rule_type, field_name=None, op=None, threshold_value1=None, threshold_value2=None, severity_if_match='critical', is_abnormal_if_match=True, message=None, is_active=True)`**
  - 閾値ルールを追加
  - **CLI**: `python3 scripts/add_threshold_rule.py --pattern-id <id> --rule-type threshold --field-name temp --op '>' --threshold 80.0`

---

### 5. 通知

#### `src/slack_notifier.py`
- **`SlackNotifier.send_alert(log_id, alert_type, log_entry)`**
  - アラートをSlackに送信
  - 戻り値: `True`（成功）または `False`（失敗）

- **`SlackNotifier.process_pending_alerts()`**
  - 保留中のアラートを処理してSlackに送信
  - **CLI**: `python3 src/slack_notifier.py --db db/monitor.db`

- **`SlackNotifier._format_message(log_id, alert_type, log_entry)`**
  - 通知メッセージをフォーマット

---

### 6. データベース操作

#### `src/database.py`
- **`Database.__init__(db_path)`**
  - データベースを初期化（テーブル作成・マイグレーション）

- **`Database.get_connection()`**
  - データベース接続を取得

- **`Database.close()`**
  - データベース接続を閉じる

---

### 7. パターンマッチング

#### `src/ingest.py`
- **`LogIngester._find_or_create_pattern(cursor, regex_rule, sample_message, verbose)`**
  - パターンを検索または作成（自動生成パターン用）
  - 戻り値: `(pattern_id, is_new_pattern)`

- **`LogIngester._check_manual_patterns(cursor, message)`**
  - 手動パターンをチェック（元のメッセージに対して直接マッチング）
  - 戻り値: `pattern_id` または `None`

---

### 8. パラメータ抽出・保存

#### `src/ingest.py`
- **`LogIngester._extract_and_save_params(cursor, log_id, regex_rule, message)`**
  - パラメータを抽出して `log_params` テーブルに保存

---

### 9. アラート作成

#### `src/ingest.py`
- **`LogIngester._create_alert(cursor, log_id, alert_type, parsed)`**
  - アラートレコードを `alerts` テーブルに作成

---

## ワークフロー別関数マッピング

### フロー1: テンプレテーブルを作成
- `Database._init_database()` - テーブル作成
- `LogIngester._get_or_create_pattern()` - 自動生成パターンの作成
- `add_pattern()` - 手動パターンの追加

### フロー2: 既知/未知の判断
- `abstract_message()` - パターン生成
- `LogIngester._find_or_create_pattern()` - パターン検索
- `LogIngester._check_manual_patterns()` - 手動パターンマッチング
- `LogIngester.ingest_file()` - 既知/未知判定の実行

### フロー3: 異常判定
- `ParamExtractor.extract_params()` - パラメータ抽出
- `AnomalyDetector.check_anomaly()` - 異常判定
- `regex_patterns.label` の参照 - 異常テンプレの判定

### フロー4: 手動でテンプレ化
- `add_pattern()` - 手動パターンの追加
- `add_pattern_from_log()` - 未知ログからパターン生成
- `map_unknown_log_to_pattern()` - 既存ログの紐付け

### フロー5: LLMによる自動解析
- `LLMAnalyzer.analyze_log()` - LLMでログを解析
- `LLMAnalyzer.process_unknown_logs()` - 未知ログの一括処理
- `add_pattern()` - LLM判定後の自動パターン追加

---

### 10. LLM解析

#### `src/llm_analyzer.py`
- **`LLMAnalyzer.__init__(db, api_key=None, model="gpt-4o-mini")`**
  - LLM解析器を初期化
  - APIキーは環境変数 `OPENAI_API_KEY` または `.env` ファイルから読み込む

- **`LLMAnalyzer.analyze_log(log_id, log_entry)`**
  - 単一のログエントリをLLMで解析
  - 戻り値: `{'is_abnormal': bool, 'label': str, 'severity': str, 'reason': str, 'pattern_suggestion': str, 'response': str}`
  - 解析結果は `ai_analyses` テーブルに保存

- **`LLMAnalyzer.process_unknown_logs(limit=10, auto_add_pattern=True)`**
  - 未知ログを一括でLLM解析
  - 異常と判断した場合: アラートを作成
  - 正常と判断した場合: 自動でパターンを追加（`auto_add_pattern=True` の場合）
  - 戻り値: 処理結果の統計情報

- **`LLMAnalyzer._create_prompt(log_entry)`**
  - LLMへのプロンプトを作成

- **`LLMAnalyzer._save_analysis(log_id, prompt, response)`**
  - 解析結果を `ai_analyses` テーブルに保存

- **`LLMAnalyzer._load_env_file()`**
  - `.env` ファイルからAPIキーを読み込む

---

## よく使うコマンド一覧

### ログ取り込み
```bash
python3 src/ingest.py <log_file> [--db db/monitor.db] [-v]
```

### パターン管理
```bash
# 手動パターン追加
python3 src/cli_tools.py add-pattern "<正規表現>" "<サンプル>" --label normal

# 未知ログからパターン生成
python3 src/cli_tools.py add-pattern-from-log <log_id> --label normal

# パターンラベル更新
python3 src/cli_tools.py update-label <pattern_id> normal --severity info

# 未知ログを既知パターンに紐付け
python3 src/cli_tools.py map-log <log_id> <pattern_id>
```

### 統計・確認
```bash
# 統計情報
python3 src/cli_tools.py stats

# 未知パターン一覧
python3 src/cli_tools.py show-unknown --limit 20
```

### 閾値ルール
```bash
python3 scripts/add_threshold_rule.py --pattern-id <id> --rule-type threshold --field-name temp --op '>' --threshold 80.0
```

### 通知
```bash
python3 src/slack_notifier.py --db db/monitor.db
```

### LLM解析
```bash
# 未知ログを一括でLLM解析（自動パターン追加あり）
python3 src/llm_analyzer.py --db db/monitor.db --limit 10

# 特定のログをLLM解析
python3 src/llm_analyzer.py --db db/monitor.db --log-id <log_id>

# 自動パターン追加なし
python3 src/llm_analyzer.py --db db/monitor.db --limit 10 --no-auto-add
```

