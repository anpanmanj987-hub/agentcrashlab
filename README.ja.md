# AgentCrashLab

### AIは「完了しました」と答えた。注文は2件できていた。

**ツール呼び出しに障害を注入し、AIの発言ではなく、実際の業務状態で成否を判定するOSSです。**

Python 3.11以上 / MIT / 実行時の外部依存なし / オフラインデモ / 実験的なv0.1

[English](README.md) · [連携仕様](docs/INTEGRATION.md) · [安全上の制約](SECURITY.md)

![実際に実行したHTTPデモ。単純な再試行では注文が2件、修正版では1件](docs/assets/demo.gif)

この画面は実行結果から生成しています。ただし比較する2種類のエージェントは、
説明用の決定的なPythonポリシーです。実際のLLMの性能比較ではありません。

## まず動かす

リポジトリ直下で、Python 3.11以上の仮想環境を使って実行します。

```bash
python -m pip install .
python -m agentcrashlab demo --transport http --open
```

**インストール不要の実行方法もあります。**

```bash
python scripts/demo.py --transport http --open
```

APIキー、LLMのダウンロード、Dockerは不要です。HTTPの模擬注文サービスは
`127.0.0.1`だけに一時的に立ち上がり、終了時に閉じます。レポートは単体HTMLで、
CDN・外部フォント・アクセス解析を使いません。パッケージをインストールする際の
ビルドツール取得には通信が必要な場合がありますが、デモ実行時には不要です。

本成果物を作成しただけではPyPIには公開されていません。
`pip install agentcrashlab`で別人の同名パッケージを取得せず、ソースか同梱wheelから導入してください。

## 再現する事故と検証結果

| ケース | 単純な再試行 | 冪等性キーを固定する修正版 |
|---|---|---|
| 正常系 | 合格・注文1件 | 合格・注文1件 |
| 注文成立後に応答喪失 | **不合格・注文2件** | 合格・注文1件 |
| 注文成立前のタイムアウト | 合格・注文1件 | 合格・注文1件 |
| 書き込み前に権限失効 | **不合格・注文0件なのに成功と報告** | 合格・停止したことを報告 |

単純版は「冪等性キーなしのリトライ」「失敗を使い切っても成功と報告する」という
2つの欠陥を意図的に含めています。修正版を使っても、一般的な安全性を保証するものではありません。

8項目の検証は、注文件数、注文内容・価格、合計金額、書き込み時の権限、虚偽の成功報告、
要求された最終状態、障害が実際に発生したか、ポリシーが正常に結果を返したかです。
何も実行しない、未発生の障害を試験済み扱いにする、例外を無視して合格にする、といった抜け道も検証します。

## コマンド

```bash
# 一覧・設定確認
agentcrashlab list
agentcrashlab show response-loss

# 不合格になる説明用ケース。終了コード1は想定どおり
agentcrashlab run response-loss --agent naive --output artifacts/broken

# 修正版。合格時は終了コード0
agentcrashlab run response-loss --agent resilient --transport http --output artifacts/fixed

# 証跡の整合性検証
agentcrashlab verify artifacts/fixed

# 記録されたツール呼び出しを新しいDBに対して再実行
agentcrashlab replay artifacts/fixed --output artifacts/replayed
```

`demo`だけは、意図した2件の不合格を含む比較結果が再現できれば終了コード0です。
個別の`run`と`replay`は、合格0、不合格1、設定・実行基盤のエラー2です。
`verify`の0は証跡の整合性が確認できたことを意味し、業務試験の合格とは異なります。
既存の出力先は上書きしません。再実行では新しい出力先を使ってください。

## 保存される証跡

シナリオJSON、実行結果JSON、イベントJSONL、実際に使ったSQLiteファイル、
JUnit XML、HTMLレポート、SHA256一覧を保存します。

リプレイは**保存された呼び出し列の再実行**です。元のLLMを再実行したり、
内部推論を再現したり、現実の注文を取り消したりする機能ではありません。
SHA256も改ざん不可能な署名ではなく、ファイルの破損検出用です。

## 自分のエージェントを接続する

`run_case(..., agent=自分の関数)`で、`tools`と`task`を受け取るPython関数を渡します。
その関数内で既存エージェントを呼び出し、注文ツールを`tools.create_order`に接続し、
エージェントが実際に返した状態を`AgentResult`で返してください。
[実行できる例](examples/custom_agent.py)と[連携仕様](docs/INTEGRATION.md)を用意しています。

この版は同期Python関数向けです。非同期フレームワークの変換、モデルの呼び出し回数制御、
コスト制限は利用側で実装します。ユーザーコードを安全に隔離するサンドボックスではありません。
本番の決済・注文・メール送信先などは接続しないでください。

## 公開・検証状況

GitHub上のリポジトリ: <https://github.com/anpanmanj987-hub/agentcrashlab>
[検証記録](docs/VERIFICATION.md)で、実測済みの内容と未検証の環境を確認できます。
[公開手順](docs/RELEASE.md)には、リリース作成やフォーク時の手順をまとめています。
PyPIには公開していません。

## 開発・ライセンス

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

MIT License。実験用の初期リリースです。合格しても本番の安全性や法令遵守を保証しません。
