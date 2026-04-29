from typing import List

from PyQt5 import QtCore, QtGui, QtWidgets


class MetadataDialog(QtWidgets.QDialog):
    """メタデータを表示・コピーするためのダイアログ"""

    def __init__(self, metadata_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("動画ファイルのメタデータ")
        self.setMinimumSize(500, 400)

        self.text_edit = QtWidgets.QPlainTextEdit(self)
        self.text_edit.setPlainText(metadata_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QtGui.QFont("Courier New", 10))

        self.copy_button = QtWidgets.QPushButton("クリップボードにコピー")
        self.close_button = QtWidgets.QPushButton("閉じる")

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.copy_button)
        button_layout.addWidget(self.close_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(button_layout)

        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.close_button.clicked.connect(self.accept)

    def _copy_to_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.text_edit.toPlainText())
        self.copy_button.setText("コピーしました！")
        QtCore.QTimer.singleShot(
            1500, lambda: self.copy_button.setText("クリップボードにコピー")
        )


class ShortcutListDialog(QtWidgets.QDialog):
    """ショートカット一覧を表示するダイアログ"""

    def __init__(self, shortcut_rows: List[tuple], parent=None):
        super().__init__(parent)
        self.setWindowTitle("ショートカット一覧")
        self.setMinimumSize(520, 480)

        table = QtWidgets.QTableWidget(self)
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["ショートカット", "操作", "分類"])
        table.setRowCount(len(shortcut_rows))
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)

        for row, (key, description, category) in enumerate(shortcut_rows):
            for col, value in enumerate((key, description, category)):
                item = QtWidgets.QTableWidgetItem(value)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, col, item)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)

        close_button = QtWidgets.QPushButton("閉じる")
        close_button.clicked.connect(self.accept)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(table)
        main_layout.addLayout(button_layout)
