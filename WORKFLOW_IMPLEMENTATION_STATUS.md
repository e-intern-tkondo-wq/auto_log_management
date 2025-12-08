# ワークフロー実装状況

> このファイルで行うこと: 5つのワークフローの実装状況と実装箇所を具体的に説明します。

## 実装状況サマリー

| フロー | 実装状況 | 完了率 |
|--------|---------|--------|
| 1. テンプレテーブルを作成する | ✅ 実装済み | 100% |
| 2. 既知/未知の判断 | ✅ 実装済み | 100% |
| 3. 異常判定（異常テンプレ or パラメータ異常） | ✅ 実装済み | 100% |
| 4. 手動でテンプレ化 | ✅ 実装済み | 100% |
| 5. LLMによる自動解析・追加 | ✅ 実装済み | 100% |

---

## フロー1: テンプレテーブルを作成する

### 実装状況: ✅ **100% 実装完了**

### 実装箇所

#### 1. データベーススキーマ定義
**ファイル**: `src/database.py`

```python
# 40-58行目: regex_patterns テーブルの作成
cursor.execute("""
    CREATE TABLE IF NOT EXISTS regex_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        regex_rule TEXT UNIQUE,              # 自動生成パターン
        manual_regex_rule TEXT UNIQUE,       # 手動パターン
        sample_message TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT 'normal',
        severity TEXT,
        note TEXT,
        first_seen_at DATETIME NOT NULL,
        last_seen_at DATETIME NOT NULL,
        total_count INTEGER NOT NULL DEFAULT 1,
        ...
    )
""")
```

#### 2. 自動生成パターンの作成
**ファイル**: `src/ingest.py`

```python
# 64-76行目: abstract_message() でパターンを生成
regex_rule = abstract_message(parsed['message'])

# 282-290行目: 新規パターンを regex_patterns テーブルに追加
cursor.execute("""
    INSERT INTO regex_patterns
    (regex_rule, manual_regex_rule, sample_message, label, severity, first_seen_at, last_seen_at, total_count)
    VALUES (?, NULL, ?, 'normal', NULL, ?, ?, 1)
""", (regex_rule, sample_message, now, now))
```

#### 3. 手動パターンの追加
**ファイル**: `src/cli_tools.py`

```python
# 254-338行目: add_pattern() 関数
# 手動で正規表現パターンを追加
def add_pattern(db_path: str, regex_rule: str, sample_message: str, 
                label: str = 'normal', severity: str = None, ...):
    # manual_regex_rule に格納
    cursor.execute("""
        INSERT INTO regex_patterns
        (regex_rule, manual_regex_rule, sample_message, label, severity, ...)
        VALUES (NULL, ?, ?, ?, ?, ...)
    """, (regex_rule, sample_message, label, severity, ...))
```

### 処理フロー

```
ログファイル読み込み
    ↓
abstract_message() でパターン生成
    ↓
regex_patterns テーブルで既存パターンを検索
    ├─ 既存パターン → カウント更新
    └─ 新規パターン → INSERT（regex_rule に格納）
```

---

## フロー2: テンプレテーブルを参照し、既知か未知かを判断する

### 実装状況: ✅ **100% 実装完了**

### 実装箇所

#### 1. 既知/未知判定ロジック
**ファイル**: `src/ingest.py`

```python
# 78-102行目: パターン検索と既知/未知判定
# 1. 自動生成パターンで検索
pattern_id, is_new_pattern = self._find_or_create_pattern(
    cursor, regex_rule, parsed['message'], verbose
)

# 2. 手動パターンもチェック（元のメッセージに対して直接マッチング）
if not pattern_id or is_new_pattern:
    manual_pattern_id = self._check_manual_patterns(cursor, parsed['message'])
    if manual_pattern_id:
        pattern_id = manual_pattern_id
        is_new_pattern = False

# 3. 既知か未知かを判断
is_known = 1 if pattern_id and not is_new_pattern else 0
```

#### 2. パターン検索処理
**ファイル**: `src/ingest.py`

