# wagom-player (Windows向けシンプル動画プレーヤー)

PyQt5 + python-vlc を使った最小構成のデスクトップ動画プレーヤーです。GOM Player風のキーボード操作、複数ファイルの連続再生、PageUp/PageDownでの移動などを備えています。

## 必要要件

- Python 3.9+
- VLC 本体（libvlcが必要）
  - https://www.videolan.org/ から VLC をインストールしてください（通常は自動検出されます）。
  - もし自動検出されない場合は、環境変数 `PYTHON_VLC_LIB_PATH` に `libvlc.dll` のあるディレクトリ（例: `C:\\Program Files\\VideoLAN\\VLC`）を設定してください。

## セットアップ

```
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## 実行

- エクスプローラから複数の動画を選択して本アプリにドラッグ&ドロップ、または引数で渡せます。
- アプリ起動時にファイルパスを引数で渡すと、それらがプレイリストに追加されます。

```
python app.py <file1> <file2> ...
```

アプリ内のメニュー「ファイル > 開く」からも複数選択可能です。

## 主なキーボード操作（既定）

- 左右矢印: 10秒シーク（←: -10s / →: +10s）
- テンキー4: 60秒戻る（NumLockが有効なテンキー入力）
- テンキー1: 60秒進む
- PageUp / PageDown: 前/次の動画へ移動
- スペース: 再生/一時停止
- テンキー8: アプリを閉じる
- テンキー0: ウィンドウ最大化/元に戻す切り替え

## 既知の注意点

- Windows向けに `set_hwnd` を使用して描画ハンドルを渡しています。他OSでは調整が必要です。
- コーデック対応はVLCに依存します。再生可否はお使いのVLCに準じます。

## ライセンス

このリポジトリのコードはサンプル用途です（ライセンス未設定）。
