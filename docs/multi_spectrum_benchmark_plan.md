# 単一条件から複数ガス・複数スペクトル検証へ

更新日: 2026-10-01

## 結論

現在の NF3/Ar と Cl2/Ar の生成ベンチマークは、それぞれ5視線を持つが、
物理的には1つの運転条件から生成した空間分布である。Ar 外部候補は圧力系列を
持つものの、主な比較量は2本の線の比であり、完全なスペクトル系列ではない。
したがって、現状だけでは次を検証できない。

- power、pressure、混合比が変わったときも同じ原子・分子モデルが成立するか;
- 純ガスから混合ガスへ移ったときの線干渉と相対感度を分離できるか;
- 装置、日、測定sessionが変わっても前処理と推定が再現するか;
- OESから得た状態量が、probe、吸収、質量分析など独立診断と一致するか;
- 仮定した Maxwell / Druyvesteyn / bi-Maxwell EEDF だけでなく、外部
  Boltzmann solver の非Maxwell EEDFを正しく積分できるか。

この不足を埋めるため、検証を1つの巨大な合否へ統合せず、次の3群へ分ける。

1. **X: 外部数値基準** — LXCat断面積とBOLSIG+でEEDF・速度係数を作り、
   OESCRのtabulated-EEDF積分を検証する。
2. **S: 複数実測スペクトル** — 多数の運転条件、gas mixture、日、sessionを使い、
   spectrum形状、線比、未使用波長窓、装置再現性を検証する。
3. **Q: 独立物理量** — Langmuir probe、TDLAS、質量分析、吸収測定を正解側に置き、
   Te、ne、準安定密度、解離率、radical密度を検証する。

XやSの合格をTe/ne精度の証明へ読み替えない。Qに独立診断がない場合は、
OES由来のTe/neを同じOESで再現しても外部物理検証とは数えない。

機械可読な候補、最小condition数、split、claim境界は
[`benchmark_portfolio.yaml`](../examples/validation/benchmark_portfolio.yaml) に固定した。

## 1. 現在のベンチマークが少ない理由

### 1.1 「5視線」は「5つの独立プラズマ条件」ではない

現行 NF3/Ar、Cl2/Ar packageの chord 0--4 は、同じtruth caseの異なる視線である。
これは視線積分と空間parameterの可観測性には有用だが、gas組成、pressure、power、
EEDF形状、装置応答の外挿を検証しない。独立単位はCSV数ではなく、**運転条件group、
測定日、または独立experiment session** とする。

### 1.2 1条件の最適化成功はmodel選択を検証しない

1つのスペクトルに対して振幅、密度、gainを調整すると、誤った励起断面積や欠落した
経路をcondition固有parameterが吸収できる。複数conditionでは、atomic data、
cross section、branching、instrument responseを全conditionで固定し、変えてよい
plasma-state parameterだけを明示できる。この固定性がOESCRモデル検証の中心である。

### 1.3 full spectrum数が多いだけでも不十分

大量データにTe、ne、radical densityの独立測定がなければ、測定スペクトルを説明する
parameterが真のplasma stateかは分からない。大量full-spectrum datasetはS群、
probeや吸収を持つ小さなdatasetはQ群として相補的に使う。

## 2. 共通問題設定

condition $c$、波長bin $k$ の観測を

$$
y_{c,k}=\mathcal H_c\!\left[
  \mathcal G_c\!\left(\mathcal E(\mathcal C(\theta_c;\phi))\right)
\right]_k+b_{c,k}+\epsilon_{c,k}
$$

とする。ここで $\theta_c$ はTe、ne、入力密度などconditionごとの量、
$\phi$ は断面積、branching、quenching、line profileなど全conditionで共通に固定する
model dataである。装置応答 $\mathcal H_c$ はlamp校正またはdataset固有metadataから与え、
同じspectrumへ自由な高次gain曲線をfitしない。

### 2.1 3種類のhold-out

