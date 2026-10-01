# OESCRモデルの理論、数値手法、評価機能および科学的適用範囲

## 要旨

OESCRは、低圧プロセスプラズマの発光分光を対象とする、縮約された定常 collisional-radiative（CR）前向きモデルと条件付き逆解析基盤である。本実装の計算鎖は、電子エネルギー分布関数（EEDF）、電子衝突速度係数、線形CR状態収支、原子線・分子バンド放射、視線積分、装置応答、残差構築、最適化、局所観測可能性評価から成る。

重要な科学的境界は次の3点である。

1. OESCRは、与えられたガス組成、電子状態、励起断面積、消光過程および放射分岐からスペクトルを計算する。自己無撞着なグローバル化学モデルではない。
2. 最適化の収束は物理量の一意な同定を意味しない。測定残差だけから作るJacobianの階数、特異値および弱いパラメータ方向を別に評価する必要がある。
3. 現在の解析解・保存則・生成データ試験は数理検証と自己整合性を支持するが、電子温度、電子密度、EEDFの外部実験に対する定量精度はまだ認定されていない。

本書は、現在のコードが実際に計算している式、各モデルの入力と出力、評価で重要な機能、得られた検証結果、参考文献を一つの論理体系としてまとめる。詳細な個別結果は[科学的検証報告書](physical_validation_report.md)、最適化履歴と図は[最適化診断報告](optimization_diagnostics.md)、公開用途ごとの主張可能範囲は[capability matrix](capability_matrix.md)に分離している。

---

## 1. 適用範囲と計算問題

### 1.1 前向き問題

前向き問題は、パラメータ集合

\[
\boldsymbol\theta =
\{n_e,\ f_E(E),\ n_s,\ \sigma_r(E),\ k_q,\ A_{ul},\
\text{geometry},\ \text{instrument}\}
\]

から、装置で観測されるスペクトル

\[
\widehat{\mathbf y}=\mathcal H\!\left[\mathcal G\!\left[
\mathcal E\!\left[\mathcal C(\boldsymbol\theta)\right]\right]\right]
\]

を得る問題である。ここで、\(\mathcal C\) はCR状態収支、\(\mathcal E\) は発光生成、\(\mathcal G\) は幾何投影、\(\mathcal H\) は装置応答を表す。

### 1.2 逆問題

逆問題は、設定で明示した有限次元パラメータ \(\mathbf x\) のみを未知量として、

\[
\mathbf x^*=\arg\min_{\mathbf x\in[\mathbf l,\mathbf u]}
\Phi(\mathbf x),\qquad
\Phi(\mathbf x)=\frac{1}{2}\|\mathbf r(\mathbf x)\|_2^2
\]

を解く。したがって、設定に含まれていても `parameters` に列挙されていない \(T_e\)、\(n_e\)、密度、EEDFパラメータは入力であり、推定結果ではない。

### 1.3 実装上の責務境界

| 層 | 主な責務 | 代表実装 |
|---|---|---|
| EEDF・速度係数 | \(f_E(E)\) の生成、\(\langle\sigma v\rangle\) 積分、断面積範囲診断 | [`physics/eedf.py`](../oescr/physics/eedf.py), [`physics/rates.py`](../oescr/physics/rates.py) |
| CR状態収支 | 反応を線形行列へ組み立て、励起状態密度を解く | [`physics/cr_processes.py`](../oescr/physics/cr_processes.py), [`physics/cr_atomic.py`](../oescr/physics/cr_atomic.py) |
| 放射 | 原子線、経験的バンド、物理単位付き電子衝突バンド | [`forward/emissivity.py`](../oescr/forward/emissivity.py), [`physics/bands.py`](../oescr/physics/bands.py) |
| 観測 | 視線積分、LSF、分光感度、校正、bin平均 | [`geometry/`](../oescr/geometry), [`instrument/`](../oescr/instrument), [`forward/observe.py`](../oescr/forward/observe.py) |
| 逆解析 | 測定読込、残差、制約、最適化、同定可能性 | [`inverse/`](../oescr/inverse) |
| 検証 | 解析解、保存則、生成ベンチマーク、外部候補、証拠監査 | [`tests/`](../tests), [`analysis/`](../oescr/analysis), [`examples/validation/`](../examples/validation) |

この分離により、新しい気体種は主として状態・遷移・反応・断面積をデータとして追加でき、既存のCRソルバーや逆解析器を気体種ごとに分岐させない。

---

## 2. EEDFモデル

### 2.1 共通定義

OESCRのEEDFは、エネルギー空間における確率密度 \(f_E(E)\) として扱う。

\[
f_E(E)\ge 0,\qquad
\int_{0}^{\infty}f_E(E)\,dE=1.
\]

実装では有限エネルギー格子上で負値を0に切り上げ、台形則によって再正規化する。したがって、解析式の無限区間正規化ではなく、指定した `energy_grid` 上での離散正規化である。

### 2.2 Maxwell型EEDF

実装式は

\[
f_M(E;T_e)=\frac{2}{\sqrt{\pi}}
\frac{\sqrt{E}}{T_e^{3/2}}
\exp\!\left(-\frac{E}{T_e}\right)
\]

である。無限区間では

\[
\langle E\rangle=\frac{3}{2}T_e
\]

となるが、有限格子では切断後に再正規化されるため、実際の平均エネルギーは診断値から確認する必要がある。`te_maxwell` は `te_shells_eV` または公開 `eedf.zones[].te_eV` を形状パラメータとして使う。

### 2.3 Druyvesteyn-like EEDF

実装は

\[
f_D(E;T_s)=C_D\sqrt{E}
\exp\!\left[-\left(\frac{E}{T_s}\right)^2\right]
\]

であり、\(C_D\) は離散正規化定数である。無限区間での平均エネルギーは

\[
\langle E\rangle=
T_s\frac{\Gamma(5/4)}{\Gamma(3/4)}
\approx 0.7397T_s
\]

である。このため `te_druyvesteyn` の `te_eV` はMaxwell型の熱力学的温度と同じ意味ではなく、形状スケールである。EEDF形状だけを比較する外部Ar評価では、Maxwell型とDruyvesteyn型を同じ入力 `te_eV` にせず、二分探索により同じ \(\langle E\rangle\) へ合わせている。

### 2.4 bi-Maxwell EEDF

低温成分と高温成分の混合として

\[
f_{BM}(E)=(1-\alpha)f_M(E;T_c)+\alpha f_M(E;T_h),
\qquad 0\le\alpha\le1,\quad T_h\ge T_c
\]

