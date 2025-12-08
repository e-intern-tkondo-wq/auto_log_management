# ドキュメント構造ガイド

> このファイルで行うこと: プロジェクトのドキュメント構造と各ファイルの役割を説明します。

## ドキュメント階層

### 📘 メインドキュメント（必須）

1. **`README.md`**
   - プロジェクト全体の概要・セットアップ・基本的な使い方
   - 最初に読むべきファイル

2. **`EXECUTION_FLOW.md`**
   - ステップバイステップの実行手順
   - 実際の操作手順が詳しく書かれている

3. **`FUNCTION_REFERENCE.md`**
   - すべての関数・コマンドのリファレンス
   - 関数の使い方を調べる際に参照

### 📗 技術詳細ドキュメント

4. **`DATABASE_ER_DIAGRAM.md`**
   - データベーススキーマの詳細
   - ER図とテーブル定義

5. **`ABNORMAL_DETECTION_FLOW.md`**
   - 異常判定のフローとデータベース反映
   - パターン1（異常テンプレ）とパターン2（パラメータ異常）の説明

6. **`WORKFLOW_IMPLEMENTATION_STATUS.md`**
   - 5つのワークフローの実装状況
   - 各フローの実装箇所とコード例

### 📙 機能別ガイド

7. **`MANUAL_PATTERN_GUIDE.md`**
   - 手動パターン追加の手順
   - Named capture groupの使い方

8. **`THRESHOLD_CHECK_EXPLANATION.md`**
   - 閾値チェックの仕組み
   - パラメータ抽出とルール評価の流れ

9. **`LLM_IMPLEMENTATION_GUIDE.md`**
   - LLM自動解析機能の実装と使用方法
   - .envファイルの設定方法

### 📕 参考資料

10. **`QUERIES.md`**
    - よく使うSQLクエリ集
    - デバッグや調査で使用

11. **`IS_KNOWN_FLAG_EXPLANATION.md`**
    - `is_known` フラグの決定システム
    - 既知/未知判定のロジック

12. **`CHANGELOG.md`**
    - 変更履歴
    - 機能追加・修正の記録

## ドキュメントの読み方

### 初心者向け
1. `README.md` - プロジェクトの概要を理解
2. `EXECUTION_FLOW.md` - 実際の操作手順を確認

### 開発者向け
1. `FUNCTION_REFERENCE.md` - 関数の使い方を確認
2. `DATABASE_ER_DIAGRAM.md` - データベース構造を理解
3. `WORKFLOW_IMPLEMENTATION_STATUS.md` - 実装の詳細を確認

### 機能別の詳細
- 手動パターン追加 → `MANUAL_PATTERN_GUIDE.md`
- 閾値チェック → `THRESHOLD_CHECK_EXPLANATION.md`
- LLM解析 → `LLM_IMPLEMENTATION_GUIDE.md`
- 異常判定 → `ABNORMAL_DETECTION_FLOW.md`

## 削除・統合されたファイル

以下のファイルは内容を統合して削除しました：

- `PROGRESS_REPORT.md` → `WORKFLOW_IMPLEMENTATION_STATUS.md` に統合
- `IMPLEMENTATION_STATUS.md` → `WORKFLOW_IMPLEMENTATION_STATUS.md` に統合
- `MANUAL_PATTERN_FEATURE.md` → `MANUAL_PATTERN_GUIDE.md` に統合
- `DB_STATUS.md` → `DATABASE_ER_DIAGRAM.md` に統合
- `SLACK_NOTIFICATION_TEST_RESULT.md` → 削除（テスト結果は実装完了済み）
- `REQUIREMENT_COMPARISON.md` → 削除（古い比較情報）

