# OESCR 検証図・最適化図の読み方とベンチマーク妥当性

## 結論

NF3/Ar と Cl2/Ar の図で、`Initial` スペクトルが最初から `Measurement` に近く見えるという指摘は正しい。現状の二ケースは、次の目的には適切である。

- forward model、測定読込、窓選択、目的関数、global/local optimizer、結果出力が一つの経路として動くことの確認
- 真値から中程度にずらした状態量を、同じ forward model で生成した観測からどこまで回収できるかという自己整合性確認
- ノイズ、波長ずれ、gain、baseline、複数 chord を含む回帰試験

しかし、次の主張を単独で支えるベンチマークとしては不十分である。

- 事前知識のない遠い初期値から常に正解へ収束する
- optimizer が初期値や乱数 seed に依存しない
- 実験プラズマの電子温度、電子密度、EEDF、種密度を物理的に正しく予測する
- forward model の不足や断面積の系統誤差があっても正しい解を得る

したがって従来の `optimization-figures` に対する正確な呼び方は、**生成データによる自己整合性・workflow benchmark** である。**optimizer robustness benchmark** や **外部物理妥当性 benchmark** ではない。遠方初期値用には役割を混ぜず、別の [`robustness-figures`](robustness-figures/) と[評価報告](optimization_robustness_benchmark.md)を追加した。

なお、図の橙線 `Initial` は「global optimizer が最初に評価した点」ではない。これは `case_init.yaml` で定義した比較用の基準予測である。NF3/Ar と Cl2/Ar の実際の global 段階は differential evolution であり、設定 bounds 全域に生成した集団から開始する。最適化履歴の最初の点と橙線は別物である。

## 1. 二つの図ディレクトリの役割

| ディレクトリ | 主な問い | 表示内容 | 主な利用者 | 証明できる範囲 |
|---|---|---|---|---|
| [`validation-figures/`](validation-figures/) | 計算結果は目標値・観測・既知真値と合っているか | 解析解との比較、複数 chord のスペクトル、波長別残差、半径方向 profile | 物理モデルと最終結果を評価する人 | 前向き計算の保存則、生成観測の再現、生成真値の回収度 |
| [`optimization-figures/`](optimization-figures/) | optimizer は何を探索し、どこへ収束したか | 未知変数、固定変数、EEDF、Loss履歴、評価点、並行座標 | 逆問題とoptimizerを評価する人 | 探索経路、収束挙動、低Loss領域、推定対象と固定入力の区別 |
| [`robustness-figures/`](robustness-figures/) | 遠方初期値から seed に依存せず held-out chord と真値を回収できるか | 未使用 spectrum、全 seed の parameter/truth、実 Loss 履歴、versioned 閾値 | 逆問題の頑健性と同定性を評価する人 | 現行パラメータ化の内部頑健性。外部物理精度ではない |

両ディレクトリには同じ NF3/Ar、Cl2/Ar、二バンド問題が現れるため、一部のスペクトルは重複して見える。しかし役割は異なる。

- `validation-figures` は **結果中心** である。スペクトル残差と生成真値への回収を読み取る。
- `optimization-figures` は **過程中心** である。探索点、Loss、bounds 内の位置、推定した量と固定した量を読み取る。
- 片方だけでは不十分である。スペクトル一致だけではパラメータの一意性が分からず、Loss低下だけでは物理量が正しいか分からない。

## 2. 全図に共通する凡例と用語

### Measurement

optimizer に与えた観測値である。二バンド、NF3/Ar、Cl2/Ar は OESCR の truth case から作成した生成データであり、実験 raw spectrum ではない。NF3/Ar と Cl2/Ar には固定 seed のノイズ、gain、baseline、波長ずれを加えている。

### Initial

`case_init.yaml` から計算した基準予測である。最適化前に人が与える nominal state を表すが、differential evolution の最初の評価点を表さない。

### Optimized

設定された目的関数を最小にしたパラメータから再計算した予測である。観測へ近いことは必要条件だが、物理量が真値に近いことの十分条件ではない。

### Known truth

生成観測を作るときに使用した `case_truth.yaml` の値である。実験データでは通常この線は存在しない。truthとの比較は生成benchmarkだけで可能である。

### Loss