```python
# 244-290行目: _get_or_create_pattern() メソッド
# regex_rule と manual_regex_rule の両方をチェック
cursor.execute("""
    SELECT id, total_count
    FROM regex_patterns
    WHERE regex_rule = ? OR manual_regex_rule = ?
""", (regex_rule, regex_rule))

# 208-238行目: _check_manual_patterns() メソッド
# 手動パターンを元のメッセージに対して直接マッチング
for row in cursor.fetchall():
    pattern = re.compile(row['manual_regex_rule'])
    if pattern.search(message):  # search を使用（部分マッチ）
        return row['id']
```

#### 3. ログエントリへの反映
**ファイル**: `src/ingest.py`

```python
# 122-137行目: log_entries テーブルに INSERT
cursor.execute("""
    INSERT INTO log_entries
    (ts, host, component, raw_line, message, pattern_id, is_known, classification, severity)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (..., pattern_id, is_known, classification, severity))
```

### 処理フロー

```
ログメッセージ
    ↓
abstract_message() でパターン生成
    ↓
regex_patterns テーブルで検索
    ├─ regex_rule で検索（自動生成パターン）
    └─ manual_regex_rule で検索（手動パターン、元のメッセージに対して直接マッチング）
    ↓
既存パターンが見つかった？
    ├─ YES → is_known = 1（既知ログ）
    └─ NO  → is_known = 0（未知ログ）
    ↓
log_entries に INSERT（is_known フラグを設定）
```

---

## フロー3: 既知なものについて、異常なテンプレかどうか、または正常なテンプレだがパラメータの内容が異常かどうかを判断する

### 実装状況: ✅ **100% 実装完了**

### 実装箇所

#### 1. 異常テンプレの判定（パターン1）
**ファイル**: `src/ingest.py`

```python
# 104-120行目: パターンのラベルに基づいてclassificationを決定
classification = 'normal'
if pattern_id:
    cursor.execute("""
        SELECT label, severity
        FROM regex_patterns
        WHERE id = ?
    """, (pattern_id,))
    pattern_row = cursor.fetchone()
    if pattern_row:
        classification = pattern_row['label']  # 'abnormal' の場合
        severity = pattern_row['severity']
```

**判定基準**: `regex_patterns.label = 'abnormal'` の場合、自動的に `log_entries.classification = 'abnormal'` に設定

#### 2. パラメータ抽出
**ファイル**: `src/ingest.py`

```python
# 142-155行目: 既知ログの場合、パラメータを抽出
if pattern_id and is_known:
    # manual_regex_rule があればそれを使用、なければ regex_rule を使用
    pattern_to_use = pattern_row['manual_regex_rule'] or pattern_row['regex_rule']
    if pattern_to_use:
        self._extract_and_save_params(cursor, log_id, pattern_to_use, parsed['message'])
```

**ファイル**: `src/param_extractor.py`

```python
# 11-60行目: ParamExtractor.extract_params() メソッド
# named capture group からパラメータを抽出
pattern = re.compile(regex_rule)
match = pattern.fullmatch(message)
if match:
    groups = match.groupdict()
    # log_params テーブルに保存
```

#### 3. パラメータ異常の判定（パターン2）
**ファイル**: `src/ingest.py`

```python
# 157-173行目: 異常判定を実行（既知ログの場合）
anomaly_info = self.anomaly_detector.check_anomaly(log_id, pattern_id)
if anomaly_info:
    # 異常が検知された場合、classificationを更新
    cursor.execute("""
        UPDATE log_entries
        SET classification = ?,
            severity = ?,
            anomaly_reason = ?
        WHERE id = ?
    """, (
        anomaly_info['classification'],  # 'abnormal'
        anomaly_info['severity'],
        anomaly_info['anomaly_reason'],
        log_id
    ))
```

**ファイル**: `src/anomaly_detector.py`

