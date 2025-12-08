# ドキュメント構造ガイド

> このファイルで行うこと: プロジェクトのドキュメント構造と各ファイルの役割を説明します。

## ドキュメント階層

### 📘 ルートディレクトリ（メインドキュメント）

1. **`README.md`**
   - プロジェクト全体の概要・セットアップ・基本的な使い方
   - 最初に読むべきファイル

2. **`EXECUTION_FLOW_CHECKLIST.md`**
   - 実行フロー確認チェックリスト
   - 各機能を1つ1つコマンドを叩いて確認するためのフロー
   - ステップバイステップの確認手順

3. **`CHANGELOG.md`**
   - 変更履歴
   - 機能追加・修正の記録

4. **`DOCUMENTATION_STRUCTURE.md`**（このファイル）
   - ドキュメント構造の説明

### 📗 `docs/guides/` - ガイド・手順書

5. **`docs/guides/EXECUTION_FLOW.md`**
   - ステップバイステップの実行手順
   - 実際の操作手順が詳しく書かれている

6. **`docs/guides/MANUAL_PATTERN_GUIDE.md`**
   - 手動パターン追加の手順
   - Named capture groupの使い方

7. **`docs/guides/THRESHOLD_CHECK_EXPLANATION.md`**
   - 閾値チェックの仕組み
   - パラメータ抽出とルール評価の流れ

8. **`docs/guides/LLM_IMPLEMENTATION_GUIDE.md`**
   - LLM自動解析機能の実装と使用方法
   - .envファイルの設定方法

9. **`docs/guides/PARAMETER_ANOMALY_DETECTION_WORKFLOW.md`**
   - パラメータ異常検知のワークフロー
   - パラメータ抽出から異常判定までの流れ

10. **`docs/guides/LOG_PARAMS_VS_PATTERN_RULES.md`**
    - log_paramsテーブルとpattern_rulesテーブルの違いと使い分け
    - パラメータ抽出とルール定義の関係

### 📙 `docs/technical/` - 技術詳細ドキュメント

11. **`docs/technical/DATABASE_ER_DIAGRAM.md`**
    - データベーススキーマの詳細
    - ER図とテーブル定義

12. **`docs/technical/ABNORMAL_DETECTION_FLOW.md`**
    - 異常判定のフローとデータベース反映
    - パターン1（異常テンプレ）とパターン2（パラメータ異常）の説明

13. **`docs/technical/WORKFLOW_IMPLEMENTATION_STATUS.md`**
    - 5つのワークフローの実装状況
    - 各フローの実装箇所とコード例

### 📕 `docs/reference/` - リファレンス資料

14. **`docs/reference/FUNCTION_REFERENCE.md`**
    - すべての関数・コマンドのリファレンス
    - 関数の使い方を調べる際に参照

15. **`docs/reference/QUERIES.md`**
    - よく使うSQLクエリ集
    - デバッグや調査で使用

16. **`docs/reference/IS_KNOWN_FLAG_EXPLANATION.md`**
    - `is_known` フラグの決定システム
    - 既知/未知判定のロジック

### 📊 `docs/results/` - テスト結果・実践結果

17. **`docs/results/ALERT_TEST_RESULT.md`**
    - アラート機能のテスト結果
    - Slack通知のテスト結果

18. **`docs/results/WORKFLOW_PRACTICE_RESULT.md`**
    - ワークフローの実践結果
    - 実際の運用での検証結果

## ドキュメントの読み方

### 初心者向け
1. `README.md` - プロジェクトの概要を理解
2. `EXECUTION_FLOW_CHECKLIST.md` - 実行フロー確認チェックリストで動作確認
3. `docs/guides/EXECUTION_FLOW.md` - 実際の操作手順を確認

### 開発者向け
1. `docs/reference/FUNCTION_REFERENCE.md` - 関数の使い方を確認
2. `docs/technical/DATABASE_ER_DIAGRAM.md` - データベース構造を理解
3. `docs/technical/WORKFLOW_IMPLEMENTATION_STATUS.md` - 実装の詳細を確認

### 機能別の詳細
- 手動パターン追加 → `docs/guides/MANUAL_PATTERN_GUIDE.md`
- 閾値チェック → `docs/guides/THRESHOLD_CHECK_EXPLANATION.md`
- LLM解析 → `docs/guides/LLM_IMPLEMENTATION_GUIDE.md`
- 異常判定 → `docs/technical/ABNORMAL_DETECTION_FLOW.md`
- パラメータ異常検知 → `docs/guides/PARAMETER_ANOMALY_DETECTION_WORKFLOW.md`

### クイックリファレンス
- SQLクエリ → `docs/reference/QUERIES.md`
- 関数リファレンス → `docs/reference/FUNCTION_REFERENCE.md`
- 既知/未知判定 → `docs/reference/IS_KNOWN_FLAG_EXPLANATION.md`

## ディレクトリ構造

```
final_creation/
├── README.md                          # プロジェクト概要
├── EXECUTION_FLOW_CHECKLIST.md        # 実行フロー確認チェックリスト
├── CHANGELOG.md                       # 変更履歴
├── DOCUMENTATION_STRUCTURE.md         # このファイル
└── docs/
    ├── guides/                        # ガイド・手順書
    │   ├── EXECUTION_FLOW.md
    │   ├── MANUAL_PATTERN_GUIDE.md
    │   ├── THRESHOLD_CHECK_EXPLANATION.md
    │   ├── LLM_IMPLEMENTATION_GUIDE.md
    │   ├── PARAMETER_ANOMALY_DETECTION_WORKFLOW.md
    │   └── LOG_PARAMS_VS_PATTERN_RULES.md
    ├── technical/                     # 技術詳細
    │   ├── DATABASE_ER_DIAGRAM.md
    │   ├── ABNORMAL_DETECTION_FLOW.md
    │   └── WORKFLOW_IMPLEMENTATION_STATUS.md
    ├── reference/                     # リファレンス
    │   ├── FUNCTION_REFERENCE.md
    │   ├── QUERIES.md
    │   └── IS_KNOWN_FLAG_EXPLANATION.md
    └── results/                       # テスト結果・実践結果
        ├── ALERT_TEST_RESULT.md
        └── WORKFLOW_PRACTICE_RESULT.md
```

## ファイルの更新履歴

- 2025-01-XX: ドキュメントを`docs/`ディレクトリ配下に整理
  - ガイド系 → `docs/guides/`
  - 技術詳細 → `docs/technical/`
  - リファレンス → `docs/reference/`
  - テスト結果 → `docs/results/`
  - `EXECUTION_FLOW_CHECKLIST.md`はルートに残す
