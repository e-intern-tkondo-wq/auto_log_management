# LLM自動解析機能の実装ガイド

> このファイルで行うこと: フロー5（LLMによる自動解析）の実装内容と使用方法を説明します。

## 実装概要

未知ログをLLM（GPT）で自動解析し、異常と判断した場合は通知、正常と判断した場合は自動でパターンを追加する機能を実装しました。

## 実装ファイル

- **`src/llm_analyzer.py`**: LLM解析のメイン実装
- **`src/database.py`**: `ai_analyses` テーブルの追加
- **`requirements.txt`**: `openai` と `python-dotenv` の追加

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

または個別にインストール:

```bash
pip install openai python-dotenv
```

### 2. .envファイルの作成

プロジェクトルートに `.env` ファイルを作成:

```bash
# .env
OPENAI_API_KEY=your_openai_api_key_here
```

**注意**: `.env` ファイルは `.gitignore` に追加することを推奨します。

### 3. APIキーの取得

OpenAI APIキーは以下から取得できます:
- https://platform.openai.com/api-keys

## 使用方法

### 基本的な使い方

#### 1. 未知ログを一括でLLM解析（自動パターン追加あり）

```bash
python3 src/llm_analyzer.py --db db/monitor.db --limit 10
```

**動作**:
- 未知ログ（`is_known = 0`）で、まだLLM解析されていないログを最大10件取得
- 各ログをLLMで解析
- **異常と判断** → アラートを作成（`alerts` テーブル）+ `log_entries.classification = 'abnormal'`
- **正常と判断** → パターンを自動追加（`regex_patterns` テーブル）+ `is_known = 1`
- 解析結果を `ai_analyses` テーブルに保存

#### 2. 特定のログをLLM解析

```bash
python3 src/llm_analyzer.py --db db/monitor.db --log-id <log_id>
```

**動作**:
- 指定したログIDのログをLLMで解析
- 解析結果を表示
- 解析結果を `ai_analyses` テーブルに保存（自動処理は行わない）

#### 3. 自動パターン追加なし（解析のみ）

```bash
python3 src/llm_analyzer.py --db db/monitor.db --limit 10 --no-auto-add
```

**動作**:
- LLMで解析は行うが、正常と判断した場合でもパターンは追加しない
- 解析結果のみを `ai_analyses` テーブルに保存

### コマンドラインオプション

```bash
python3 src/llm_analyzer.py [OPTIONS]

Options:
  --db PATH              データベースパス（デフォルト: db/monitor.db）
  --api-key KEY          OpenAI APIキー（環境変数または.envファイルからも読み込める）
  --model MODEL          モデル名（デフォルト: gpt-4o-mini）
  --limit N              処理するログ数の上限（デフォルト: 10）
  --no-auto-add          自動パターン追加を無効化
  --log-id ID            特定のログIDを解析
```

## 処理フロー

```
未知ログ（is_known = 0）
    ↓
process_unknown_logs()
    ├─ 未知ログを抽出
    │   └─ ai_analyses に未登録のログのみ
    └─ 各ログをLLMで解析
        ↓
    analyze_log()
        ├─ プロンプトを作成
        ├─ OpenAI APIに送信
        ├─ JSON形式でレスポンスを取得
        └─ ai_analyses テーブルに保存
        ↓
    解析結果に基づいて処理
        ├─ abnormal → アラート作成 + classification = 'abnormal'
        ├─ normal → パターン追加 + is_known = 1
        └─ unknown → そのまま（手動対応待ち）
```

## LLMのプロンプト

LLMには以下のようなプロンプトを送信します:

```
Analyze the following system log entry and determine if it indicates an abnormal condition.

Log Information:
- Timestamp: ...
- Host: ...
- Component: ...
- Message: ...

Please provide your analysis in JSON format with the following structure:
{
    "is_abnormal": true/false,
    "label": "normal" or "abnormal" or "unknown",
    "severity": "info" or "warning" or "critical" or "unknown",
    "reason": "Brief explanation of your judgment",
    "pattern_suggestion": "Regular expression pattern suggestion if this is a normal log..."
}
```

## データベーススキーマ

### ai_analyses テーブル

```sql
CREATE TABLE ai_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,
    prompt TEXT,
    response TEXT,
    model_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_id) REFERENCES log_entries(id)
)
```

## 実装の詳細

### 1. APIキーの読み込み順序

1. コンストラクタの `api_key` 引数
2. 環境変数 `OPENAI_API_KEY`
3. `.env` ファイル（プロジェクトルート）

### 2. パターン追加のロジック

- **LLMがパターンを提案した場合**: 提案されたパターンを `manual_regex_rule` に格納
- **LLMがパターンを提案しなかった場合**: `abstract_message()` で自動生成したパターンを `regex_rule` に格納

### 3. 重複解析の防止

`ai_analyses` テーブルを参照して、既に解析済みのログはスキップします。

```sql
SELECT le.id, ...
FROM log_entries le
LEFT JOIN ai_analyses aa ON le.id = aa.log_id
WHERE le.is_known = 0 AND aa.id IS NULL
```

## 使用例

### 例1: 未知ログを10件解析

```bash
python3 src/llm_analyzer.py --db db/monitor.db --limit 10
```

**出力例**:
```
Processing 10 unknown logs with LLM...
  ✅ Log 123: Added pattern 45 (normal)
  ✅ Log 124: Added pattern 46 (normal, auto-generated)
  ℹ️  Log 125: Classified as abnormal
  ...

Processing complete:
  Processed: 10
  Abnormal: 2
  Normal: 7
  Unknown: 1
  Patterns added: 7
  Alerts created: 2
```

### 例2: 特定のログを解析

```bash
python3 src/llm_analyzer.py --db db/monitor.db --log-id 123
```

**出力例**:
```
Analysis result for log 123:
  Label: normal
  Severity: info
  Is abnormal: False
  Reason: This is a regular initialization log
  Pattern suggestion: \[\s+\d+\.\d+\]\s+kernel:\s+.*
```

## トラブルシューティング

### エラー: "OpenAI API key not found"

**原因**: APIキーが設定されていない

**解決方法**:
1. `.env` ファイルに `OPENAI_API_KEY=...` を追加
2. または環境変数 `OPENAI_API_KEY` を設定
3. または `--api-key` オプションで指定

### エラー: "openai package not installed"

**原因**: `openai` パッケージがインストールされていない

**解決方法**:
```bash
pip install openai
```

### エラー: "Invalid JSON response"

**原因**: LLMがJSON形式でレスポンスを返さなかった

**解決方法**:
- モデルを変更してみる（`--model gpt-4` など）
- プロンプトを調整する（`src/llm_analyzer.py` の `_create_prompt()` メソッド）

## 注意事項

1. **APIコスト**: LLM APIの使用にはコストがかかります。大量のログを処理する場合は注意してください。
2. **レート制限**: OpenAI APIにはレート制限があります。大量のログを処理する場合は、`--limit` オプションで制限してください。
3. **精度**: LLMの判定は100%正確ではありません。重要なログは手動で確認することを推奨します。
4. **パターン提案**: LLMが提案するパターンは必ずしも最適ではありません。必要に応じて手動で調整してください。

## 今後の改善点

- [ ] バッチ処理の最適化（並列処理など）
- [ ] エラーハンドリングの強化
- [ ] 解析結果の可視化
- [ ] カスタムプロンプトのサポート
- [ ] 他のLLMプロバイダー（Claude、Gemini等）のサポート