```python
# 24-92行目: AnomalyDetector.check_anomaly() メソッド
# pattern_rules テーブルからルールを取得
cursor.execute("""
    SELECT rule_type, field_name, op, threshold_value1, ...
    FROM pattern_rules
    WHERE pattern_id = ? AND is_active = 1
""", (pattern_id,))

# log_params テーブルからパラメータ値を取得
cursor.execute("""
    SELECT param_name, param_value_num, param_value_text
    FROM log_params
    WHERE log_id = ?
""", (log_id,))

# ルールを評価（threshold, contains, regex）
for rule in rules:
    if self._evaluate_rule(rule, message, params):
        return {
            'classification': 'abnormal',
            'severity': rule['severity_if_match'],
            'anomaly_reason': rule['message']
        }
```

### 処理フロー

```
既知ログ（is_known = 1）
    ↓
┌─────────────────────────────────────┐
│ パターン1: 異常テンプレの判定        │
├─────────────────────────────────────┤
│ regex_patterns.label = 'abnormal'? │
│   ├─ YES → classification = 'abnormal' │
│   └─ NO  → 次へ                      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ パターン2: パラメータ異常の判定      │
├─────────────────────────────────────┤
│ 1. パラメータ抽出 → log_params に保存 │
│ 2. pattern_rules からルールを取得    │
│ 3. ルールを評価                       │
│    ├─ 異常 → classification = 'abnormal' │
│    └─ 正常 → classification = 'normal'   │
└─────────────────────────────────────┘
```

---

## フロー4: 未知なものについて、手動でテンプレ化できそうなものは手動でテンプレを作り、再度2に戻り、既知に割り振られるようにする

### 実装状況: ✅ **100% 実装完了**

### 実装箇所

#### 1. 手動パターンの追加
**ファイル**: `src/cli_tools.py`

```python
# 254-338行目: add_pattern() 関数
# 正規表現パターンを直接指定して追加
def add_pattern(db_path: str, regex_rule: str, sample_message: str, 
                label: str = 'normal', ...):
    # manual_regex_rule に格納
    cursor.execute("""
        INSERT INTO regex_patterns
        (regex_rule, manual_regex_rule, sample_message, label, ...)
        VALUES (NULL, ?, ?, ?, ...)
    """, (regex_rule, sample_message, label, ...))
```

```python
# 341-397行目: add_pattern_from_log() 関数
# 未知ログから自動的にパターンを生成して追加
def add_pattern_from_log(db_path: str, log_id: int, label: str = 'normal', ...):
    # abstract_message() でパターンを生成
    regex_rule = abstract_message(log_row['message'])
    # パターンを追加
    pattern_id = add_pattern(db_path, regex_rule, sample_message, label, ...)
    # ログエントリを新しく追加したパターンに紐付け
    cursor.execute("""
        UPDATE log_entries
        SET pattern_id = ?,
            is_known = 1,
            is_manual_mapped = 1,
            classification = ?,
            severity = ?
        WHERE id = ?
    """, (pattern_id, label, severity, log_id))
```

#### 2. 既存の未知ログを既知パターンに紐付け
**ファイル**: `src/cli_tools.py`

```python
# 204-251行目: map_unknown_log_to_pattern() 関数
# 未知ログを既知パターンに手動で紐付ける
def map_unknown_log_to_pattern(db_path: str, log_id: int, pattern_id: int):
    cursor.execute("""
        UPDATE log_entries
        SET pattern_id = ?,
            is_known = 1,
            is_manual_mapped = 1,
            classification = ?,
            severity = ?
        WHERE id = ?
    """, (pattern_id, pattern_row['label'], pattern_row['severity'], log_id))
```

#### 3. 手動パターンのマッチング（フロー2に戻る）
**ファイル**: `src/ingest.py`

```python
# 208-238行目: _check_manual_patterns() メソッド
# 新しいログを取り込む際に、手動パターンが優先的にマッチする
def _check_manual_patterns(self, cursor, message: str) -> Optional[int]:
    cursor.execute("""
        SELECT id, manual_regex_rule
        FROM regex_patterns
        WHERE manual_regex_rule IS NOT NULL
    """)
    for row in cursor.fetchall():
        pattern = re.compile(row['manual_regex_rule'])
        if pattern.search(message):  # 元のメッセージに対して直接マッチング
            return row['id']  # 既知パターンとして扱われる
```