| hold-out | 目的 | 規則 |
|---|---|---|
| 波長窓 | 未使用線・bandを予測できるか | fit窓とscore窓をspeciesとtransition単位で分離する |
| 運転条件 | pressure、power、混合比で共通model dataが保たれるか | frameではなくsetpoint groupを丸ごと分離する |
| 日・session | calibration driftや再現性に耐えるか | BOSCHはday、N2 leakはsessionを丸ごと分離する |

parameter mappingを持たないOESCRに、process setpointから未知stateを予測するsurrogateを
暗黙に追加しない。独立state入力のないcondition hold-outでは、未知stateの予測ではなく、
共通model dataを固定した上で各conditionの未使用波長窓をscoreする。

### 2.2 合否の決め方

大量実測datasetでは、repeat frame間の差を基準にする。condition $c$ における
spectrum model error $E_{\mathrm{model},c}$ とrepeatability
$E_{\mathrm{rep},c}$ を同じ正規化で計算し、pilot前に係数を固定する。最初の提案値は

$$
E_{\mathrm{model},c}\le 3E_{\mathrm{rep},c}
$$

である。絶対校正がないdatasetではshapeとratioだけを評価し、scale誤差を合否に混ぜない。
独立reference $q_c^{\mathrm{ref}}$ を持つTe、ne、densityについては

$$
z_c=\frac{|q_c^{\mathrm{OESCR}}-q_c^{\mathrm{ref}}|}
{\sqrt{u_{c,\mathrm{OESCR}}^2+u_{c,\mathrm{ref}}^2}}
$$

を用い、少なくとも80%のconditionで $z_c\le2$、かつpressure、power、mixtureに対する
一方向の残差傾向がないことを初期gateとする。reference uncertaintyがないpaperはこの
Q-gateを実行せず、trend比較に留める。

外部数値基準では、BOLSIG+が出力した $f_E(E)$ と同じLXCat processをOESCRへ入力し、

$$
k_r=\int\sigma_r(E)\sqrt{\frac{2eE}{m_e}}f_E(E)\,dE
$$

を比較する。十分に非零な速度係数について相対差1%以下、EEDF正規化誤差
$10^{-6}$ 以下を事前gateとする。near-zero rateは相対誤差から除外し、絶対誤差と
support coverageを別記する。

## 3. 優先順位付きベンチマーク

### P0-X1: LXCat + BOLSIG+ 外部EEDF・速度係数系列

**目的**: userが取得したLXCatを実際に使い、OESCR内部で生成したMaxwell EEDFを正解に
しない数値検証を作る。

- external solver: 公式BOLSIG+ 07/2024 console版`bolsigminus`。OESCR packageからimportせず、
  別processで実行する。binaryは公式利用条件に従いrepositoryへ同梱・第三者再配布しない。
- cross sections: userがLXCatから直接取得したnative file。repositoryへ再配布せず、
  database名、process ID、取得日、row数、SHA-256をmanifestへ記録する。
- gas cases: pure Ar、Ar/O2、Ar/NF3、Ar/Cl2。
- grid: 10, 30, 50, 100, 200, 300 Td。mixtureは O2、NF3、Cl2について5、20、50%を
  Arへ混合し、合計60 EEDF conditionsとする。
- OESCR input: `eedf_tabulated` forwardだけを使い、自由EEDF inverseは行わない。
- comparison: EEDF overlay、mean energy、各processのrate coefficient、threshold近傍の
  energy-grid convergence。
- claim: tabulated EEDFの正規化、補間、単位、quadratureの外部tool一致。
- 非claim: BOLSIG+のuniform-field/two-term仮定が実機EEDFを表すこと、Te/neの測定精度。

BOLSIG+は電子Boltzmann方程式からEEDF、transport coefficient、rate coefficientを求める
external solverであり、LXCatもBOLSIG+によるonline swarm計算を提供する。これにより
LXCatは「OESスペクトル正解」ではなく、**断面積入力と外部EEDF/rate基準**として使う。

