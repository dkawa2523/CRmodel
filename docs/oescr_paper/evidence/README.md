# 数値実験の根拠と再現

本ディレクトリは論文図表の数値、標準結果、実行記録、検証に用いたソースの固定コピーを保存する。解析解との保存則確認を除き、測定入力はすべて同じ前向きモデルから生成した数値fixtureである。実測に対する電子温度・電子密度の精度を示す資料ではない。

## 読む順序

- `benchmark_metrics.json`: 図表に使った解析保存則、最小inverse、共通状態、六kernel、複数視線の値。
- `common_state_parameter_recovery.csv` / `common_state_summary.yaml`: 共通Te/ne回復とholdout。Ar/Cl2の既定回復ゲートはFAILである。
- `exported_spectral_metrics.csv`: 保存済み予測から独立に集計した非重み付き相対L2。最適化の目的関数値とは定義が異なる。
- `two_band_recovery.csv`: 無ノイズ生成値からの比・actinometry・絶対強度の数値回復。
- `ar_six_kernel_summary.yaml` / `ar_kernel_sensitivity.csv`: 固定neでの共有Maxwellian有効Te回復。六kernelはすべてvalidation_candidate。
- `multichord_parameter_recovery.csv`: 事前分布と平滑化を使うempirical多視線例。`N2e` / `Cl2e` は有効発光源密度であり、自己無撞着に計算した全分子密度ではない。
- `results/`: 各caseの標準 `result.yaml`、最適case、識別可能性、profile、局所曲率。case内の絶対パスは記録した実行ディレクトリを指すため、他のPCでは再実行で生成し直す。
- `run_execution.json` / `run_manifest.json`: コマンド、exit status、環境、入力hash。経過時間は並列実行の記録であり、制御された性能比較ではない。
- `source_snapshot.zip` / `source_snapshot_manifest.json`: 未コミットの実装と入力を含む固定source。git HEADだけでは実行時の内容を表せないため、archiveと全ファイルのSHA256を保存した。

CSVの `relative_error` / `relative_l2` は0–1の比率であり、本文の百分率は100倍した値である。図のprofileは測定のみの条件付き目的関数差であり、校正済み信頼区間ではない。図内の半径shellは中心から壁へ1,2,3である。

## 再実行

現在のリポジトリで再計算する場合は、Python 3.10以上の環境で以下を実行する。

```powershell
python -m pip install -e ".[dev]"
python docs/oescr_paper/reproduce/run_benchmarks.py
```

この操作は測定fixtureを書き換えず、`.local_outputs/paper_benchmarks/` に結果を生成する。続けて図と根拠CSVを生成する。NF3とCl2の長いempirical fitを省く場合は `--skip-multichord` を指定する。ただし、その場合は既存出力があれば図に再利用されるため、完全な再現には省略しない。

論文の数値を同じソースから再現する場合は、`source_snapshot.zip` を新しい空ディレクトリへ展開し、その場所を作業ディレクトリとして使う。archive内にも同じ `docs/oescr_paper/reproduce/` の実行スクリプトが入っている。環境に依存した数値微差はあり得るため、全桁一致と科学的な一致を区別する。archiveのhashはmanifestと照合できる。

共通状態runnerが終了code1になるのは、保存済みAr/Cl2生成fixtureの回復誤差とholdoutが設定済み閾値を満たさないためである。後続の実験はこの結果を記録して継続する。最適化自体の収束と回復ゲートの合否を混同しない。

今回の凍結source再実行では、既存の対象テスト106件がすべてPASSした（pytest記録9.09秒）。対象は `test_cr_analytic.py`、`test_spectral_sampling.py`、`test_model_contracts.py`、`test_argon_six_kernel_candidate.py`、`test_common_state_benchmarks.py`、`test_use_case_examples.py` である。全テストsuiteの合格や外部実験精度の証明とは区別する。凍結sourceの実行前後hash一致と、ライブ作業ツリーからの分離は `run_manifest.json` の `source_hashes_unchanged_through_run` と `execution_isolated_from_live_workspace` がともにtrueであることを確認した。

## CSV/YAMLから図までの経路

`run_benchmarks.py` は各runnerを実行した後、同じディレクトリの `make_benchmark_figures.py` を実行する。この図生成スクリプトだけを再実行する場合は、リポジトリルートから以下を使う。

```powershell
python docs/oescr_paper/reproduce/make_benchmark_figures.py
```

読み込む根拠は `.local_outputs/paper_benchmarks/` の標準result、監査YAML、`spectra/*.csv`、`audit_spectra/*.csv`、profile CSVである。解析保存例と共通状態の雑音なし真値は、同じ固定ソースと入力caseで前向き計算する。図と同時に、使用した数値を本ディレクトリのCSV/JSONへ書き出す。したがって、`evidence/` だけを残してruntime出力を削除した場合は、上のfull runnerで標準結果を再生成してから図生成を実行する。

