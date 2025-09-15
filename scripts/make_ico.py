from pathlib import Path
from PyQt5 import QtCore, QtGui, QtSvg


def svg_to_ico(svg_path: Path, ico_path: Path, size: int = 256) -> None:
    svg_path = svg_path.resolve()
    ico_path = ico_path.resolve()
    renderer = QtSvg.QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise SystemExit(f"Invalid SVG: {svg_path}")

    image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(image)
    try:
        vb = renderer.viewBoxF()
        if vb.width() <= 0 or vb.height() <= 0:
            # fallback to identity
            renderer.render(painter)
        else:
            scale = min(size / vb.width(), size / vb.height())
            tw = vb.width() * scale
            th = vb.height() * scale
            dx = (size - tw) / 2.0
            dy = (size - th) / 2.0
            painter.translate(dx, dy)
            painter.scale(scale, scale)
            renderer.render(painter)
    finally:
        painter.end()

    if not image.save(str(ico_path), b"ICO"):
        raise SystemExit(f"Failed to save ICO: {ico_path}")


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    svg = base / "resources" / "icons" / "app.svg"
    ico = base / "resources" / "icons" / "app.ico"
    svg_to_ico(svg, ico)
    print(f"[i] ICO generated at: {ico}")