を用いる。`Tc_eV`、`Th_eV`、`hot_fraction` はすべて明示入力であり、暗黙の高温成分は作らない。低分解能スペクトルで自由形状EEDFを逆推定する代わりに、この有限次元族までに制限することで、パラメータ数と観測情報量の不均衡を抑える。

### 2.5 tabulated EEDF

入力点 \((E_i,f_i)\) を内部格子へ線形補間し、入力範囲外を0として再正規化する。

\[
f_T(E)=\mathcal N\left[operatorname{interp}(E;E_i,f_i)\right].
\]

これは前向き評価には有用だが、低分解能装置での自由配列逆推定は制限される。観測核の階数と正則化を別途実証しない限り、スペクトルだけから任意EEDFを一意に回収したとは解釈できない。

### 2.6 EEDF評価で重要な機能

| 機能 | 定義 | 検出する問題 |
|---|---|---|
| 正規化 | \(\int f_EdE\) | 負値、空分布、補間失敗 |
| 平均エネルギー | \(\langle E\rangle=\int Ef_EdE\) | EEDF族間での不公平な比較 |
| 上位10%格子確率 | \(\int_{E\ge E_{90\%\,grid}}f_EdE\) | `energy_grid.max_eV` が低すぎる可能性 |
| 端点相対値 | \(f_E(E_{max})/\max f_E\) | 高エネルギー尾部の切断 |
| 断面積被覆確率 | \(\int_{E_{min}^{\sigma}}^{E_{max}^{\sigma}}f_EdE\) | EEDFが断面積データ範囲外へ漏れる問題 |

これらはモデルの物理的正しさではなく、積分領域と入力データの適合性を診断する。

---

## 3. 電子衝突速度係数と断面積モデル

### 3.1 EEDF積分

電子速度を

\[
v(E)=\sqrt{\frac{2eE}{m_e}}
\]

とし、反応 \(r\) の速度係数を

\[
k_r[f_E]=\int_0^{\infty}\sigma_r(E)v(E)f_E(E)\,dE
\]

で計算する。\(\sigma\) が \(\mathrm{m^2}\)、\(v\) が \(\mathrm{m\,s^{-1}}\) であるため、\(k_r\) の単位は \(\mathrm{m^3\,s^{-1}}\) になる。CSV断面積は内部格子へ線形補間され、表の外側では0となる。

### 3.2 利用可能な速度係数モデル

| `kind` | 式・入力 | 適切な用途 | 主な制限 |
|---|---|---|---|
| `cross_section_file` | 上式をCSV断面積で積分 | 状態分解された物理計算 | 断面積の由来、不確かさ、閾値、範囲に依存 |
| `threshold_model` | 下記の解析的代理断面積 | 感度解析、初期モデル | 実験・理論断面積の代用として定量主張不可 |
| `constant` | \(k_r=k_0\) | 既知の有効速度係数 | EEDF依存性を表現しない |

閾値代理モデルは、\(x=\max(E-E_{th},0)\)、\(w=E_{peak}-E_{th}\) として

\[
\sigma(E)=
\begin{cases}
\sigma_{peak}\dfrac{x}{w}\exp\!\left(1-\dfrac{x}{w}\right),& E>E_{th},\\
0,&E\le E_{th}
\end{cases}
\]

を用いる。\(E=E_{peak}\) で \(\sigma=\sigma_{peak}\) となる。

### 3.3 断面積評価で重要な機能

- エネルギー列が厳密増加、断面積が有限・非負であることを読込時に検査する。
- ファイルSHA-256、エネルギー範囲、コメントメタデータ、EEDF被覆確率を診断へ残す。
- 外部Ar評価では、LXCat曲線を平滑化・振幅調整せず数値ダイジェストで固定する。
- 宣言された励起閾値未満では断面積を明示的に0とする。
- 断面積モデル間の差を統計的不確かさとみなさず、model discrepancy の感度包絡として扱う。

速度係数は高エネルギー尾部と閾値近傍の両方に敏感である。そのため、数個の高エネルギー断面積点が合うことだけでは、低温プラズマで使うEEDF積分速度係数を検証できない。

---

## 4. 線形collisional-radiativeモデル

### 4.1 定常状態方程式

解く励起状態密度ベクトルを \(\mathbf n^*\) とすると、各zoneで

\[
\mathbf M(\boldsymbol\theta)\mathbf n^*=\mathbf b(\boldsymbol\theta)
\]

を解く。外部から与える基底状態、ラジカル、準安定状態、電子は右辺源または衝突体として使い、`solve: true` の状態だけを未知数にする。

状態 \(i\) の連続式として書けば

\[
0=\sum_{j\ne i}\nu_{j\rightarrow i}n_j
+S_i^{ext}
-n_i\sum_{k\ne i}\nu_{i\rightarrow k}
-n_i\nu_i^{loss}.
\]

OESCRはこれを、対角損失を正、他状態からの流入を負の非対角成分とする \(\mathbf M\) に組み立てる。

### 4.2 反応族と有効周波数

| 反応族 | 係数単位 | 有効周波数 |
|---|---:|---:|
| 電子衝突 | \(\mathrm{m^3\,s^{-1}}\) | \(\nu_e=n_ek_e[f_E]\) |
| 一次反応 | \(\mathrm{s^{-1}}\) | \(\nu_1=k_1\) |
| 二体反応 | \(\mathrm{m^3\,s^{-1}}\) | \(\nu_2=k_2n_M\) |
| 三体反応 | \(\mathrm{m^6\,s^{-1}}\) | \(\nu_3=k_3n_Mn_N\) |

源状態が未知ベクトル内にある場合、\(M_{ss}\leftarrow M_{ss}+\nu\) とし、遷移先も未知なら \(M_{ts}\leftarrow M_{ts}-\nu\) とする。源状態が外部密度 \(n_s^{ext}\) で遷移先が未知なら、\(b_t\leftarrow b_t+\nu n_s^{ext}\) とする。

この線形性を守るため、二体・三体反応の衝突体は外部密度に限定される。未知状態同士の衝突による非線形項を暗黙に線形化することはしない。

### 4.3 放射遷移と完全な分岐

上準位 \(u\) から下準位 \(l\) への放射は一次損失

\[
\nu_{u\rightarrow l}=A_{ul}^{eff}
\]

としてCR行列へ入り、\(l\) が解く状態ならカスケード源にもなる。観測対象でない分岐も上準位の全損失に含めなければ、対象線の光子生成率を過大評価する。Ar species pack が2p1と2p6のNIST分岐をすべて持つのはこのためである。