現在の図のLossは、単純なスペクトル二乗誤差だけではない。設定に応じてスペクトル残差、窓の面積・peak、line ratio、gain prior、パラメータ prior、平滑化を含む。したがって次に注意する。

- 異なるケースのLoss絶対値を比較しない。残差数と重みが違う。
- Lossが下がっても、すべての物理量が正しくなったとは限らない。
- ノイズとpriorがあるため、生成truthが目的関数の厳密な最小点になるとは限らない。

### Value / known truth

`1.0` が生成真値である。例えば `0.85` は真値より15%低い。橙から青が `1.0` に近づけば、その変数の回収は改善したと読む。

### EEDF

現在の最適化図のEEDFは自由形状を直接推定した結果ではない。`plasma_mode: te` と Maxwell 分布を仮定し、推定または固定した電子温度から導出している。

- NF3/Ar: 電子温度を推定するため、EEDFも間接的に変化する。
- Cl2/Ar: 電子温度を固定しているため、EEDFは予測結果ではなく固定入力からの派生量である。
- 二バンド: 電子温度とEEDFは固定入力である。

## 3. 初期スペクトルが近い問題の定量評価

### 3.1 NF3/Ar

9個の推定変数の初期値は、生成真値に対して約7.1–23.5%低い。目的関数は次のように変化した。

| 評価点 | Loss |
|---|---:|
| `case_init.yaml` の基準値 | `210.744` |
| 生成truth | `201.856` |
| 最適化結果 | `199.242` |
| global探索の最初の実評価点 | `2376.463` |
| global探索内の最小値 | `212.464` |

基準値から最適値へのLoss改善は `5.46%` である。橙線が既に観測へ近いという視覚的印象と整合する。一方、global探索の最初の実評価点は大きく離れており、792回のglobal評価後にlocal least-squaresへ渡している。つまり、**表示された基準値は近いが、実際のglobal探索はその一点から局所的に開始していない**。

最適化後の相対誤差は、電子温度 `-7.5～-9.5%`、F密度 `-9.5～-14.8%`、N2 emitter proxy `-11.4～-23.5%` である。スペクトルがほぼ重なっても状態量が完全には回収されないことは、逆問題の縮退を示している。

### 3.2 Cl2/Ar

6個の推定変数の初期値は、生成真値に対して約6.7–22.2%低い。目的関数は次のように変化した。

| 評価点 | Loss |
|---|---:|
| `case_init.yaml` の基準値 | `349.354` |
| 生成truth | `348.627` |
| 最適化結果 | `348.088` |
| global探索の最初の実評価点 | `377.317` |
| global探索内の最小値 | `348.234` |

基準値から最適値へのLoss改善は `0.36%` しかない。したがってこのケースについては、optimizerが観測を大幅に改善したというより、**最初から同程度に説明できる近傍で、種密度profileを微調整した**と解釈するのが正しい。

Cl2/Arでは電子温度と電子密度を推定していない。図に表示されるtruthとの差は、optimizerの失敗ではなく、固定入力と生成truthの差である。

### 3.3 近く見える理由

1. `case_init.yaml` は `case_truth.yaml` を `include` し、一部の状態量だけを上書きしている。このため、上書きしていないモデル構造、線位置、profile、装置条件などはtruthと共通である。
2. 観測は同じOESCR forward modelから生成している。forward model discrepancyが存在しない inverse crime 型の自己整合性試験である。
3. NF3/Ar と Cl2/Ar は `relative_shape` であり、自動gainとoffsetをfitする。絶対振幅差の一部はnuisance parameterに吸収される。
4. 図Aは測定peakで正規化している。絶対振幅差より、線形状と相対line ratioが強調される。
5. Cl2/Arの発光成分は固定形状のempirical effective emitterである。密度を変えても主に各固定profileの振幅が変わるため、近い初期密度ならスペクトル形状も近い。
6. priorの中心は初期値と同じである。これは独立な事前知識を模した設定だが、生成benchmarkとしては初期近傍を有利にする。

### 3.4 妥当性判定

