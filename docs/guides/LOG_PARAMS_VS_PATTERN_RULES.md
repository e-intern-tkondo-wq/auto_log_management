# log_params と pattern_rules の違い

> このファイルで行うこと: `log_params`テーブルと`pattern_rules`テーブルの役割と違いを説明します。

## 概要

`log_params`と`pattern_rules`は、**異常判定システムの2つの重要なコンポーネント**です。これらは**一緒に使用**されて、ログから抽出したパラメータ値が異常かどうかを判定します。

## 主な違い

| 項目 | `log_params` | `pattern_rules` |
|------|-------------|----------------|
| **役割** | **データストア**（実際の値） | **ルール定義**（判定基準） |
| **格納内容** | ログから抽出したパラメータ値 | 異常判定のルール（閾値、条件） |
| **関連テーブル** | `log_entries`（1つのログに複数のパラメータ） | `regex_patterns`（1つのパターンに複数のルール） |
| **更新頻度** | ログ取り込みのたびに追加 | 手動で定義・更新 |
| **例** | `temp=85.0`, `bandwidth=31.504` | `temp > 80.0` なら異常 |

---

## 1. `log_params` テーブル（データストア）

### 役割

**実際のログから抽出したパラメータ値を保存**します。

### スキーマ

```sql
CREATE TABLE log_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER NOT NULL,              -- どのログから抽出したか
    param_name TEXT NOT NULL,             -- パラメータ名（例: "temp", "bandwidth"）
    param_value_num REAL,                 -- 数値パラメータ（例: 85.0）
    param_value_text TEXT,                -- テキストパラメータ（例: "85°C"）
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_id) REFERENCES log_entries(id)
)
```

### 特徴

- **データを保存するだけ**（どの値が異常かは判断しない）
- **named capture group**を含む正規表現パターンから自動抽出
- 1つのログエントリに複数のパラメータが紐付く可能性がある

### 例

```sql
-- ログ: "[    0.005840] GPU temp: 85°C"
-- パターン: "\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C"

log_id: 123
param_name: "temp"
param_value_num: 85.0
param_value_text: "85"
```

### データの流れ

```
ログメッセージ
    ↓
正規表現パターン（named capture group含む）
    ↓
パラメータ抽出（ParamExtractor）
    ↓
log_params テーブルに保存
```

---

## 2. `pattern_rules` テーブル（ルール定義）

### 役割

**異常判定のルールを定義**します。どのパラメータを、どのような条件でチェックするかを定義します。

### スキーマ

```sql
CREATE TABLE pattern_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id INTEGER NOT NULL,          -- どのパターンに対するルールか
    rule_type TEXT NOT NULL,              -- ルールタイプ（threshold, contains, regex）
    field_name TEXT,                      -- チェックするパラメータ名（例: "temp"）
    op TEXT NOT NULL,                     -- 演算子（例: ">", "<", "=="）
    threshold_value1 REAL,                -- 閾値1（例: 80.0）
    threshold_value2 REAL,                -- 閾値2（範囲チェック用）
    severity_if_match TEXT NOT NULL,      -- 異常時のseverity（例: "critical"）
    is_abnormal_if_match INTEGER DEFAULT 1, -- マッチ時に異常とするか
    message TEXT,                         -- 異常理由メッセージ（例: "GPU temp > 80°C"）
    is_active INTEGER DEFAULT 1,          -- ルールが有効か
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pattern_id) REFERENCES regex_patterns(id)
)
```

### 特徴

- **ルールを定義するだけ**（実際の値は保存しない）
- 手動で定義・更新する必要がある
- 1つのパターンに複数のルールを定義可能

### 例

```sql
-- パターンID 100（GPU温度ログ）に対するルール

pattern_id: 100
rule_type: "threshold"
field_name: "temp"
op: ">"
threshold_value1: 80.0
severity_if_match: "critical"
message: "GPU temp > 80°C"
is_active: 1
```