### 4.4 放射閉じ込め

現在の標準モデルはslab escape factorであり、

\[
\beta(\tau_0)=
\begin{cases}
1,&\tau_0\rightarrow0,\\
\dfrac{1-e^{-\tau_0}}{\tau_0},&\tau_0>0
\end{cases},
\qquad A_{ul}^{eff}=\beta A_{ul}
\]

とする。`beta_override` では \(0\le\beta\le1\) を直接指定できる。これは完全な放射輸送やHolstein方程式の解ではなく、実効A係数近似である。実装済み形状はslabのみであり、円筒等を名目だけで選択することは拒否する。

### 4.5 壁損失

円筒容器の実効長を

\[
L=\frac{V}{A}
=\frac{\pi R^2H}{2\pi RH+2\pi R^2},
\]

平均熱速度を

\[
\bar v_{th}=\sqrt{\frac{8k_BT_g}{\pi m_s}}
\]

として、壁損失周波数を

\[
\nu_{wall}=\gamma_s\,\alpha_{flux}\frac{\bar v_{th}}{L}
\]

で与える。`thermal_flux_factor` は明示値であり、等方的な面フラックス \(\bar v/4\) を使う定義なら0.25を指定する。これは壁面反応ネットワークではなく、励起状態の実効一次損失である。

### 4.6 線形解法と状態収支

通常は `numpy.linalg.solve` を使い、線形代数例外時だけ最小二乗へフォールバックする。解く前の負密度を診断してから0へclipするため、clipによって異常が隠れない。各状態について

\[
R_i^{net}=R_i^{source}-R_i^{loss}
\]

を反応・放射・壁損失別に再構築する。重要な評価量は行列階数、条件数、相対残差、clip前負密度比、各状態のnet balanceである。

---

## 5. 発光モデル

### 5.1 原子線

線形状 \(\phi_{ul}(\lambda)\) を

\[
\int\phi_{ul}(\lambda)d\lambda=1
\]

に正規化し、光学的に等方な体積分光放射率を

\[
j_{ul,\lambda}=
\frac{n_uA_{ul}^{eff}}{4\pi}
\frac{hc}{\lambda_{ul}}
\phi_{ul}(\lambda)
\]

とする。単位は \(\mathrm{W\,m^{-3}\,sr^{-1}\,nm^{-1}}\) である。積分値は

\[
\int j_{ul,\lambda}d\lambda
=\frac{n_uA_{ul}^{eff}hc}{4\pi\lambda_{ul}}
\]

となるため、光子数と放射パワーの保存を独立に試験できる。

### 5.2 バンド輪郭

Gaussian輪郭は

\[
\phi_b(\lambda)=C_b
\exp\!\left[-\frac{(\lambda-\lambda_b)^2}{2\sigma_b^2}\right],
\qquad
\sigma_b=\frac{\mathrm{FWHM}}{2\sqrt{2\ln2}}
\]

を面積1へ正規化する。tabulated輪郭はCSVを線形補間して面積1へ正規化する。したがって、輪郭は総振幅を変えず波長方向へ分配する役割を持つ。

### 5.3 三つのバンド発光モデル

#### effective excitation band

\[
j_b^{eff}(\lambda)=
C_b\,n_e n_s k_b[f_E]\phi_b(\lambda).
\]

電子衝突感度を保持する経験的イベント率モデルである。出力basisは `effective_event_rate_density_m-3_s-1_nm-1` で、放射パワーではない。

#### effective density band

\[
j_b^{dens}(\lambda)=C_bn_s\phi_b(\lambda).
\]

発光種代理密度から測定形状を作る経験モデルである。NF3/ArやCl2/Ar生成ベンチマークの一部はこの種の有効エミッターを使うため、化学種密度や絶対光子生成率と同一視できない。

#### electron-impact photon band

\[
j_b^{phys}(\lambda)=
\frac{n_en_sk_b[f_E]Y_bB_b}{4\pi}
\frac{hc}{\lambda}\phi_b(\lambda),
\]

ここで \(Y_b\) は衝突当たり光子yield、\(B_b\) は分岐比である。これは原子線と同じ放射パワーbasisを持ち、絶対校正用途で組み合わせられる。

### 5.4 評価上の重要点

- 経験バンドと物理バンドを同じ単位とみなさない。
- `calibrated_absolute` は経験バンドを拒否する。
- `ForwardResult` は総和だけでなく、原子線・各バンドのbasisと成分を返す。
- 原子線と物理バンドを合算した保存則試験により、\(4\pi\)、光子エネルギー、輪郭積分、視線長、装置binの取り扱いを同時に確認する。

---

## 6. 空間幾何モデル

### 6.1 axisymmetric shell

半径境界 \(r_k,r_{k+1}\) の円筒殻をimpact parameter \(b_m\) のchordが横切る長さは

\[
W_{mk}=2\left[
\sqrt{\max(r_{k+1}^2-b_m^2,0)}
-\sqrt{\max(r_k^2-b_m^2,0)}
\right]
\]

である。ただし \(|b_m|\ge r_{k+1}\) なら0とする。zone放射率からchord放射輝度への投影は

\[
I_{m,\lambda}=\sum_kW_{mk}j_{k,\lambda}
\]

である。現在の5-chordベンチマークは同一高さの軸対称殻を仮定する。

### 6.2 その他の幾何

| モデル | 内容 | 科学的状態 |
|---|---|---|
| `chordavg` | 1本の観測にzoneを加算 | 最小例・非空間分解用途 |
| `axisym_shell` | 上記の解析的chord行列 | 標準経路 |
| `asym_lowrank` | 一次方位モードの乗算補正 | 実験的hook。外部妥当性未検証 |
| `user_field` | 任意の2次元forward matrix | tomography・光学系を外部計算する場合 |

`user_field` は複雑な幾何をコアへ増築せず、外部で検証したforward operatorを注入する境界である。

---

## 7. 装置モデル

### 7.1 処理順序

装置処理は次の順序で行う。

1. 波長シフト
2. line-spread function（LSF）畳み込み
3. 波長依存throughput
4. 次元付き校正変換
5. gainとbaseline
6. 測定bin内の積分平均

概念的には

\[
y_i=\frac{1}{\Delta\lambda_i}
\int_{\lambda_{i-1/2}}^{\lambda_{i+1/2}}
\left[g\,\mathcal K_{LSF}\{I(\lambda-\delta\lambda)T(\lambda)\}
+b(\lambda)\right]d\lambda.
\]