| 評価目的 | 現行ケースの適否 | 理由 |
|---|---|---|
| forward/inverseの接続確認 | 適切 | 入力から観測比較、最適化、出力までを通せる |
| 真値近傍での局所回収 | 適切 | 初期値とtruthの差、回収量を直接比較できる |
| global探索コードがboundsを探索すること | 条件付きで適切 | 実traceは広い候補を含むが、seedは各ケース1個だけ |
| 初期値非依存性 | 不適切 | 遠方・境界・複数random startの成功率を評価していない |
| optimizer間の性能比較 | 不適切 | 比較optimizer、計算予算統一、反復試験がない |
| 外部物理精度 | 不適切 | 観測が同じforward modelから生成されている |
| 電子密度推定 | 二バンドabsoluteのみ | NF3/Ar、Cl2/Arでは固定入力 |
| 電子温度・EEDF推定 | NF3/Arで限定的 | Maxwell族内のTe推定であり、自由EEDF推定ではない |

## 4. `validation-figures` の読み方

### 4.1 解析前向き計算

図: [`01_analytic_forward_reproduction.png`](validation-figures/01_analytic_forward_reproduction.png)

**問い:** OESCRが計算したスペクトルを波長積分したとき、入力係数から独立に計算した解析目標値と一致するか。

- A: 500 nmの単一電子衝突光子bandの分光放射輝度。
- B: Aを短波長側から累積積分した値。青が黒破線の解析目標へ収束するかを見る。
- C: 500 nm bandと600 nm原子線を同時に計算したスペクトル。
- D: Cの累積積分。500 nmで一段上がり、600 nmで二段目が加わる。

**評価:** 最終積分の相対誤差は単一band `7.21e-7`、band+原子線 `6.33e-7` である。放射強度の組立て、line profile正規化、波長積分が解析式と整合している。

**意味しないこと:** 実ガスの断面積や励起kineticsが正しいこと、実験スペクトルを再現できることは示さない。

### 4.2 二バンド逆解析

図: [`02_two_band_inverse_recovery.png`](validation-figures/02_two_band_inverse_recovery.png)

**問い:** 最小構成のratio/actinometry/absolute inverseが、既知の一変数を回収できるか。

- A: 500 nm Targetと510 nm Actinometerの比からTarget密度を推定する。橙は真値の50%から開始する。
- B: 絶対校正スペクトルから電子密度を推定する。橙は真値の50%から開始する。
- C: Target密度が `1.0e18` からtruth `2.0e18 m-3` へ回収されたことを示す。
- D: 電子密度が `1.5e16` からtruth `3.0e16 m-3` へ回収されたことを示す。

**評価:** 一変数、同一model、固定Te、既知source密度、理想的な絶対校正という閉じた問題では数値的にtruthを回収する。初期振幅は観測の約半分であり、NF3/ArやCl2/Arより初期差が明瞭である。

**意味しないこと:** 多変数の非一意性、model discrepancy、実験校正誤差、断面積誤差に対する頑健性は示さない。

### 4.3 NF3/Ar生成benchmark

図: [`03_nf3_spectral_fit_and_recovery.png`](validation-figures/03_nf3_spectral_fit_and_recovery.png)

**問い:** 複数chordの生成F Iスペクトルをfitしたとき、半径方向のTe、F、N2 emitter proxyをどこまで回収できるか。

- A–C上段: 中心、中央、外側chordのF I 685.6/703.7/712.8 nm領域。
- A–C下段: `prediction - measurement` を各windowの測定peakに対する百分率で表示する。0に近く、波長依存の系統形状が小さいほどよい。
- D: 電子温度profile。
- E: F密度profile。
- F: N2 emitter proxy profile。

**評価:** optimizedは特に外側chordの残差を低減するが、truth profileを完全には回収しない。スペクトル一致とパラメータ一致が同義でないことを示す。D–Fでは青が黒へどれだけ近づいたかを主に評価し、上段の曲線の重なりだけで合格としない。

**注意:** `N2_emit` はN2総密度ではなく、effective bandを駆動する発光proxyである。電子密度は推定していない。

### 4.4 Cl2/Ar生成benchmark

図: [`04_cl2_spectral_fit_and_recovery.png`](validation-figures/04_cl2_spectral_fit_and_recovery.png)

**問い:** Cl2 band、Ar II/Cl II、Cl I/Xe Iを用いたrelative-shape fitから、ClとCl2 emitter proxyの半径方向分布をどこまで回収できるか。

