# OESCRの理論・実装と数値検証

全25ページ、数式26件、図5点（うちベンチマーク図4組）、参考文献12件。OESCRを初めて読む研究者に向けて、低圧プラズマの分光診断における位置づけ、実装した方程式と近似、計算フロー、逆解析、物理項の改訂方法、複数ガス対応を論文形式で説明する。

[閲覧用PDF](../../output/pdf/oescr_theory_and_validation_ja.pdf)

本稿は2026年10月27日の保存した実装スナップショットと入力を記述する。以後のコード変更へ自動追従する文書ではない。掲載した生成データの回復試験と、独立実測による検証を区別する。実測に対する電子温度・電子密度の定量精度は未検証であり、Ar/Cl₂の共有状態例が回復判定に不合格となる結果も掲載する。

## 原稿と添付資料

- [主原稿](manuscript/main.tex)：各節を読み込むLaTeXソース。
- [図](figures/)：ベクトルPDFと確認用PNG。
- [数値実験の根拠・再現手順](evidence/README.md)：数値表、実行記録、環境、ソースと入力の固定コピー。
- [参考文献データ](references.bib)：出典をまとめたBibTeX。本文の参考文献は[手動組版用ファイル](manuscript/references.tex)を使用する。

数式はLaTeXの数式環境で組版し、図もベクトルPDFを埋め込む。閲覧・配布にはフォントを埋め込んだ最終PDFを用いる。

## 再組版

XeLaTeX互換の環境、またはTectonicを使用する。`manuscript/`を作業ディレクトリとして、例えば次のように組版する。

```powershell
tectonic main.tex
```

XeLaTeXを使う場合は、相互参照と目次を解決するために必要な回数だけ再実行する。生成される`main.pdf`が閲覧用PDFの元になる。ベンチマークの再計算は組版と独立しており、手順は[エビデンスの説明](evidence/README.md)を参照する。

現行プリアンブルはWindowsのYu Mincho、Yu Gothic、Times New Roman、Arial、Consolasを使用する。Linux等でこれらがない場合は、`manuscript/main.tex`冒頭のフォント指定を、利用可能な日本語・欧文フォントへ変更する。

原稿・図・数値・実行記録をまとめた[配布用一式](../../output/oescr_paper_bundle.zip)も利用できる。

このリポジトリでは `reproduce/build_pdf.ps1 -Compiler <tectonicの実行パス>` で閲覧用PDFを所定の出力先へ生成できる。