中心点sampleではなくbin平均を使い、bin境界を内部積分格子へ明示挿入する。これにより細格子の位相による面積損失を防ぐ。

### 7.2 LSF

- Gaussian: 指定FWHMから標準偏差を求め、離散kernelを総和1へ正規化する。
- Voigt: Gaussian幅 \(\sigma\) とLorentz半幅 \(\gamma\) をFaddeeva関数で合成し、非負化・正規化する。

LSF正規化は分光形状を広げても総信号量を保存するために重要である。

### 7.3 校正basis

| 出力 | 変換 |
|---|---|
| spectral radiance | \(L_\lambda\) を保持 |
| collected spectral power | \(P_\lambda=L_\lambda A\Omega\eta_v\) |
| photoelectron spectrum | \(N_{pe,\lambda}=P_\lambda t_{int}\eta_q/(hc/\lambda)\) |

絶対校正では、collection area、solid angle、viewing factor、積分時間、quantum efficiencyのうち変換に必要な項を明示する。相対標準校正不確かさ \(u_c\) は平均予測を変えず、測定共分散へ

\[
\mathbf C_{eff}=\mathbf C_{meas}
+(u_c\mathbf y)(u_c\mathbf y)^T
\]

というrank-one相関誤差として加える。

---

## 8. 逆解析モデル

### 8.1 パラメータ座標

正値パラメータにはlog座標を選べる。

\[
x=\log_{10}\theta,\qquad \theta=10^x.
\]

これにより、複数桁にわたる密度や速度係数を有界区間で探索できる。Jacobian、Laplace標準偏差、最適化traceの `x` はoptimizer座標であるため、物理単位へ戻して解釈する必要がある。

### 8.2 gain・offset・tilt

相対スペクトルでは、予測 \(p_i\) に対して

\[
\widehat y_i=g(1+t\xi_i)p_i+c,
\qquad
\xi_i=\frac{\lambda_i-\bar\lambda}{(\lambda_{max}-\lambda_{min})/2}
\]

を線形最小二乗でprofile outできる。gainは正値に制限し、chordごとまたは装置共通にできる。ただしgainを自動fitすると絶対発光scaleを吸収するため、`calibrated_absolute` では禁止する。

### 8.3 全スペクトル残差

独立標準偏差 \(\sigma_i\) がある場合は

\[
r_i^{spec}=\frac{\widehat y_i-y_i}{\sigma_i}.
\]

共分散 \(\mathbf C=\mathbf L\mathbf L^T\) がある場合は、逆行列を作らず

\[
\mathbf r^{spec}=\mathbf L^{-1}(\widehat{\mathbf y}-\mathbf y)
\]

とする。不確かさが無い相対データでは、測定スペクトルの標準偏差でscaleする。

### 8.4 window形状、面積、peak

window端の点から定数または一次baseline \(b_w(\lambda)\) を求め、

\[
\widetilde y_w(\lambda)=y_w(\lambda)-b_w(\lambda)
\]

とする。window-fitは面積、peak、L2、または無正規化を選び、測定windowの標準偏差でscaleする。面積とpeakのscalar残差は

\[
r_A=\frac{\widehat A-A}{|A|},\qquad
r_P=\frac{\widehat P-P}{|P|}
\]

である。弱いwindowは同じchordの最大信号に対する閾値で除外し、その名称を結果へ残す。

### 8.5 線比残差

線比は対数比で比較する。

\[
r_{a/b}^{ratio}
=\log\frac{\widehat q_a}{\widehat q_b}
-\log\frac{q_a}{q_b}.
\]

この形は共通の乗算gainを相殺し、過大・過小を対称に扱う。ただし、異なる波長間の分光感度誤差、励起断面積比、分岐、消光差は残る。

### 8.6 feature共分散、事前分布、平滑化

面積・peak・線比featureにも共分散 \(\mathbf C_f\) を指定でき、Cholesky whiteningを行う。同じfeatureをscalar weightと共分散の両方へ重複投入しない。

Gaussian priorとlog-Gaussian priorはそれぞれ

\[
r_p=\frac{\theta-\mu}{\sigma},\qquad
r_{p,\log}=\frac{\log_{10}\theta-\mu_{\log}}{\sigma_{\log}}
\]

である。zone配列の一次・二次平滑化は

\[
\mathbf r_{reg}=\sqrt{w}\frac{\Delta^q\boldsymbol\theta}
{\max(\operatorname{std}(\boldsymbol\theta),1)},
\qquad q\in\{1,2\}
\]

として目的関数へ加える。これらは解を安定化できるが、測定情報を増やさない。

### 8.7 最適化

標準手順は次の二段階である。

1. differential evolutionによる有界global探索
2. `scipy.optimize.least_squares` のTrust Region Reflective法による局所精密化

global探索は多峰性・初期値依存を軽減し、局所法は残差ベクトル構造を利用して収束させる。再現性のためglobal seedを設定できる。`--record-trace` を指定した場合のみ、実際の各目的関数評価についてstage、loss、optimizer座標を保存する。trace図は補間や架空の候補点ではなく、この実評価履歴から作る。

### 8.8 局所観測可能性

最適点近傍で測定残差だけを有限差分し、

\[
J_{ij}=\frac{\partial r_i^{data}}{\partial x_j}
\approx\frac{r_i(\mathbf x+\Delta x_j\mathbf e_j)-r_i(\mathbf x)}{\Delta x_j}
\]

を作る。特異値分解

\[
\mathbf J=\mathbf U\boldsymbol\Sigma\mathbf V^T
\]

からrank、条件数、各列norm、弱い右特異ベクトルを報告する。事前分布と平滑化を除外することが最重要であり、そうしないと仮定による曲率を測定可能性と誤認する。

フルrankでも

\[
\kappa=\sigma_{max}/\sigma_{min}
\]

が大きい場合、ノイズやモデル誤差に対して脆弱である。NF3/Arの \(\kappa\approx3.15\times10^6\) はその例である。

### 8.9 Laplace近似

事前分布・正則化を含む完全目的Jacobian \(\mathbf J_{obj}\) から

\[
\mathbf C_x\approx
\left(\mathbf J_{obj}^T\mathbf J_{obj}+10^{-12}\mathbf I\right)^{-1}
\]

を計算する。これは局所・条件付き曲率であり、cross-section uncertainty、model discrepancy、共分散hyperparameter、不連続なmode uncertaintyを周辺化したBayesian posteriorではない。

### 8.10 四つの用途契約