- A: 300–312 nmのCl2 molecular band。baseline補正後の信号がnoiseに対して弱く、点が大きく散る。
- B: 478–484.5 nmのAr II/Cl II doublet。
- C: 818–832 nmのCl I/Xe I領域。
- 各下段: 波長別残差。0周辺へランダムに散ればよく、peak位置に同符号の構造が残ればline amplitudeまたはshapeの不足を疑う。
- D: Cl密度profile。
- E: Cl2 emitter proxy profile。

**評価:** B、Cの主要line形状は再現する。Aはnoise優勢で拘束力が弱い。D、Eではoptimizedがtruthへ近づくが、Cl2 emitter内側shellには約13–16%の過小推定が残る。

**注意:** Te、ne、EEDFはこのケースでは推定していない。Cl2 306 nmの弱いwindowを視覚的にfitできたように見せることより、signal-to-noiseとparameter recoveryを優先して評価する。

## 5. `optimization-figures` の読み方

### 5.1 二バンド最小逆解析

図: [`01_two_band_optimization_diagnostics.png`](optimization-figures/01_two_band_optimization_diagnostics.png)

- A: optimizerに与えた二bandスペクトルと初期・最終予測。
- B: Target密度と電子密度の初期値、最終値、truth。各値は別のinverse modeで一変数ずつ推定する。
- C: Teは固定、neはabsolute modeだけで推定したことを明示する。
- D: 固定Teから導出したMaxwell EEDF。推定結果ではない。
- E: 実際のlocal objective評価に対するbest-so-far Loss。単調に下がる青線を見る。
- F: 一変数の評価点とLoss地形。横軸 `1.0` がtruth、縦軸は最初の評価Lossで正規化している。

**評価:** 初期値がtruthの50%でも一変数解を回収できる。これはAPIと目的関数の最小契約試験として強いが、多変数optimizerの頑健性試験としては単純すぎる。

### 5.2 NF3/Ar最適化診断

図: [`02_nf3_optimization_diagnostics.png`](optimization-figures/02_nf3_optimization_diagnostics.png)

- A: 中央chordのF I領域。peak正規化と自動gain適用後なので、絶対振幅差ではなく形状・line ratioを見る。
- B: 9個の未知変数。橙から青への移動と、黒点線 `1.0` への接近を読む。
- C: Teは推定したが、neは固定したことを示す。灰色のneがtruthへ近づかないのはoptimizerの失敗ではない。
- D: 中心shellの推定Teから導出したMaxwell EEDF。平均エネルギーはtruth `4.14 eV`、初期 `3.54 eV`、最終 `3.75 eV`。
- E: 863個の実評価点。灰色がglobal、橙がlocal、青がbest-so-far、星が最小Lossである。縦点線より右がlocal段階。
- F: bounds内で正規化した並行座標。青い低Loss経路が広い場合、複数の組合せが似たLossを与える。黒実線と黒点線のずれは、最小Loss点とtruthが異なることを示す。

**評価:** global探索後にLossは低下するが、低Loss候補はTe–Fの複数方向へ広がる。条件数 `3.15e6` と合わせ、強い悪条件性を示す。スペクトルの重なりを9変数の高精度同定と解釈しない。

### 5.3 Cl2/Ar最適化診断

図: [`03_cl2_optimization_diagnostics.png`](optimization-figures/03_cl2_optimization_diagnostics.png)

- A: 中央chordのAr II/Cl IIとCl I/Xe I。絶対scaleではなくrelative shapeを表示する。
- B: 6個の未知密度の初期・最終・truth比。
- C: Teとneはいずれも固定入力である。
- D: 固定Teから導出したMaxwell EEDF。optimized曲線がないのは意図的である。
- E: 816個の実評価点とbest-so-far Loss。
- F: 6変数の並行座標。NF3/Arより低Loss経路が狭く、局所条件数 `59.5` と整合する。

**評価:** 探索は安定しているが、初期Lossと最終Lossの差はわずか `0.36%` である。これは「困難な初期値から救済した」結果ではなく、「近い基準解を同じmodel内で調整した」結果である。

## 6. 第三者が図を評価する順序

