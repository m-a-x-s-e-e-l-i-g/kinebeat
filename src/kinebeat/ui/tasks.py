from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


class TaskWorker(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, task: Callable[..., Any]) -> None:
        super().__init__()
        self._task = task
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self._task(
                progress=self.progress.emit,
                cancelled=self._cancelled.is_set,
            )
        except Exception as error:  # noqa: BLE001 - surfaced to the desktop UI
            self.failed.emit(str(error))
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()