| mode | 主に使う情報 | 推定できる条件 | 禁止・注意事項 |
|---|---|---|---|
| `relative_shape` | 正規化形状、chord差、相対線強度 | Jacobianが対象parameterに感度を持つ | gainと \(n_e n_s\) の絶対scaleは交絡し得る |
| `ratio_diagnostic` | 指定線・window比 | 励起・分岐・消光・分光感度比が既知 | 比だけで絶対密度scaleを一般には決められない |
| `actinometry` | target/actinometer比 | 両者の励起・消光仮定とactinometer密度が外部妥当 | 新しい化学モデルを内部で追加するmodeではない |
| `calibrated_absolute` | 絶対校正スペクトル | 絶対光学系、物理basis、source密度、局所rankが閉じる | auto gainと経験バンドを拒否 |

---

## 9. 数値品質モデル

### 9.1 デフォルト診断

| 診断 | warning | error | 意味 |
|---|---:|---:|---|
| CR条件数 | \(>10^{10}\) | \(>10^{14}\) | 状態密度が入力誤差へ過敏 |
| CR相対残差 | \(>10^{-8}\) | \(>10^{-5}\) | 線形解が方程式を満たさない |
| clip前負密度L1比 | \(>10^{-12}\) | \(>10^{-6}\) | 反応構造または数値条件の問題 |
| EEDF上位格子10%確率 | \(>10^{-2}\) | \(>5\times10^{-2}\) | energy上限不足の可能性 |
| EEDF端点/peak | \(>2\times10^{-2}\) | \(>10^{-1}\) | 尾部切断の可能性 |
| 断面積被覆確率 | \(<0.99\) | \(<0.90\) | 断面積範囲不足 |

rank不足は閾値にかかわらず `cr.singular_matrix` errorとなる。policyは `raise` または結果を保持する `report` を選べる。

### 9.2 格子収束

opt-inの収束試験では、energy格子と内部wavelength格子をそれぞれ既定で2倍に細分し、全装置・全chordの最大相対L2差

\[
\epsilon_{grid}=
\max_{m,d}
\frac{\|\mathbf y^{refined}_{m,d}-\mathbf y^{base}_{m,d}\|_2}
{\max(\|\mathbf y^{refined}_{m,d}\|_2,\|\mathbf y^{base}_{m,d}\|_2,\epsilon)}
\]

を評価する。既定は warning \(10^{-3}\)、error \(10^{-2}\) である。逆解析中に毎回実行すると計算量が約3倍になるため、case qualificationとrelease gateに限定する。

---

## 10. 検証の証拠階層

| 階層 | 問い | 現在の証拠 | 許されない拡張解釈 |
|---|---|---|---|
| 解析核 | 実装が閉形式解・保存則と一致するか | 二準位、三準位cascade、放射・バンド保存 | 実際のプラズマが同じ縮約機構であること |
| 数値適格性 | 格子・行列・単位が健全か | quality gate、格子refinement、schema/contract test | 原子データの正しさ |
| 生成end-to-end | 同じモデル由来の観測を逆解析できるか | 二バンド、NF3/Ar、Cl2/Ar | 外部実験への予測精度 |
| 外部診断 | 文献データに対する機構感度を示せるか | Arellano Ar、Schuecke N2/O2候補 | uncertainty付き定量validation |
| 外部定量 | held-out・校正・入力closure・固定公差を満たすか | 現在は該当なし | Te、ne、EEDF精度の一般主張 |

生成データの正解をfitに使っていないことだけでは、外部validationにならない。外部定量認定には、少なくともデータ由来、held-out、校正basis、モデル入力closure、evaluation-only利用、evaluator identity、事前固定した受入指標が必要である。

---

## 11. 各評価と、合否を左右する重要機能

### 11.1 二準位CR閉形式解

外部状態 \(G\) から未知状態 \(U\) へpump \(\nu_p\)、\(U\) からquench \(\nu_q\)、放射 \(A\) を与える。

\[
n_U=\frac{n_G\nu_p}{\nu_q+A}.
\]

試験値は \(n_G=3.0\times10^{10}\,\mathrm{m^{-3}}\)、\(\nu_p=4\,\mathrm{s^{-1}}\)、\(\nu_q=2\,\mathrm{s^{-1}}\)、\(A=10\,\mathrm{s^{-1}}\) である。行列、右辺、密度、rank、相対残差、source=lossを同時に検査する。

重要な機能は、外部sourceを右辺へ入れること、放射とquenchを同じ対角損失へ足すこと、clip前の解で残差を評価することである。この試験が落ちる場合、より複雑なスペクトル評価へ進む意味はない。

### 11.2 三準位cascade・分岐・光子保存

\(G\rightarrow U\)、\(U\rightarrow M\)、\(U\rightarrow G\)、\(M\rightarrow G\) を持つ系では

\[
n_U=\frac{S}{A_{UM}+A_{UG}},\qquad
n_M=\frac{A_{UM}n_U}{A_{MG}}.
\]

さらに

\[
\frac{\dot N_{UM}}{\dot N_{UG}}=\frac{A_{UM}}{A_{UG}},\quad
\dot N_{UM}+\dot N_{UG}=S,\quad
\dot N_{MG}=\dot N_{UM}
\]

を検査する。重要機能は、観測しない放射分岐も上準位損失へ入ることと、下準位が未知ならcascade源として非対角行列へ入ることである。

### 11.3 物理electron-impact photon band

単一zone、既知 \(n_e,n_s,k,Y,B\)、Gaussian輪郭、中心chordを使い、解析的な光子生成率

\[
R_\gamma=n_en_skYB
\]

から放射パワー、chord放射輝度、装置bin積分までを比較する。バンド積分体積放射の相対差は \(7.21\times10^{-7}\)、中心chordも同じ相対差で一致した。

重要機能は、輪郭面積1、\(hc/\lambda\)、\(1/4\pi\)、chord長、LSF・bin面積保存、出力basisである。

### 11.4 原子線と物理バンドの結合保存

原子線と物理バンドを同一のradiant-power basisで合算し、成分積分と総積分を照合する。合計体積放射の相対差は \(6.33\times10^{-7}\) であった。

この評価で重要なのは、成分basisを保持する機能である。経験バンドを混ぜた総和が数値的に計算できても、異なる物理単位の和なら保存則の証拠にはならない。

### 11.5 数値異常・単位契約

以下を意図的に作って、無言の成功ではなく分類された失敗になることを確認する。

- rank-deficient CR行列
- EEDF上限不足
- 不正な断面積表
- 非一様装置格子
- mass未指定の壁損失
- 未実装trapping geometry
- absolute modeでの経験bandまたはauto gain
- covarianceの非対称・非正定値・次元不一致