### データの流れ

```
手動でルールを定義
    ↓
pattern_rules テーブルに保存
    ↓
異常判定時に参照される
```

---

## 3. 両者の関係

### 異常判定の流れ

```
1. ログ取り込み
   ↓
2. パラメータ抽出 → log_params に保存
   （例: temp=85.0）
   ↓
3. pattern_rules からルールを取得
   （例: temp > 80.0 なら異常）
   ↓
4. AnomalyDetector が両方を参照して評価
   log_params の値（85.0）と pattern_rules のルール（> 80.0）を比較
   ↓
5. 条件にマッチ → 異常と判定
   （85.0 > 80.0 なので異常）
```

### コード実装

```python
# src/anomaly_detector.py

def check_anomaly(self, log_id: int, pattern_id: int):
    # 1. pattern_rules からルールを取得（ルール定義）
    cursor.execute("""
        SELECT rule_type, field_name, op, threshold_value1, ...
        FROM pattern_rules
        WHERE pattern_id = ? AND is_active = 1
    """, (pattern_id,))
    rules = cursor.fetchall()
    
    # 2. log_params からパラメータ値を取得（実際の値）
    cursor.execute("""
        SELECT param_name, param_value_num, param_value_text
        FROM log_params
        WHERE log_id = ?
    """, (log_id,))
    
    params = {}
    for row in cursor.fetchall():
        params[row['param_name']] = (
            row['param_value_num'] 
            if row['param_value_num'] is not None 
            else row['param_value_text']
        )
    
    # 3. ルールとパラメータ値を比較して異常判定
    for rule in rules:
        if self._evaluate_rule(rule, message, params):
            return {
                'classification': 'abnormal',
                'severity': rule['severity_if_match'],
                'anomaly_reason': rule['message']
            }
```

---

## 具体例

### 例: PCIe帯域幅の監視

#### 1. ログメッセージ
```
Jul 14 11:20:17 172.20.224.102 kernel: [ 19.033705] pci 0000:01:00.0: 31.504 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x4 link at 0000:00:08.0 (capable of 63.012 Gb/s with 16.0 GT/s PCIe x4 link)
```

#### 2. 手動パターン（named capture group含む）
```regex
\[\s+\d+\.\d+\]\s+pci\s+\S+:\s+(?P<available_bandwidth>\d+\.\d+)\s+Gb/s\s+available\s+PCIe\s+bandwidth
```

#### 3. log_params に保存される値（データ）
```sql
log_id: 456
param_name: "available_bandwidth"
param_value_num: 31.504
param_value_text: "31.504"
```

#### 4. pattern_rules に定義されるルール（判定基準）
```sql
pattern_id: 200
rule_type: "threshold"
field_name: "available_bandwidth"
op: "<"
threshold_value1: 50.0
severity_if_match: "warning"
message: "PCIe bandwidth < 50 Gb/s"
```

#### 5. 異常判定の実行
```
log_params の値: available_bandwidth = 31.504
pattern_rules のルール: available_bandwidth < 50.0
評価: 31.504 < 50.0 → True → 異常と判定
結果: classification = 'abnormal', severity = 'warning'
```

---

## まとめ

| 観点 | `log_params` | `pattern_rules` |
|------|-------------|----------------|
| **何を保存するか** | 実際のパラメータ値（データ） | 異常判定のルール（定義） |
| **いつ作成されるか** | ログ取り込み時（自動） | 手動で定義 |
| **何を参照するか** | `log_entries`（ログ） | `regex_patterns`（パターン） |
| **用途** | パラメータ値の保存 | 異常判定基準の定義 |
| **更新頻度** | ログ取り込みのたび | 必要に応じて手動更新 |

**重要なポイント**: 
- `log_params`は**「何が起きたか」**を記録
- `pattern_rules`は**「何が異常か」**を定義
- 両方を組み合わせて**異常判定**を実行