実装状況（2026-10-01）: immutable CSV/hash manifestの境界、EEDF conventionの明示、
condition/process完全性、EEDF正規化・補間・平均energy、process別rate、near-zero absolute
gate、cross-section supportを検査するcomparatorを実装済みである。入口は
`scripts/compare_external_eedf_rates.py`、入力例は
`examples/validation/external_eedf_rate_template` に置く。analytic fixtureはcomparatorの
software testであり、科学的合格には数えない。全E/Nのexternal/OESCR EEDF overlayと、
mean energy・process別OESCR/external rate比を受入帯付きで描く主図生成も実装済みである。
公式BOLSIG+出力の取得・固定・60条件実行は未完了であり、現在のfixture図を外部物理検証図と
表示してはならない。

公式manualの07/2024 console形式に従う独立run producer
`scripts/prepare_bolsig_reference_run.py`も実装した。Biagi Ar fileのhashを検証してから、
10/30/50/100/200/300 Td、300 K、temporal growth、400-point gridのrun-by-run EEDF/rate
出力instructionとmanifestを作る。このscriptはOESCRをimportせず、公式binaryがない状態を
`not_executed`として保持する。したがって準備完了と外部数値合格は明確に分離される。

user取得済みLXCat 2ファイルも監査した。NGFSRDW/BSRそれぞれのAr 2p1・2p6直接励起曲線で、
raw file SHA-256とprocess曲線digestは既存Arellano診断の固定値に一致する。したがって
これらは個別励起速度係数の比較には使用するが、運動量移行、ionization、その他inelastic
channelを含まないためBoltzmann方程式からEEDFを生成する完全collision setではない。
不足channelをcurated近似で補って外部合格を作ることはせず、同一database由来の完全setを
追加取得する。両native downloadからArellano診断を再実行した結果は保存済みassessmentと
byte単位で一致し、SHA-256
`ded0452fe27a053a34cc6469543a39f43659d8deff5b4d5c1a4b59d8575870fd` を再現した。この再現はatomic-input感度計算の
監査であり、P0-X1のBOLSIG+ EEDF合格ではない。

その後、LXCat Biagi（Magboltz 8.97 transcription）のcomplete Ar setもinventoryした。
raw SHA-256は
`43cefbee063bb43df5a1a593c40e6370dc745bf9460300ad3ade5886a71363b1`、内訳はelastic 1、
excitation 44、ionization 1である。共通`oescr.data.lxcat` adapterへparserを移し、全processの
row数・energy範囲・numeric digestを固定し、選択processを無加工の標準CSVへexportできるように
した。これによりpure Ar 6条件のcollision input不足は解消した。未完了なのは公式BOLSIG+の
実行・出力固定であり、既存独自solverの値で代用しない。対象版は公式07/2024
`bolsigminus`とし、downloadが利用条件への同意を伴うため自動取得は行わない。

### P0-S1: Fuller 2001 Cl2/Ar ICP power・混合比系列

Fuller、Herman、Donnellyは18 mTorrのCl2/Ar ICPで、Ar fraction 1、13、40、78、96%と
rf-power seriesを測定した。response補正済みのCl2 306.0 nm、Cl 822.2 nm、
Cl+ 482.0 nm、Ar+ 480.7 nm、Ne 585.2 nm、Xe 828.0 nm、およびabsolute densityを含む。
現行の `cl2_ar_icp_fuller2001` はこの文献をanchorにした**生成1条件**であり、文献の
外部系列を直接評価していない。

追加case `fuller2001_cl2_ar_power_fraction` は次を行う。

- figureの全power点をdigitizeし、raw vector座標、軸変換、source hashを保存する;
- 5 mixture groupを独立単位とし、1/13/40% Arをmodel整備、78/96% Arを事前固定の
  mixture hold-outにする;
- 306.0/828.0と822.2/828.0のactinometry、482.0/585.2と480.7/585.2のion経路を分ける;
- 600 WのCl2解離率 78--96% mixture trendとabsolute Cl、Cl2、Cl+、Ar+ densityを
  published OES/actinometry resultとして比較する;