重要機能は、schemaだけでなく実値・単位・相互参照を検査するsemantic validation、`DiagnosticReport`、provenance出力である。

### 11.6 二バンド最小逆解析

Targetとactinometerの二つの物理bandを用い、三つの用途を同じ前向きモデル上で縦断評価する。

| mode | 未知量 | 観測 | 正解 | 推定 | rank |
|---|---|---|---:|---:|---:|
| ratio | Target密度 | 1つの対数線比 | \(2.0\times10^{18}\) | \(1.99999999968\times10^{18}\) | 1/1 |
| actinometry | Target密度 | 同じ対数線比 | \(2.0\times10^{18}\) | \(1.99999999968\times10^{18}\) | 1/1 |
| calibrated absolute | 電子密度 | 18点の絶対放射輝度 | \(3.0\times10^{16}\) | \(3.00000000000\times10^{16}\) | 1/1 |

ratio/actinometryでは電子温度は固定で、EEDFも固定Maxwell族である。absoluteで電子密度が回復できるのは、absolute calibration、source密度、物理band、gain固定という閉じた問題を意図的に作ったためである。

重要機能は、modeごとの禁止条件、測定metadataと校正契約の一致、ratio残差、rank-one calibration covariance、data-only rankである。

### 11.7 NF3/Ar生成自己整合性

An and HongのNF3/Ar発光特徴を参照したmeasurement-like生成データで、5 chord、広帯域N2有効band、F線、Ar線を使う。未知量は3 zoneの \(T_e\)、F密度、N2 emitter proxy密度の9変数で、\(n_e\) は固定入力である。

| 指標 | 初期 | 最適化後 |
|---|---:|---:|
| objective cost | 210.744 | 199.242 |
| mean correlation | 0.992536 | 0.992781 |
| mean NRMSE/std | 0.156053 | 0.142517 |
| pair classification accuracy | 0.900 | 1.000 |
| data-only rank | — | 9/9 |
| condition number | — | \(3.15\times10^6\) |

回復誤差はTeが約7.5–9.5%、Fが約9.5–14.8%、N2 emitter proxyが約11.4–23.5%である。スペクトル一致とparameter一致が同じではなく、N2 proxyは初期値より平均誤差が悪化した。

重要機能は、広帯域と線を別windowとして評価すること、低信号gating、線比pattern、5 chord空間感度、測定だけのSVDである。高条件数のため、full rankを強い同定と解釈してはならない。

### 11.8 Cl2/Ar生成自己整合性

FullerらのCl2/Ar ICPの特徴を参照し、Cl2 306 nm band、Ar II/Cl II線、Cl I/Xe I線を5 chordへ空間化した生成データを使う。未知量は3 zoneのCl密度とCl2 emitter proxy密度の6変数で、\(T_e\)、\(n_e\)、EEDFは固定である。

| 指標 | 初期 | 最適化後 |
|---|---:|---:|
| objective cost | 349.354 | 348.088 |
| mean correlation | 0.987496 | 0.987538 |
| mean NRMSE/std | 0.203031 | 0.202536 |
| pair classification accuracy | 0.6667 | 0.8667 |
| data-only rank | — | 6/6 |
| condition number | — | 59.5 |

Cl密度平均絶対相対誤差は18.99%から5.87%、Cl2 proxyは13.49%から11.21%へ改善した。このcaseはNF3より局所条件が良いが、Te・ne・EEDFの予測試験ではない。

重要機能は、近接するAr II/Cl II、Cl I/Xe Iをwindowと比で扱うこと、global gain/tiltが物理ratioを不当に吸収しないこと、固定量とfit量を報告で分離することである。

### 11.9 Schuecke N2/O2外部候補

10 Pa N2/O2 ICPのpower scanから、絶対UV体積光子生成率、NO密度、gas temperature、probe由来 \(n_e,T_e\) をdigitizeし、ファイルhashと座標変換を固定した。UV光子率の報告相対不確かさは8.9%、NO密度は20%、gas temperatureは3%である。

一方、論文が主要経路として扱うN2(A)準安定密度は独立測定されていない。したがって、

\[
N_2(A)+NO(X)\rightarrow N_2(X)+NO(A)
\]

等を無視して単一electron-impact bandへ置換すると、信号源の物理を変えてしまう。入力closureは `open` で、dataset preparationは完了しているがOESCR定量比較は保留である。

重要機能は、`volumetric_photon_rate` という観測basisを明示できることと、データが存在しても入力closureが閉じなければvalidationへ昇格させない証拠gateである。

### 11.10 Arellano Ar線比、NIST、Chilton、LXCat

response-corrected実験線比 \(I(763.5)/I(750.4)\) の2–100 Pa系列をheld-out候補とし、低圧2–10 Paの実測範囲0.5836–0.6967を、direct-ground-state corona近似の感度計算と比較する。

各上準位の全NIST分岐を使い、branching fractionを

\[
B_{ul}=\frac{A_{ul}}{\sum_lA_{ul}}
\]

とする。外部評価器が計算するbranching-weighted photon-rate比は

\[
R_{763/750}=
\frac{k_{2p6}[f_E]B_{763}}{k_{2p1}[f_E]B_{750}}.
\]

BSR-500とNGFSRDW断面積、Maxwell/Druyvesteyn、平均energy 3–12 eV、native/NIST閾値を組み合わせた24条件で評価した。

| 断面積族 | 予測比範囲 | 低圧実測との重なり |
|---|---:|---|
| BSR-500 | 0.5845–1.2020 | あり |
| NGFSRDW | 0.1149–0.3209 | なし |
| 全感度包絡 | 0.1149–1.2020 | あり。ただし確率区間ではない |

20/40/100 eVのChilton直接励起anchorに対し、BSRとNGFSRDWの比はenergy依存で大きく異なる。24条件における二モデル間の最大/最小予測比は3.68–5.09倍であり、断面積model discrepancyが支配的である。

Chiltonの40 eV、1 mTorr cascade anchorを適用した場合のnominal線比倍率は1.587だが、これは実験圧力・EEDFへ移植できないため主予測に適用していない。Arellano記載のAr消光だけを加えた感度では、低圧比の最大変化は約\(6.3\times10^{-5}\)であった。

重要機能は、正しいAr 2p1/2p6 level mapping、全放射分岐、LXCat production process ID・row数・数値hash、閾値以下0、EEDF平均energy matching、観測への振幅tuning禁止である。ただし独立EEDF、metastable、cascade closure、uncertainty付き公差が無いため、結果は `diagnostic_only_not_validation` である。

