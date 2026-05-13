import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets", exc_type=ImportError)
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv[:1])
    return app