### 処理フロー

```
未知ログ（is_known = 0）
    ↓
手動でパターンを作成
    ├─ 方法A: add-pattern コマンドで正規表現を直接指定
    └─ 方法B: add-pattern-from-log コマンドで未知ログから自動生成
    ↓
regex_patterns テーブルに manual_regex_rule として追加
    ↓
既存の未知ログを既知パターンに紐付け（オプション）
    └─ map-log コマンドで手動紐付け
    ↓
新しいログを取り込む
    ↓
_check_manual_patterns() で手動パターンがマッチ
    ↓
is_known = 1（既知ログとして扱われる）
```

---

## フロー5: 未知かつテンプレ化できないものについては、LLMによってエラーの内容を解析し、異常であれば通知を、正常であればテンプレDBへの自動追加をする

### 実装状況: ✅ **100% 実装完了**

### 実装箇所

#### 1. LLM処理モジュール
**ファイル**: `src/llm_analyzer.py`

```python
# 23-52行目: LLMAnalyzer クラス
class LLMAnalyzer:
    def __init__(self, db: Database, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        # .envファイルまたは環境変数からAPIキーを読み込む
        self.api_key = os.getenv('OPENAI_API_KEY') or self._load_env_file()
        self.client = OpenAI(api_key=self.api_key)
```

#### 2. 単一ログのLLM解析
**ファイル**: `src/llm_analyzer.py`

```python
# 75-120行目: analyze_log() メソッド
def analyze_log(self, log_id: int, log_entry: Dict) -> Dict:
    # プロンプトを作成
    prompt = self._create_prompt(log_entry)
    
    # OpenAI APIに送信
    response = self.client.chat.completions.create(
        model=self.model,
        messages=[...],
        response_format={"type": "json_object"}
    )
    
    # 解析結果をパース
    result = json.loads(response_text)
    
    # ai_analyses テーブルに保存
    self._save_analysis(log_id, prompt, response_text)
    
    return {
        'is_abnormal': result.get('is_abnormal', False),
        'label': result.get('label', 'unknown'),
        'severity': result.get('severity', 'unknown'),
        'reason': result.get('reason', ''),
        'pattern_suggestion': result.get('pattern_suggestion', '')
    }
```

#### 3. 未知ログの一括処理
**ファイル**: `src/llm_analyzer.py`

```python
# 222-330行目: process_unknown_logs() メソッド
def process_unknown_logs(self, limit: int = 10, auto_add_pattern: bool = True):
    # 未知ログを取得（まだLLM解析されていないもの）
    cursor.execute("""
        SELECT le.id, le.ts, le.host, le.component, le.message, le.raw_line
        FROM log_entries le
        LEFT JOIN ai_analyses aa ON le.id = aa.log_id
        WHERE le.is_known = 0 AND aa.id IS NULL
        ORDER BY le.ts DESC
        LIMIT ?
    """, (limit,))
    
    # 各ログをLLMで解析
    for log_row in unknown_logs:
        result = self.analyze_log(log_id, log_entry)
        
        if result['label'] == 'abnormal':
            # 異常と判断 → アラートを作成
            self._create_alert(log_id, 'abnormal')
            # log_entries を更新
            cursor.execute("""
                UPDATE log_entries
                SET classification = 'abnormal', severity = ?, anomaly_reason = ?
                WHERE id = ?
            """, (result['severity'], result['reason'], log_id))
        
        elif result['label'] == 'normal' and auto_add_pattern:
            # 正常と判断 → パターンを自動追加
            pattern_id = add_pattern(...)
            # ログエントリをパターンに紐付け
            cursor.execute("""
                UPDATE log_entries
                SET pattern_id = ?, is_known = 1, is_manual_mapped = 1,
                    classification = 'normal', severity = ?
                WHERE id = ?
            """, (pattern_id, result['severity'], log_id))
```

#### 4. .envファイルの読み込み
**ファイル**: `src/llm_analyzer.py`

```python
# 54-82行目: _load_env_file() メソッド
def _load_env_file(self) -> Optional[str]:
    # プロジェクトルートの .env ファイルを読み込む
    env_path = os.path.join(current_dir, '.env')
    # OPENAI_API_KEY=... の形式で読み込む
```