### 11.11 証拠完全性監査

`validation.yaml` と監査器は、次を機械的に検査する。

- source citationとdataset origin
- held-out状態
- measurement basisとcalibration
- artifact SHA-256
- evaluator SHA-256、version、result contract
- model input closure
- evaluation dataがtuningに使われていないこと
- acceptance metricとthreshold

NF3/ArとCl2/Arは宣言した `generated_self_consistency` として再現可能だが、generated、not held-out、synthetic detector countsであるため外部定量readyではない。この拒否は機能不全ではなく、証拠階層の誤表示を防ぐ機能である。

---

## 12. 評価指標の定義と解釈

### 12.1 スペクトル指標

chordごとのRMSEと正規化RMSEは

\[
\operatorname{RMSE}=\sqrt{\frac{1}{N}\sum_i(\widehat y_i-y_i)^2},
\]

\[
\operatorname{NRMSE}_{std}=\frac{\operatorname{RMSE}}{\operatorname{std}(\mathbf y)},
\qquad
\operatorname{NRMSE}_{range}=\frac{\operatorname{RMSE}}{\max y-\min y}
\]

である。相関係数は形状一致を示すが、scale・baseline誤差を単独では示さない。したがって相関、NRMSE、window面積、peak、ratioを併用する。

### 12.2 parameter回復

parameter groupの平均絶対相対誤差は

\[
\operatorname{MARE}=\frac{1}{P}\sum_{j=1}^P
\frac{|\widehat\theta_j-\theta_j^{truth}|}{\max(|\theta_j^{truth}|,\epsilon)}.
\]

truthがある生成benchmarkでのみ使える。実験データでtruthが無い場合、スペクトルfitをparameter accuracyへ読み替えない。

### 12.3 window・pair分類

線windowは面積比0.75–1.35、peak比0.80–1.25、peak shift 0.5 nm以内を既定good範囲とする。広帯域はそれぞれ0.50–1.80、0.60–1.50、3.0 nmである。pairは

\[
e_{ab}=\log(\widehat R_{ab})-\log(R_{ab})
\]

に対し、\(|e_{ab}|\le0.15\) をbalancedとする。これらは生成回帰用の分類閾値であり、外部実験の物理的受入公差ではない。

### 12.4 release gate

生成self-consistency gateは、pair/window/line分類の非劣化、相関低下0.002以内、NRMSE悪化5%以内、いずれかの分類5 percentage points以上改善、Cl2 pair accuracy 0.80以上を要求する。これはコード変更の回帰検知であり、論文データとのagreement判定ではない。

---

## 13. 物理量ごとの現在の到達点

| 対象 | 現在可能なこと | 現在の証拠 | まだ主張できないこと |
|---|---|---|---|
| 励起断面積 | 任意気体・状態のCSVをSI単位で積分し、範囲・hashを追跡 | analytic rate path、LXCat Ar感度 | 付属seed断面積の一般精度 |
| 励起状態密度 | 宣言した線形CR系をzoneごとに解く | 二準位・三準位閉形式 | 完全状態CRM、非線形化学組成 |
| 原子線 | 全分岐を含む光子・power生成 | cascade・NIST Ar pack・保存則 | trappingを含む一般放射輸送 |
| 分子band | 経験proxyと物理photon bandを使い分ける | analytic physical-band試験 | rovibronic state-complete CRM |
| \(T_e\) | 低次元EEDF族のparameterとして条件付きfit | NF3生成case | 外部実験に対する定量精度 |
| \(n_e\) | 絶対校正・source closure時にfit | 二バンドabsolute生成case | 相対スペクトルのみからの絶対回復 |
| EEDF | Maxwell/Druyvesteyn/bi-Maxwell/tabulated前向き、低次元逆解析 | Ar EEDF-family感度 | 自由形状EEDFの一意な外部回復 |
| 多気体 | species pack namespaceと外部密度で合成 | CF4/O2/Ar composition test | 自己無撞着な多気体global chemistry |

---

## 14. 現在の限界と、次に必要な科学的検証

### 14.1 model discrepancy

現在のLaplace共分散は測定・校正共分散を条件としており、断面積、分岐、消光、band yield、幾何、未記述機構の不確かさを含まない。Arellano評価で断面積族間差が3.68–5.09倍に達したことから、少なくとも主要線について複数データ源またはuncertainty-bearing断面積が必要である。

### 14.2 EEDF同定

EEDFの自由度を増やす前に、観測核のrank、選択線のthreshold分布、装置分解能、絶対scale、cross-section uncertaintyを評価すべきである。現時点では、Maxwell/bi-Maxwell等の宣言した低次元族内での条件付き推定に限定するのが妥当である。

### 14.3 外部定量benchmark

優先すべき外部benchmarkは、次を同一運転点で満たす必要がある。

1. rawまたは再配布可能な応答補正済みスペクトル
2. pointwiseまたはfeature covariance
3. 独立 \(n_e\)、\(T_e\) またはEEDF
4. source species・metastable密度、またはそれらを消去できる観測設計
5. 装置関数・視線幾何・absolute calibration
6. fitに使わないheld-out線または運転点
7. 事前固定したacceptance metricとtolerance

この条件を満たさないデータに合わせて新しいglobal chemistryを追加することは、OESCR核の検証ではなく、未検証subsystemで入力不足を埋めることになるため行わない。

---

## 15. 再現手順

### 15.1 解析・単体・契約試験

```bash
pytest -q
ruff check oescr tests scripts
pyrefly check
lint-imports
radon cc oescr
radon mi oescr
```

### 15.2 最小用途

```bash
python scripts/run_inverse.py \
  examples/use_cases/two_band/case_ratio_init.yaml \
  examples/use_cases/two_band/inverse_ratio.yaml \
  --out .local_outputs/two_band_ratio --record-trace

python scripts/run_inverse.py \
  examples/use_cases/two_band/case_absolute_init.yaml \
  examples/use_cases/two_band/inverse_absolute.yaml \
  --out .local_outputs/two_band_absolute --record-trace
```

### 15.3 NF3/Ar・Cl2/Ar最適化診断

```bash
python scripts/run_inverse.py \
  examples/benchmarks/nf3_ar_ccp_clean_2023/case_init.yaml \
  examples/benchmarks/nf3_ar_ccp_clean_2023/inverse.yaml \
  --out .local_outputs/optimization_diagnostics/nf3 --record-trace

python scripts/run_inverse.py \
  examples/benchmarks/cl2_ar_icp_fuller2001/case_init.yaml \
  examples/benchmarks/cl2_ar_icp_fuller2001/inverse.yaml \
  --out .local_outputs/optimization_diagnostics/cl2 --record-trace

python scripts/generate_optimization_diagnostic_figures.py
```