- 文献のdensityとTeはいずれもOESとmodel仮定を含むため、独立truthにしない。

author-hosted source PDFを再監査し、SHA-256
`8df375068d854eab94fccf382de02d08b179c4c7386826cff7c2e4bc1a85107e`を固定した。公開図は
rasterで、response補正済みintegrated emissionとactinometry-derived densityを示すが、
machine-readable full spectrumは含まない。したがってraster digitization uncertainty付きの
power/mixture trend候補としては維持するが、full-spectrum overlayや同じactinometry式に対する
独立density truthには昇格させない。

このcaseはCl2/Arで複数conditionを最短で追加でき、生成benchmarkと外部実測trend比較を
明確に分離できるため最優先とする。独立診断とのquantitative Q評価はLi et al.または
別のprobe/absorption datasetで行う。

### P0-S2: An and Hong 2023 NF3/O2・N2/O2 8条件時系列

open-access論文はN2/O2とNF3/O2の2系列について、O2比0、20、50、80%、total 50 sccm、
Ar actinometer 2 sccmを用い、plasma生成後60秒を1 Hzで測定した。したがって8 condition
groups、最大480 frameの系列となる。F 703.7/712.9 nm、O 777.3/844.7 nm、N2 band、
N2+ 391.3 nm、Ar lineを同時に含む。

追加case `an2023_nf3_o2_n2_o2_series` は次を行う。

- 8 conditionsを全て保持し、frameを独立conditionとして水増ししない;
- ignition/transientとstable plateauを分離し、plateauのmedian spectrumとframe間分散を
  model errorの基準にする;
- N2/O2系列を干渉・前処理確認、NF3/O2系列をF/O/N emissionの本評価に使う;
- O2 fraction 0/50%をmodel整備、20/80%を未使用mixture点として固定する;
- paper内Te/neは同じOES line-ratio由来なので、独立Q評価ではなく再現性比較と明記する。

raw numerical spectrumが論文付属物として得られない場合は、figure-derived window areaと
time traceのみを使用し、full-spectrum合格とは呼ばない。

### P0-S3: Daly et al. 2023 industrial ICP 5 gas systems

公開datasetは812,500組のOES/imageを含み、Ar、O2、Ar/O2、CF4/O2、SF6/O2をindustrial
ICP etcherのoperating space全域で測定している。論文が示すsetpoint範囲は次の通りである。

| gas | ICP W | table W | pressure mTorr | gas flow sccm | paperのsetpoints |
|---|---:|---:|---:|---:|---:|
| Ar | 480--3000 | 0--600 | 5--90 | 3.5--70 | 10,000 |
| O2 | 600--3000 | 30--600 | 5--90 | 2.5--50 | 10,000 |
| Ar/O2 | 750--3000 | 30--540 | 5--80 | 各2.5--50 | 30,000 |
| CF4/O2 | 600--3000 | 30--600 | 4--90 | 4.2--84 / 2.5--50 | 60,000 |
| SF6/O2 | 750--3000 | 30--600 | 5--80 | 2.6--52 / 2.5--50 | 70,000 |

48.8 GB全体をrepositoryへ入れない。first pilotは各gas 30 setpoint groupsを決定論的に選び、
低・中央・高pressure、power、flow、mixtureを含める。setpointごとの全repeat frameを
同じgroupに置き、同一setpointのframeがtrain/testへ分裂しないようにする。

2026-10-01の配布監査では、Zenodoは4,882,411,252 byteの分割file 10個を、連結してから
展開する単一`tar.xz` streamとして公開している。個別spectrumやmetadataだけを選択取得する
indexはない。このため「30 setpointだけ先にdownloadする」ことはできず、測定pilotには
48,824,112,520 byteのarchiveを一度取得・検証・展開するdata-access gateがある。

