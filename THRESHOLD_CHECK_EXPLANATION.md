# 閾値チェックの仕組み

## 概要

閾値チェックは、**`log_params` テーブル**と**`pattern_rules` テーブル**の**両方**を使用して実現されています。

## データフロー

```
ログメッセージ
    ↓
パラメータ抽出（named capture group）
    ↓
log_params テーブルに保存（パラメータ値）
    ↓
pattern_rules テーブルからルールを取得（閾値定義）
    ↓
AnomalyDetector が両方を参照して評価
    ↓
異常判定結果
```

## 各テーブルの役割

### 1. `log_params` テーブル（データストア）

**役割**: ログから抽出したパラメータ値を保存

**例**:
```sql
log_id: 123
param_name: "temp"
param_value_num: 85.0
param_value_text: "85"
```

**特徴**:
- パラメータ値を保存するだけ
- どの値が異常かは判断しない
- named capture groupを含むパターンから自動抽出

### 2. `pattern_rules` テーブル（ルール定義）

**役割**: 閾値チェックのルールを定義

**例**:
```sql
pattern_id: 100
rule_type: "threshold"
field_name: "temp"
op: ">"
threshold_value1: 80.0
severity_if_match: "critical"
message: "GPU temp > 80°C"
```

**特徴**:
- どのパラメータをチェックするか（`field_name`）
- どのような条件か（`op`, `threshold_value1`）
- 異常時のseverity（`severity_if_match`）

### 3. `AnomalyDetector` クラス（実行エンジン）

**役割**: `log_params` と `pattern_rules` を参照して異常判定を実行

**処理フロー**:
1. `pattern_rules` からルールを取得
2. `log_params` からパラメータ値を取得
3. ルールの条件を評価
4. 条件にマッチした場合、異常と判定

## 具体例

### 例: GPU温度の監視

#### 1. ログメッセージ
```
[    0.005840] GPU temp: 85°C
```

#### 2. 手動パターン（named capture groupを含む）
```regex
GPU temp: (?P<temp>\d+)°C
```

#### 3. パラメータ抽出 → `log_params` テーブル
```sql
INSERT INTO log_params (log_id, param_name, param_value_num, param_value_text)
VALUES (123, 'temp', 85.0, '85');
```

#### 4. ルール定義 → `pattern_rules` テーブル
```sql
INSERT INTO pattern_rules (
    pattern_id, rule_type, field_name, op,
    threshold_value1, severity_if_match, message
)
VALUES (
    100, 'threshold', 'temp', '>',
    80.0, 'critical', 'GPU temp > 80°C'
);
```

#### 5. 異常判定時の処理

```python
# AnomalyDetector.check_anomaly(log_id=123, pattern_id=100)

# 1. pattern_rules からルールを取得
rule = {
    'field_name': 'temp',
    'op': '>',
    'threshold_value1': 80.0,
    'severity_if_match': 'critical'
}

# 2. log_params からパラメータ値を取得
params = {'temp': 85.0}  # log_params テーブルから取得

# 3. ルールを評価
value = params['temp']  # 85.0
threshold = rule['threshold_value1']  # 80.0
op = rule['op']  # '>'

# 4. 条件評価
if value > threshold:  # 85.0 > 80.0 → True
    return {
        'classification': 'abnormal',
        'severity': 'critical',
        'anomaly_reason': 'GPU temp > 80°C'
    }
```

## 重要なポイント

### ✅ 両方のテーブルが必要

- **`log_params` だけ**: パラメータ値はあるが、どの値が異常か判断できない
- **`pattern_rules` だけ**: ルールはあるが、実際のパラメータ値がない
- **両方**: パラメータ値とルールを組み合わせて異常判定が可能

### 閾値チェックの種類

`pattern_rules` の `rule_type` によって、以下のチェックが可能：

1. **`threshold`**: パラメータ値のしきい値チェック
   - 例: `temp > 80`, `gran_size < 100`
   - **`log_params` の `param_value_num` を使用**

2. **`contains`**: メッセージまたはパラメータ値に文字列が含まれるか
   - 例: メッセージに "error" が含まれる
   - **`log_params` の `param_value_text` または `message` を使用**

3. **`regex`**: 正規表現マッチング
   - 例: メッセージが特定のパターンにマッチする
   - **`log_params` の `param_value_text` または `message` を使用**

## コード実装

### `AnomalyDetector.check_anomaly()`

```python
def check_anomaly(self, log_id: int, pattern_id: int):
    # 1. pattern_rules からルールを取得
    cursor.execute("""
        SELECT rule_type, field_name, op, threshold_value1, ...
        FROM pattern_rules
        WHERE pattern_id = ? AND is_active = 1
    """, (pattern_id,))
    rules = cursor.fetchall()
    
    # 2. log_params からパラメータ値を取得
    cursor.execute("""
        SELECT param_name, param_value_num, param_value_text
        FROM log_params
        WHERE log_id = ?
    """, (log_id,))
    
    params = {}
    for row in cursor.fetchall():
        # 数値があれば数値を使用、なければテキスト
        params[row['param_name']] = (
            row['param_value_num'] 
            if row['param_value_num'] is not None 
            else row['param_value_text']
        )
    
    # 3. 各ルールを評価
    for rule in rules:
        if self._evaluate_rule(rule, message, params):
            return {
                'classification': 'abnormal',
                'severity': rule['severity_if_match'],
                'anomaly_reason': rule['message']
            }
```

### `_evaluate_rule()` での閾値チェック

```python
def _evaluate_rule(self, rule, message, params):
    if rule['rule_type'] == 'threshold':
        # log_params からパラメータ値を取得
        field_name = rule['field_name']
        if field_name not in params:
            return False
        
        value = params[field_name]  # log_params から取得した値
        threshold = rule['threshold_value1']  # pattern_rules から取得した閾値
        op = rule['op']
        
        # 閾値チェック
        if op == '>':
            return value > threshold
        elif op == '<':
            return value < threshold
        # ...
```

## まとめ

**閾値チェックは `log_params` と `pattern_rules` の両方を使用します**:

- **`log_params`**: パラメータ値を保存（データ）
- **`pattern_rules`**: 閾値チェックのルールを定義（ルール）
- **`AnomalyDetector`**: 両方を参照して異常判定を実行（エンジン）

named capture groupが不要な場合、`log_params` にデータが保存されないため、`pattern_rules` の `threshold` タイプのルールは使用できません。ただし、`contains` や `regex` タイプのルール（メッセージ本文に対して直接適用）は使用可能です。