1. **推定対象を確認する。** 固定量を予測結果として扱わない。
2. **観測が実験か生成かを確認する。** 現行の二バンド、NF3/Ar、Cl2/Ar図は生成観測である。
3. **スペクトルの軸を確認する。** peak正規化、baseline補正、auto gainがある場合、絶対振幅の正しさは評価できない。
4. **波長別残差を見る。** 曲線の重なりだけでなく、line位置に系統残差が残っていないかを見る。
5. **パラメータ回収を見る。** truthがある場合は `optimized / truth` を確認する。
6. **Loss履歴を見る。** best-so-farが十分下がり、globalからlocalへの移行後に改善があるかを見る。
7. **並行座標とidentifiabilityを見る。** 低Loss経路が広い場合、最良一点だけを信頼しない。
8. **主張範囲を限定する。** 生成自己整合性、外部物理精度、固定入力からの派生量を区別する。

## 7. optimizer robustness benchmarkの実施結果

2026-10-01 に、従来図を自己整合性 baseline として保持したまま、別の厳しい層を追加した。遠方・非単調初期値、truth-near parameter prior なし、seed 7/19/43、chord 0–3 fitting、chord 4 held-out、training Loss のみによる run 選択、version 2 で固定した parameter/held-out tolerance を使用した。評価器 version 1 の noisy pointwise NRMSE にあった noise-floor と固定成分混入の問題は、optimizer 出力を変更せず noise-free truth-spectrum NRMSE へ修正した。

結果は NF3/Ar、Cl2/Ar とも **FAIL** である。Loss は数値的に収束したが、seed 間で異なる shell 分布が同程度の Loss を与え、held-out spectrum と真値パラメータを同時に回収できなかった。詳細な設定、図、数値、解釈は[遠方初期値からの最適化頑健性ベンチマーク](optimization_robustness_benchmark.md)に固定している。

したがって現行図に対して「広い初期条件から頑健に成功した」という表現は用いない。次の内部検証は、探索予算の増加ではなく、measurement-only Jacobian が支持する低次元 profile parameterization を導入し、同じ初期値・seed・分割・閾値で再実行する。

なお、次の項目は optimizer 内部頑健性とは別の外部物理検証として未完了である。

1. auto gain/offset を使う shape 評価と、絶対校正を固定した amplitude 評価を別ケースにする。
2. truth 生成器と inverse forward model を意図的に変え、line shape、断面積、baseline の model discrepancy を加える。
3. 実験 benchmark を外部 evaluator で評価し、OESCR 内部の同一数値核による自己採点と分離する。

## 8. 証拠ファイルと再生成

| 内容 | ファイル |
|---|---|
| 図の生成コード | [`generate_validation_figures.py`](../scripts/generate_validation_figures.py)、[`generate_optimization_diagnostic_figures.py`](../scripts/generate_optimization_diagnostic_figures.py)、[`generate_robustness_benchmark_figures.py`](../scripts/generate_robustness_benchmark_figures.py) |
| NF3/Ar初期値・truth・bounds・prior | [`case_init.yaml`](../examples/benchmarks/nf3_ar_ccp_clean_2023/case_init.yaml)、[`case_truth.yaml`](../examples/benchmarks/nf3_ar_ccp_clean_2023/case_truth.yaml)、[`inverse.yaml`](../examples/benchmarks/nf3_ar_ccp_clean_2023/inverse.yaml) |
| Cl2/Ar初期値・truth・bounds・prior | [`case_init.yaml`](../examples/benchmarks/cl2_ar_icp_fuller2001/case_init.yaml)、[`case_truth.yaml`](../examples/benchmarks/cl2_ar_icp_fuller2001/case_truth.yaml)、[`inverse.yaml`](../examples/benchmarks/cl2_ar_icp_fuller2001/inverse.yaml) |
| 全パラメータの回収値 | [`parameter_recovery.csv`](optimization-figures/parameter_recovery.csv) |
| 遠方初期値 benchmark | [`optimization_robustness_benchmark.md`](optimization_robustness_benchmark.md)、[`robustness_summary.csv`](robustness-figures/robustness_summary.csv) |
| 詳細な物理検証 | [`physical_validation_report.md`](physical_validation_report.md) |
| モデル式と根拠 | [`model_methods_and_validation.md`](model_methods_and_validation.md) |

図の再生成手順は [`optimization_diagnostics.md`](optimization_diagnostics.md) と [`physical_validation_report.md`](physical_validation_report.md) に記載している。`.local_outputs/` のtraceは生成物でありGit管理対象外だが、公開PNGと `parameter_recovery.csv` はGit管理する。