| 図 | 主な保存数値 |
|---|---|
| `benchmark_analytic` | `analytic_conservation.csv`, `analytic_spectrum.csv` |
| `benchmark_common_state` | `common_state_summary.yaml`, `common_state_parameter_recovery.csv`, `ar_o2_o777_spectrum.csv`, `ar_cl2_cl755_spectrum.csv`, 各temperature_profile CSV |
| `benchmark_ar_six_kernel` | `ar_six_kernel_summary.yaml`, `ar_kernel_sensitivity.csv`, VIS/NIR spectrum CSV |
| `benchmark_multichord` | `multichord_parameter_recovery.csv`, `nf3_central_spectrum.csv`, `cl2_central_spectrum.csv` |

## 外部資料の出典表示

六つのAr励起曲線はAnthony SchmalzriedのZenodo record 8192503（DOI: [10.5281/zenodo.8192503](https://doi.org/10.5281/zenodo.8192503)）から選択したCC BY 4.0の表である。archive内の `examples/data/cross_sections_external/argon_zenodo_8192503/README.md` と `manifest.yaml` に、作成者、DOI、license URL、原本hash、抽出・形式変換の内容を保持した。数値行の補間や平滑化はしていない。NISTの放射分岐はspecies pack内の出典・版・取得日・波長medium情報を保持している。curated曲線には、文献に基づく初期値用curveと例示的synthetic effective emitterの区分を各CSVおよびmanifestに残した。

archiveはソース、CSV、YAML、JSON、READMEを収録し、BOLSIG+実行binaryや `.local_outputs/` の外部ダウンロード原本を含まない。参考文献に基づくデータの出典表示を、物理的な適用範囲の資格化と混同しない。

## 印刷時の可読性に関する表示更新

最終PDFで図を幅16cmに挿入したときに文字が小さくならないよう、図の表示部分だけを更新した。最終図のPDF幅は7.0in（504pt）に固定し、元図の最小文字サイズを10.3ptとした。このため幅16cmで挿入したときの最小文字は約9.27ptとなる。解析例は7.0×3.1in、六kernel例は7.0×5.9in、多視線例は7.0×5.8inである。

共通状態の図は7.0×8.2inの3行2列へ配置し、(a)Ar/O2回復、(b)Ar/O2温度profile、(c)Ar/Cl2回復、(d)Ar/Cl2温度profile、(e)O777のfitスペクトル、(f)Cl755のholdoutスペクトルとした。観測値・計算値・判定・profile値は変更していない。表示更新の前後で、本ディレクトリの数値根拠ファイル全件のSHA256一致を確認した。

固定した数値計算ソースのarchiveとhashは更新していない。そのためarchive内の図生成スクリプトは旧配置を保持する。本稿の最終配置を再現する際は、archive展開後に、外側の `reproduce/make_benchmark_figures.py` を展開先の同じ位置へコピーしてから図生成を行う。この差は図のサイズ、文字、凡例、パネル配置だけであり、物理モデルやベンチマーク数値の変更ではない。

## 図と指標

`../figures/benchmark_analytic.pdf` は600nm原子線と500nmバンドの重ね合わせおよび積分保存則、`benchmark_common_state.pdf` は共有状態の回復・代表線・測定のみprofile、`benchmark_ar_six_kernel.pdf` は二広帯域channelと感度、`benchmark_multichord.pdf` は5視線・3shellのempirical例を示す。PNGは同じ図の視覚確認用である。

L2の定義は `sqrt(sum((prediction-reference)^2)/sum(reference^2))`。共通状態runnerのfit指標は選択されたチャネルの全画素を集計し、`exported_spectral_metrics.csv` の `selected_spectral_relative_l2` は実際のfit pixel maskだけを集計する。端の画素の取り扱いにより微差が生じる。六kernelのscore standardized RMSEは `sqrt(mean(((prediction-measurement)/sigma)^2))` であり、L2とは別の無次元量である。

最終PDFのページ数・埋込フォント・文字抽出・版面確認・SHA-256は `document_quality.json` に記録する。

## 理論解説の改訂と追加の実装確認

改訂版は、各機能の入力・計算・用途を先に説明し、第6章に機能群、処理フロー、数値解法、設計上の工夫を加えた。第7章を数値検証、第8章を現行機能・実測評価・計算核の拡張課題として整理している。既存26式と77件の数値根拠ファイルは、改訂前の記録と一致する。新章では、台形積分、区分線形の累積面積と画素平均、共通校正誤差の白色化を4式で説明する。

計算計画の再利用、反復と最終診断の分離、校正group、識別可能性、profileに関する既存テストを保存ソースから追加実行し、43件の成功を確認した。対象と結果は `implementation_checks.json` に保存する。これは元のベンチマークの106件とは別の確認である。

計算フロー図は `../reproduce/make_computation_flow.py` が生成する。ベンチマーク図と数値は既存の記録を維持し、新図は処理の接続を表す図として独立に管理する。最終PDFの32ページ、30式、5図、12文献、フォント埋込と版面確認は `document_quality.json` に対応する。