一方、著者の公開repositoryには7 tool setpointを入力して3072-bin spectrumを生成する
trained tool-encoder/spectrum-decoderがある。これをOESCRから独立した
`scripts/prepare_daly_surrogate_pilot.py`で実行し、公開範囲全体を決定論的に層別した
30条件/gas、計150 spectrumを生成した。実行revisionは
`c1d6b3eb204401dcc6792d2bdd9ee9c7c3468dd9`、出力tree SHA-256は
`337fe43510f2e41fb5097642763fd408130557c869e431426b67de151688ce51`である。
これはmulti-gasの波長・emitter coverageを事前監査する外部empirical surrogateであり、
held-out measured spectrum、Te、ne、EEDFの合格証拠には数えない。TensorFlowもOESCRの
runtime dependencyへ追加せず、external producerの隔離環境だけで使う。

OESCRで直ちに扱えるArとO/Ar lineを第1段階とし、CF4/O2とSF6/O2は測定窓に必要な
emitter/cross sectionが揃っているかを先にcoverage表で判定する。未modeled peakを自由な
baselineで消さず、coverage不足として報告する。Te/ne referenceがないため、このsuiteの
claimはfull-spectrum shape、held-out wavelength、gas-mixture interference、process trendに
限定する。

### P1-S4: Sayyed et al. 2025 BOSCH multi-day cyclic spectra

公開datasetは10個の日別NetCDF、185--884 nmの3648 channels、25 Hz OES、5 Hzの31 process
parameters、wafer metrologyを持つ。processは1秒ignitionの後、100 cyclesを実行し、各cycleは
4.5秒SF6 etchと1.5秒C4F8 passivationからなる。

OESCRは定常縮約modelなので、cycle全体を時系列chemistry modelでfitしない。各cycleの
中央plateauをSF6 phaseとC4F8 phaseの別conditionとして抽出し、phase transitionは別の
適用外診断にする。dayを跨ぐsplitを使い、同じwaferや隣接frameをtrain/testへ分けない。

- main plot: measured/predicted plateau spectrumとresidual;
- repeatability: 同一wafer100 cycles内の分布;
- transfer: 1日を丸ごとhold-outしたline-area/shape;
- secondary association: spectrum residualとetch depth/selectivityの関係。ただし因果予測とは
  呼ばない。

### P1-S5: Yuk et al. 2026 N2/air micro-leak sessions

公開dataはN2 2500 sccm、2.5 Torrでair leak 10--60 ppmを導入し、200--850 nm、2048 channels、
0.95 nm resolutionで取得した。波長選定experimentは2つ、検出experimentはA/B/Cの3
sessionsを持ち、NO gamma 245.2 nmが主要応答として報告されている。

OESCRではclassifier精度を主目的にせず、N2/O2/NOの小濃度変化に対するspectrum responseと
session transferを評価する。A/Bで前処理と窓を固定し、Cを完全hold-outにする。NO(A) sourceを
air-leak ppmから予測するchemistryは追加せず、NO emitterが未整備なら「必要line-shape/data
不足」を結果にする。これはTe/ne benchmarkではない。

### P1-Q2: Chai and Kwon 2019 Ar CCP/ICP + Langmuir probe

この論文はCCP/ICP、power 5--200 W、pressure 8--80 PaでOES+CRによるTe/neをLangmuir probeと
比較し、Te 1.2--2.2 eV、ne 4e9--8e11 cm-3を扱う。two-temperature EEDFとfinite-cylinder
escape factorの影響も比較している。現行Ar ratio候補よりTe/ne検証へ直接対応する。

ただしraw spectrumとprobe tableのmachine-readable公開は確認できない。著者提供dataまたは
合法に取得したsupplementが得られるまで `blocked_on_raw_data` とする。figureだけの場合は
minimum 6 conditions/CCP、6 conditions/ICPを圧力・power範囲全体から事前選定し、digitization
uncertaintyをreference uncertaintyへ加える。raw data取得後に全条件へ置換する。

このcaseだけが直ちにTe/neの外部定量claim候補になり得るが、OESCRにtwo-temperature EEDFや
trappingを「合うまで」追加しない。まず現在modelでblind evaluationし、系統残差がmodel欠落と
整合するかを示してから、既存plugin境界内の最小変更を判断する。

