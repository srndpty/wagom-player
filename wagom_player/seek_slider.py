from PyQt5 import QtCore, QtGui, QtWidgets


class SeekSlider(QtWidgets.QSlider):
    """クリック位置ジャンプ + ドラッグ追従 + 1分ごとの目盛り線描画スライダ"""

    clickedValue = QtCore.pyqtSignal(int)

    # ### 変更点: paintEventメソッドを追加 ###
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """スライダーの背景に1分ごとの目盛り線を描画する"""
        # 最初に、スライダーのデフォルト描画（溝、ハンドルなど）を実行する
        super().paintEvent(event)

        # 動画の総時間（ミリ秒）を取得。動画が読み込まれていなければ何もしない。
        duration = self.maximum()
        if duration <= 0:
            return

        # --- 描画準備 ---
        painter = QtGui.QPainter(self)
        
        # 目盛り線の色とスタイルを設定 (白の半透明)
        pen_color = QtGui.QColor(255, 255, 255, 100)  # RGBA (A=100で半透明)
        pen = QtGui.QPen(pen_color)
        pen.setWidth(4)  # 線の太さ
        painter.setPen(pen)

        # --- 目盛り線の位置を計算して描画 ---
        
        # QStyleOptionSliderを使って、スライダーの描画に必要な情報を取得する
        # これにより、異なるOSやテーマでも正確な位置に描画できる
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        
        # スライダーの「溝」部分の矩形領域を取得する
        groove_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self
        )
        
        tick_interval_ms = 60 * 1000  # 1分 = 60000ミリ秒
        
        # 1分から、動画の長さを超えない範囲でループ
        current_ms = tick_interval_ms
        while current_ms < duration:
            # 現在の時間（ミリ秒）が、スライダーの溝の中でどのX座標に対応するかを計算
            x = self.style().sliderPositionFromValue(
                self.minimum(),
                self.maximum(),
                current_ms,
                groove_rect.width(),
            ) + groove_rect.x()

            # 計算したX座標に縦線を描画
            painter.drawLine(x, groove_rect.top(), x, groove_rect.bottom())

            # 次の1分へ
            current_ms += tick_interval_ms

    def _pos_to_value(self, event: QtGui.QMouseEvent) -> int:
        if self.orientation() == QtCore.Qt.Horizontal:
            pos = event.pos().x()
            span = max(1, self.width())
        else:
            pos = self.height() - event.pos().y()
            span = max(1, self.height())
        rng = self.maximum() - self.minimum()
        val = self.minimum() + int(rng * pos / span)
        return max(self.minimum(), min(self.maximum(), val))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            val = self._pos_to_value(event)
            self.setSliderDown(True)
            self.setValue(val)
            try:
                self.sliderPressed.emit()
                self.sliderMoved.emit(val)
            except Exception:
                pass
            self.clickedValue.emit(val)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.LeftButton and self.isSliderDown():
            val = self._pos_to_value(event)
            if val != self.value():
                self.setValue(val)
                try:
                    self.sliderMoved.emit(val)
                except Exception:
                    pass
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            try:
                self.sliderReleased.emit()
            except Exception:
                pass
            event.accept()
            return
        super().mouseReleaseEvent(event)