"""缩略图：按小尺寸读、后台算、算好之前显示空底槽。

按需加载 —— 列表只在要画某一行时才调 get()，所以只算屏幕上看得见的那些。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

THUMB = 64


def read_thumbnail(path: Path, size: int = THUMB) -> QImage | None:
    """只把需要的像素解出来 —— 2048×2048 的图读 64px 就够。"""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source = reader.size()
    if source.isValid() and (source.width() > size or source.height() > size):
        reader.setScaledSize(source.scaled(size, size, Qt.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return None
    if image.width() > size or image.height() > size:
        image = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


class _Signals(QObject):
    done = Signal(str, object)


class _Task(QRunnable):
    def __init__(self, key: str, path: Path, size: int, signals: _Signals) -> None:
        super().__init__()
        self._key = key
        self._path = path
        self._size = size
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # 线程里只能造 QImage，QPixmap 必须回主线程
        try:
            image = read_thumbnail(self._path, self._size)
        except Exception:
            image = None
        self._signals.done.emit(self._key, image)


class ThumbCache(QObject):
    """路径 → 64×64 缩略图。读不出来的记一笔 None，不反复重试。"""

    ready = Signal(str)

    def __init__(self, size: int = THUMB, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._pixmaps: dict[str, QPixmap | None] = {}
        self._inflight: set[str] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._signals = _Signals(self)
        self._signals.done.connect(self._store)

    def get(self, path: Path | str | None) -> QPixmap | None:
        if path is None:
            return None
        key = str(path)
        if key in self._pixmaps:
            return self._pixmaps[key]
        if key not in self._inflight:
            self._inflight.add(key)
            self._pool.start(_Task(key, Path(path), self._size, self._signals))
        return None

    def finished(self, path: Path | str | None) -> bool:
        """已经试过了（不管成没成）。用来区分"还在算"和"读不出来"。"""
        return path is not None and str(path) in self._pixmaps

    def _store(self, key: str, image: QImage | None) -> None:
        self._inflight.discard(key)
        self._pixmaps[key] = None if image is None else QPixmap.fromImage(image)
        self.ready.emit(key)

    def clear(self) -> None:
        self._pixmaps.clear()
        self._inflight.clear()

    def size(self) -> QSize:
        return QSize(self._size, self._size)