### P2-X2: MassiveOES/Moose 分子band line-shape cross-tool

N2(C-B)、N2+(B-X)、OH(A-X)、NO(B-X)などのrovibronic spectrumは、atomic lineを並べた
OESCR検証では代用できない。MassiveOESはmeasured/simulated spectrumのexportとbatch fittingを
提供し、MooseはMassiveOES databaseを用いた独立Python simulatorである。

最初のcaseはN2 SPS 337 nm周辺について、Trot 300、500、800、1200 K、Tvib 1000、3000、
6000 K、Gaussian FWHM 0.05/0.2/0.95 nmのgridを外部toolで生成し、OESCR側はfrozen reference
CSVだけを読む。これはline position、convolution、band envelopeのcross-tool benchmarkであり、
electron-impact populationやgas chemistryの検証ではない。現在のempirical bandがこのgateを
満たせない場合は、coreを増やす前に独立したrovibronic band pluginが必要かを判断する。

## 4. 実装順序

1. **P0-X1**: 実装済みcomparatorへ、inventory済みBiagi Ar setのBOLSIG+入力、外部出力CSV、
   確定hash manifestを接続する。最初にAr 6 E/N点を通し、次に完全collision setを取得した
   O2/NF3/Cl2 mixtureへ広げる。
2. **P0-S1**: Fullerの外部power・mixture系列をdigitizeし、現行生成Cl2 caseと別IDで評価する。
3. **P0-S2**: An/Hongの8条件時系列を取得可能範囲でpackage化し、同一OES由来Te/neをQ claimから
   除外したspectrum/actinometry評価を行う。
4. **P0-S3 pilot**: 公開surrogateによる各gas 30 setpoint、計150 spectrumのpreflightは完了した。
   次は48.8 GB archiveを取得・hash検証・展開し、同じcondition designを実測repeat groupへ
   対応付ける。Ar、O2、Ar/O2を先に評価し、coverageを確認後にCF4/O2、SF6/O2へ進む。
5. **P1-S4/S5**: BOSCHはday split、N2 leakはsession splitで装置・session transferを評価する。
6. **P1-Q2**: Chai/Kwon raw dataを取得できた時点でTe/ne外部定量gateを実行する。
7. **P2-X2**: 分子bandをOESCRの明示的用途に含める判断をした場合だけcross-tool caseを実装する。

順序変更時は、この文書、portfolio YAML、`development_plan.md`、`scientific_validation.md`の
claim/statusを同じcommitで更新する。datasetを入手できたことだけを理由にcore modelを追加しない。

## 5. 各caseで必ず作る図

統計量だけの図ではなく、第三者が物理的意味を読める次の図を固定する。

1. measured spectrumとpredicted spectrumの重ね描き、主要line/band label、下段residual;
2. fitに使った波長領域と完全hold-out領域を背景色で区別したspectrum;
3. pressure、power、mixtureに対する主要line ratioまたはwindow areaの実測・予測比較;
4. 独立referenceがある場合だけ、Te/ne/densityのprediction対referenceと1:1線・error bar;
5. BOLSIG+ caseではEEDF overlayと、process別rate coefficientのOESCR/BOLSIG+比;
6. BOSCH/N2 leakでは、trainとhold-outのday/sessionを明示した代表spectrum比較。

loss historyやparallel-coordinate plotはoptimizer診断として別添にし、科学的合否の主図にしない。

## 6. OESCRへ入れないもの

- dataset固有のprocess recipeからspecies densityを生成するglobal chemistry;
- Daly dataset専用のdeep surrogateをOESCR physicsとして取り込むこと;
- BOSCHのcycleを説明するためだけの時系列reaction network;
- 同じOESから計算したTe/neを独立truthとすること;
- unmodeled peakを吸収する任意波長gainや高次baseline;
- raw LXCat/BOLSIG+ executableのrepository再配布;
- external **reference producer**からOESCRのrate/EEDF kernelをimportして「独立計算」と呼ぶこと。

