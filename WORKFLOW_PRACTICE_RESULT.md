# パラメータ異常検知ワークフロー実践結果

> このファイルで行うこと: 正常ログに対するパラメータベースの異常検知ワークフローの実践結果を記録します。

## 実践日時

2025年12月XX日

## 実践内容

### ステップ1: パターンとルールの追加

#### 1-1: パターン追加（named capture group含む）

```bash
python3 src/cli_tools.py add-pattern \
  "\[\s+\d+\.\d+\]\s+GPU\s+temp:\s+(?P<temp>\d+)°C" \
  "[    0.005840] GPU temp: 75°C" \
  --label normal \
  --severity info \
  --component kernel \
  --note "GPU温度ログ（パラメータ: temp）"
```

**結果**: パターンID 1898が作成されました

#### 1-2: 閾値ルール追加

```bash
python3 scripts/add_threshold_rule.py \
  --pattern-id 1898 \
  --rule-type threshold \
  --field-name temp \
  --op '>' \
  --threshold 80.0 \
  --severity critical \
  --message "GPU temp > 80°C"
```

**結果**: ルールID 1が作成されました

### ステップ2: ログ取り込み

#### テストログ

```
Jul 14 11:20:17 172.20.224.102 kernel: [    0.005840] GPU temp: 75°C
Jul 14 11:20:18 172.20.224.102 kernel: [    0.005841] GPU temp: 85°C
Jul 14 11:20:19 172.20.224.102 kernel: [    0.005842] GPU temp: 90°C
```

#### 取り込み実行

```bash
python3 src/ingest.py /tmp/test_gpu_temp.log --db db/monitor.db -v
```

**結果**: 
- 3行すべてがパターンID 1898にマッチ
- パラメータが正しく抽出されました

### ステップ3: 結果確認

#### ログエントリとパラメータ

| log_id | message | pattern_id | is_known | classification | severity | anomaly_reason | param_name | param_value_num |
|--------|---------|------------|----------|----------------|----------|----------------|------------|-----------------|
| 39342 | GPU temp: 75°C | 1898 | 1 | normal | info | NULL | temp | 75.0 |
| 39343 | GPU temp: 85°C | 1898 | 1 | **abnormal** | **critical** | **GPU temp > 80°C** | temp | 85.0 |
| 39344 | GPU temp: 90°C | 1898 | 1 | **abnormal** | **critical** | **GPU temp > 80°C** | temp | 90.0 |

#### アラート

| alert_id | log_id | alert_type | status | classification |
|----------|--------|------------|--------|----------------|
| (作成済み) | 39343 | abnormal | pending | abnormal |
| (作成済み) | 39344 | abnormal | pending | abnormal |

## ワークフローの動作確認

### ✅ ステップ1: 手動でパラメータ化を実装

- ✅ named capture group `(?P<temp>\d+)` を含むパターンを追加
- ✅ 理想値（閾値）を`pattern_rules`に追加（80°Cを超えた場合に異常）

### ✅ ステップ2: パラメータ化が実装されているか判断

- ✅ 手動パターンが優先的にマッチ（パターンID 1898）
- ✅ named capture groupが検出され、パラメータ抽出が実行された

### ✅ ステップ3: パラメータ化が実装されていない場合は正常形とする

- ✅ パラメータが抽出されない場合は、異常判定が実行されない（正常形として扱われる）

### ✅ ステップ4: パラメータ抽出と異常判定

- ✅ パラメータが正しく抽出され、`log_params`テーブルに保存された
- ✅ `pattern_rules`と`log_params`を突合して異常判定が実行された
- ✅ 閾値を超えたログ（85°C, 90°C）が`classification='abnormal'`に更新された
- ✅ アラートが作成された

## 実装のポイント

### 1. 手動パターンの優先

**実装箇所**: `src/ingest.py` の82-99行目

```python
# 手動パターンを先にチェック（named capture groupを含むパターンを優先）
manual_pattern_id = self._check_manual_patterns(cursor, parsed['message'])
if manual_pattern_id:
    pattern_id = manual_pattern_id
    is_new_pattern = False
```

**効果**: named capture groupを含む手動パターンが優先的にマッチし、パラメータ抽出が確実に実行される

### 2. パラメータ抽出の自動実行

**実装箇所**: `src/ingest.py` の147-160行目

```python
# パラメータ抽出（既知ログの場合）
if pattern_id and is_known:
    pattern_to_use = pattern_row['manual_regex_rule'] or pattern_row['regex_rule']
    if pattern_to_use:
        self._extract_and_save_params(cursor, log_id, pattern_to_use, parsed['message'])
```

**効果**: named capture groupがあれば自動的にパラメータが抽出され、`log_params`に保存される

### 3. 異常判定の自動実行

**実装箇所**: `src/ingest.py` の162-178行目

```python
# 異常判定を実行（既知ログの場合）
anomaly_info = self.anomaly_detector.check_anomaly(log_id, pattern_id)
if anomaly_info:
    # classificationを更新
    cursor.execute("""
        UPDATE log_entries
        SET classification = 'abnormal', severity = ?, anomaly_reason = ?
        WHERE id = ?
    """, ...)
```

**効果**: `pattern_rules`と`log_params`を突合して自動的に異常判定が実行され、異常と判断された場合は`classification`が更新される

## まとめ

✅ **すべてのワークフローが正常に動作しました**

1. ✅ 手動でパラメータ化を実装 → パターンとルールを追加
2. ✅ パラメータ化の判断 → 手動パターンが優先的にマッチ
3. ✅ パラメータ化なしの場合は正常形 → パラメータが抽出されない場合は異常判定が実行されない
4. ✅ パラメータ抽出と異常判定 → パラメータが抽出され、閾値チェックが実行され、異常と判断されたログが`abnormal`に分類された

## 次のステップ

このワークフローを他のログタイプにも適用できます：

1. PCIe帯域幅の監視
2. メモリ使用率の監視
3. ディスクI/Oの監視
4. その他の数値パラメータを含むログ

詳細な手順は `PARAMETER_ANOMALY_DETECTION_WORKFLOW.md` を参照してください。