#### 5. データベーススキーマ
**ファイル**: `src/database.py`

```python
# 189-199行目: ai_analyses テーブルの作成
cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id INTEGER NOT NULL,
        prompt TEXT,
        response TEXT,
        model_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (log_id) REFERENCES log_entries(id)
    )
""")
```

#### 6. CLIツール
**ファイル**: `src/llm_analyzer.py`

```python
# 333-405行目: main() 関数
# コマンドラインインターフェース
python3 src/llm_analyzer.py --db db/monitor.db --limit 10
python3 src/llm_analyzer.py --db db/monitor.db --log-id <log_id>
```

### 処理フロー

```
未知ログ（is_known = 0）
    ↓
LLM解析（process_unknown_logs()）
    ├─ 未知ログを抽出（ai_analyses に未登録のもの）
    └─ 各ログをLLMで解析
        ↓
    LLMの判定結果
        ├─ abnormal → アラート作成 + log_entries.classification = 'abnormal'
        ├─ normal → パターン自動追加 + is_known = 1
        └─ unknown → そのまま（手動対応待ち）
    ↓
ai_analyses テーブルに解析結果を保存
```

### 使用方法

#### 1. .envファイルの設定

プロジェクトルートに `.env` ファイルを作成:

```bash
# .env
OPENAI_API_KEY=your_openai_api_key_here
```

#### 2. 依存パッケージのインストール

```bash
pip install openai python-dotenv
```

#### 3. LLM解析の実行

```bash
# 未知ログを一括でLLM解析（自動パターン追加あり）
python3 src/llm_analyzer.py --db db/monitor.db --limit 10

# 特定のログをLLM解析
python3 src/llm_analyzer.py --db db/monitor.db --log-id <log_id>

# 自動パターン追加なし（解析のみ）
python3 src/llm_analyzer.py --db db/monitor.db --limit 10 --no-auto-add
```

### 実装のポイント

1. **APIキーの取得**: 環境変数 `OPENAI_API_KEY` または `.env` ファイルから読み込む
2. **JSON形式のレスポンス**: LLMにJSON形式でレスポンスを要求し、パースしやすい形式に
3. **自動処理**: 
   - 異常 → アラート作成（`alerts` テーブル）
   - 正常 → パターン追加（`regex_patterns` テーブル）+ ログエントリの紐付け
4. **解析履歴の保存**: すべての解析結果を `ai_analyses` テーブルに保存
5. **重複解析の防止**: `ai_analyses` テーブルを参照して、既に解析済みのログはスキップ

---

## まとめ

### 実装済み（フロー1-4）

- ✅ **フロー1**: テンプレテーブルの作成（自動生成・手動追加の両方）
- ✅ **フロー2**: 既知/未知の判断（自動生成パターン・手動パターンの両方をチェック）
- ✅ **フロー3**: 異常判定（異常テンプレ・パラメータ異常の両方）
- ✅ **フロー4**: 手動テンプレ化（パターン追加・既存ログの紐付け）

### 実装済み（フロー5）

- ✅ **フロー5**: LLMによる自動解析・追加
  - LLM処理ロジック: ✅ 実装済み（`src/llm_analyzer.py`）
  - 自動通知: ✅ 実装済み（異常と判断した場合に `alerts` テーブルに追加）
  - 自動パターン追加: ✅ 実装済み（正常と判断した場合に `regex_patterns` テーブルに追加）
  - .envファイルからのAPIキー読み込み: ✅ 実装済み

### 実装のポイント

1. **フロー2の実装**: `_check_manual_patterns()` により、手動パターンが優先的にマッチし、既知ログとして扱われる
2. **フロー3の実装**: 2つのパターンで異常判定
   - パターン1: `regex_patterns.label = 'abnormal'` の場合
   - パターン2: `pattern_rules` + `log_params` による閾値チェック
3. **フロー4の実装**: 手動パターン追加後、新しいログを取り込むと自動的に既知ログとして扱われる