外部tool outputはimmutable CSV/NetCDFとmanifestとして境界を越え、OESCR comparatorはそれを
OESCR側の計算経路で読む。独立なのはreference producerであり、比較器そのものではない。
これにより、モデルを深掘りしつつglobal model化せず、外部基準との独立性を保つ。

## 7. 一次資料

1. G. A. Daly et al., “Data-driven plasma modelling: surrogate collisional radiative models of
   fluorocarbon plasmas from deep generative autoencoders,” *Machine Learning: Science and
   Technology* 4 (2023) 035035, [doi:10.1088/2632-2153/aced7f](https://doi.org/10.1088/2632-2153/aced7f).
   Dataset: [Zenodo 10.5281/zenodo.7704879](https://doi.org/10.5281/zenodo.7704879).
2. M. A. Sayyed et al., “A Multi-Model Dataset for BOSCH Plasma-Etching,”
   [Zenodo 10.5281/zenodo.17122442](https://doi.org/10.5281/zenodo.17122442), 2025.
3. Y. Yuk et al., “Data and Code for: Mutual Information-Based Wavelength Selection for
   Micro-Leak Detection in N2 Semiconductor Process Environments,”
   [Mendeley Data 10.17632/9gy9v3h4mp.1](https://doi.org/10.17632/9gy9v3h4mp.1), 2026.
4. N. C. M. Fuller, I. P. Herman, V. M. Donnelly, “Optical actinometry of Cl2, Cl, Cl+, and Ar+
   densities in inductively coupled Cl2-Ar plasmas,” *J. Appl. Phys.* 90 (2001) 3182--3191,
   [doi:10.1063/1.1391222](https://doi.org/10.1063/1.1391222).
5. S. An, S. J. Hong, “Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD
   Chamber Cleaning,” *Coatings* 13 (2023) 91,
   [doi:10.3390/coatings13010091](https://doi.org/10.3390/coatings13010091).
6. H. Li, Y. Zhou, V. M. Donnelly, “Optical and mass spectrometric measurements of dissociation
   in low frequency, high density, remote source O2/Ar and NF3/Ar plasmas,” *JVST A* 38
   (2020) 023011, [doi:10.1116/1.5126429](https://doi.org/10.1116/1.5126429).
7. K.-B. Chai, D.-H. Kwon, “Optical emission spectroscopy and collisional-radiative modeling
   for low temperature Ar plasmas,” *JQSRT* 227 (2019) 136--144,
   [doi:10.1016/j.jqsrt.2019.02.015](https://doi.org/10.1016/j.jqsrt.2019.02.015).
8. F. J. Arellano et al., “First-principles simulation of optical emission spectra for low-pressure
   argon plasmas and its experimental validation,” *PSST* 32 (2023) 125007,
   [doi:10.1088/1361-6595/ad0ede](https://doi.org/10.1088/1361-6595/ad0ede).
9. G. J. M. Hagelaar, L. C. Pitchford, “Solving the Boltzmann equation to obtain electron
   transport coefficients and rate coefficients for fluid models,” *PSST* 14 (2005) 722--733,
   [doi:10.1088/0963-0252/14/4/011](https://doi.org/10.1088/0963-0252/14/4/011).
   Software: [BOLSIG+](https://www.bolsig.laplace.univ-tlse.fr/).
10. J. Voráč et al., “Batch processing of overlapping molecular spectra as a tool for
    spatio-temporal diagnostics of power modulated microwave plasma jet,” *PSST* 26 (2017)
    025010, [doi:10.1088/1361-6595/aa51f0](https://doi.org/10.1088/1361-6595/aa51f0).
11. NIST Atomic Spectra Database, version 5.12,
    [doi:10.18434/T4W30F](https://doi.org/10.18434/T4W30F). NIST ASDは波長、level、transition
    probabilityの基準であり、低温process plasmaの測定spectrumまたはEEDF truthではない。
