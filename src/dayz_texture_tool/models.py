from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProcessingResult:
    success: bool
    input_path: Path | None = None
    outputs: list[Path] = field(default_factory=list)
    processor: str = ""
    elapsed_ms: int = 0
    error: str = ""
    messages: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    results: list[ProcessingResult] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failed(self) -> int:
        return sum(1 for result in self.results if not result.success and result.error)

    @property
    def skipped(self) -> int:
        return sum(1 for result in self.results if not result.success and not result.error)

    @property
    def success(self) -> bool:
        return self.failed == 0

    @property
    def outputs(self) -> list[Path]:
        output_paths = []
        for result in self.results:
            output_paths.extend(result.outputs)
        return output_paths

    @property
    def elapsed_ms(self) -> int:
        return int((time.time() - self.start_time) * 1000)

    def add(self, result: ProcessingResult) -> None:
        self.results.append(result)
        self.messages.extend(result.messages)