### 15.4 証拠監査と外部Ar感度

```bash
python scripts/audit_validation_evidence.py

python scripts/assess_arellano_atomic_model.py \
  --bsr-download path/to/lxcat_bsr_download.txt \
  --ngfsrdw-download path/to/lxcat_ngfsrdw_download.txt
```

LXCat raw downloadはredistribution条件のためrepositoryへ格納せず、外部入力として使用する。評価artifactはprocess ID、row count、numeric SHA-256によって同一性を確認する。

---

## 16. 参考文献・データ源

1. T. van der Mullen, “On the atomic state distribution function in inductively coupled plasmas—I. Thermodynamic equilibrium and departure from equilibrium,” *Physics Reports* 191 (1990). [doi:10.1016/0370-1573(90)90010-E](https://doi.org/10.1016/0370-1573(90)90010-E). CRモデル一般の理論背景。
2. T. Holstein, “Imprisonment of Resonance Radiation in Gases,” *Physical Review* 72 (1947) 1212. [doi:10.1103/PhysRev.72.1212](https://doi.org/10.1103/PhysRev.72.1212). 放射閉じ込めの理論背景。OESCRのslab式は簡略escape-factor近似であり、同論文の完全輸送解ではない。
3. A. Kramida, Yu. Ralchenko, J. Reader, and NIST ASD Team, *NIST Atomic Spectra Database*, SRD 78. [doi:10.18434/T4W30F](https://doi.org/10.18434/T4W30F), [NIST ASD](https://physics.nist.gov/asd). 波長、準位、遷移確率、Ar分岐の基準。
4. M. J. Druyvesteyn, “Der Niedervoltbogen,” *Zeitschrift für Physik* 64 (1930) 781–798. [doi:10.1007/BF01773007](https://doi.org/10.1007/BF01773007). Druyvesteyn型電子分布の歴史的背景。OESCR式の `te_eV` は平均energyではなく形状scaleである。
5. S. Pancheshnyi et al., “The LXCat project: Electron scattering cross sections and swarm parameters for low temperature plasma modeling,” *Chemical Physics* 398 (2012) 148–153. [doi:10.1016/j.chemphys.2011.04.020](https://doi.org/10.1016/j.chemphys.2011.04.020). LXCatデータ基盤。
6. O. Zatsarinny, Y. Wang, and K. Bartschat, “Electron-impact excitation of argon at intermediate energies,” *Physical Review A* 89 (2014) 022706. [doi:10.1103/PhysRevA.89.022706](https://doi.org/10.1103/PhysRevA.89.022706). BSR-500 Ar励起断面積。
7. S. Kaur, R. Srivastava, R. P. McEachran, and A. D. Stauffer, “Electron impact excitation of the np5(n+1)p states of Ar, Kr and Xe atoms,” *Journal of Physics B* 31 (1998) 4833–4852. [doi:10.1088/0953-4075/31/21/015](https://doi.org/10.1088/0953-4075/31/21/015). NGFSRDW Ar励起断面積。
8. J. E. Chilton, J. B. Boffard, R. S. Schappe, and C. C. Lin, *Physical Review A* 57 (1998) 267–277. [doi:10.1103/PhysRevA.57.267](https://doi.org/10.1103/PhysRevA.57.267). Ar直接励起とcascade anchor。
9. F. J. Arellano et al., *Plasma Sources Science and Technology* 32 (2023) 125007. [doi:10.1088/1361-6595/ad0ede](https://doi.org/10.1088/1361-6595/ad0ede). Ar 763.5/750.4 nm外部線比候補。
10. L. Schuecke et al., *Plasma Sources Science and Technology* 34 (2025) 045015. [doi:10.1088/1361-6595/adcbd3](https://doi.org/10.1088/1361-6595/adcbd3). N2/O2 ICPの絶対UV・NO・電子状態候補データ。
11. N. C. M. Fuller, I. P. Herman, and V. M. Donnelly, “Optical actinometry of Cl2, Cl, Cl+, and Ar+ densities in inductively coupled Cl2-Ar plasmas,” *Journal of Applied Physics* 90 (2001) 3182–3191. [doi:10.1063/1.1391222](https://doi.org/10.1063/1.1391222). Cl2/Ar生成benchmarkの物理的anchor。
12. S. An and S. J. Hong, “Spectroscopic Analysis of NF3 Plasmas with Oxygen Additive for PECVD Chamber Cleaning,” *Coatings* 13 (2023) 91. [doi:10.3390/coatings13010091](https://doi.org/10.3390/coatings13010091). NF3/Ar生成benchmarkの発光特徴anchor。
13. R. Storn and K. Price, “Differential Evolution—A Simple and Efficient Heuristic for Global Optimization over Continuous Spaces,” *Journal of Global Optimization* 11 (1997) 341–359. [doi:10.1023/A:1008202821328](https://doi.org/10.1023/A:1008202821328). global最適化。
14. M. A. Branch, T. F. Coleman, and Y. Li, “A Subspace, Interior, and Conjugate Gradient Method for Large-Scale Bound-Constrained Minimization Problems,” *SIAM Journal on Scientific Computing* 21 (1999) 1–23. [doi:10.1137/S1064827595289108](https://doi.org/10.1137/S1064827595289108). bound-constrained Trust Region Reflective法の背景。
15. SciPy Developers, [`scipy.optimize.least_squares`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) and [`scipy.optimize.differential_evolution`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html). OESCRが直接利用する数値実装のAPI仕様。

---

## 17. 結論

OESCRの強みは、巨大な一体型global modelではなく、EEDF、断面積積分、線形CR、放射、幾何、装置、逆解析を、入力・単位・診断を明示して接続する点にある。解析解と保存則に対する数理検証、生成スペクトルに対するend-to-end回帰、外部データ候補に対するclosure監査は実装済みである。

一方、現在の最も重要な科学的結論は「外部定量精度をまだ主張しない」ことである。NF3/ArとCl2/Arは有用な生成回帰であり、Arellano Arは断面積model discrepancyを定量的に露出し、Schuecke N2/O2は未測定metastableが比較を閉じないことを示した。次の完成条件は、新しい複雑な化学層を追加することではなく、OESCRの既存経路に合う校正済みheld-outデータと独立入力を確保し、Te・ne・低次元EEDFの推定精度を固定公差で評価することである。
