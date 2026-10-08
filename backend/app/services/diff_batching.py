"""Split a unified PR diff into context-window-sized batches for review.

Pure functions only: no I/O, no settings. Sizes are measured in characters; token budgets are converted with a
conservative ``CHARS_PER_TOKEN`` because code tokenizes densely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CHARS_PER_TOKEN = 3
CONTEXT_SAFETY_RATIO = 0.9

NOISE_FILENAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "go.sum",
        "composer.lock",
        "Gemfile.lock",
    }
)
NOISE_SUFFIXES = (".min.js", ".min.css", ".map")
NOISE_DIRS = ("vendor/", "node_modules/", "dist/", "build/")

DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$", re.MULTILINE)
HUNK_START_RE = re.compile(r"^@@", re.MULTILINE)
UNPARSED_PATH = "(diff)"


def count_changed_lines(diff: str) -> int:
    return sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))


def _count(diff: str, sign: str) -> int:
    return sum(1 for line in diff.splitlines() if line.startswith(sign) and not line.startswith(sign * 3))


@dataclass(frozen=True)
class FileDiff:
    path: str
    header: str
    hunks: tuple[str, ...]
    binary: bool = False

    @property
    def text(self) -> str:
        return self.header + "".join(self.hunks)

    @property
    def changed_lines(self) -> int:
        return sum(count_changed_lines(h) for h in self.hunks)

    @property
    def additions(self) -> int:
        return sum(_count(h, "+") for h in self.hunks)

    @property
    def deletions(self) -> int:
        return sum(_count(h, "-") for h in self.hunks)


@dataclass
class DiffBatch:
    text: str = ""
    paths: list[str] = field(default_factory=list)
    changed_lines: int = 0

    def add(self, path: str, text: str) -> None:
        self.text += text
        if path not in self.paths:
            self.paths.append(path)
        self.changed_lines += count_changed_lines(text)


@dataclass(frozen=True)
class BatchPlan:
    batches: list[DiffBatch]
    files: list[FileDiff]
    filtered: list[str]
    cut_files: list[str]
    overflow: list[str]
    budget_chars: int


def is_noise_path(path: str) -> bool:
    """True for lockfiles, minified/source-map files and vendored or build output."""
    name = path.rsplit("/", 1)[-1]
    if name in NOISE_FILENAMES or name.endswith(NOISE_SUFFIXES):
        return True
    padded = f"/{path}"
    return any(f"/{d}" in padded for d in NOISE_DIRS)


def parse_file_diffs(diff: str) -> list[FileDiff]:
    """Split a unified diff into per-file sections. Text before the first file header is ignored.

    A non-empty diff without any ``diff --git`` header is returned as one pseudo-file so it is still reviewed.
    """
    headers = list(DIFF_HEADER_RE.finditer(diff))
    if not headers:
        return [FileDiff(UNPARSED_PATH, "", (diff,))] if diff.strip() else []

    files: list[FileDiff] = []
    for idx, match in enumerate(headers):
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(diff)
        section = diff[match.start() : end]
        starts = [m.start() for m in HUNK_START_RE.finditer(section)]
        header = section[: starts[0]] if starts else section
        bounds = [*starts, len(section)]
        hunks = tuple(section[bounds[i] : bounds[i + 1]] for i in range(len(starts)))
        a_path, b_path = match.group(1), match.group(2)
        path = a_path if "\n+++ /dev/null" in header else b_path
        binary = "\nBinary files " in header or "\nGIT binary patch" in header
        files.append(FileDiff(path, header, hunks, binary))
    return files


def _hard_cut(prefix: str, line: str, budget: int) -> list[str]:
    room = max(budget - len(prefix), 1_000)
    return [prefix + line[i : i + room] for i in range(0, len(line), room)]


def split_oversized(file: FileDiff, budget: int) -> tuple[list[str], bool]:
    """Split one file's diff into pieces of at most ``budget`` characters, each starting with the file header.

    Returns ``(pieces, hard_cut)``; ``hard_cut`` is True when a single line had to be cut mid-line.
    """
    header = file.header
    pieces: list[str] = []
    current = header
    hard_cut = False

    def flush() -> None:
        nonlocal current
        if current != header:
            pieces.append(current)
        current = header

    for hunk in file.hunks:
        if len(header) + len(hunk) <= budget:
            if len(current) + len(hunk) > budget:
                flush()
            current += hunk
            continue
        flush()
        hunk_head, _, body = hunk.partition("\n")
        prefix = f"{header}{hunk_head}\n"
        chunk = prefix
        for line in body.splitlines(keepends=True):
            if len(prefix) + len(line) > budget:
                if chunk != prefix:
                    pieces.append(chunk)
                pieces.extend(_hard_cut(prefix, line, budget))
                chunk = prefix
                hard_cut = True
                continue
            if len(chunk) + len(line) > budget:
                pieces.append(chunk)
                chunk = prefix
            chunk += line
        if chunk != prefix:
            pieces.append(chunk)
    flush()
    return pieces, hard_cut


def pack_batches(files: list[FileDiff], budget: int) -> tuple[list[DiffBatch], list[str]]:
    """Greedily pack files (in order) into batches of at most ``budget`` characters.

    Returns ``(batches, cut_files)``.
    """
    batches: list[DiffBatch] = []
    cut_files: list[str] = []
    current = DiffBatch()

    def place(path: str, text: str) -> None:
        nonlocal current
        if current.text and len(current.text) + len(text) > budget:
            batches.append(current)
            current = DiffBatch()
        current.add(path, text)

    for file in files:
        text = file.text
        if len(text) <= budget:
            place(file.path, text)
            continue
        pieces, hard_cut = split_oversized(file, budget)
        if hard_cut:
            cut_files.append(file.path)
        for piece in pieces:
            place(file.path, piece)
    if current.text:
        batches.append(current)
    return batches, cut_files


def plan_batches(diff: str, *, target_chars: int, ceiling_chars: int, max_batches: int) -> BatchPlan:
    """Filter noise and pack the diff into at most ``max_batches`` batches.

    The batch budget starts at ``min(target_chars, ceiling_chars)`` and doubles (capped at the ceiling) while more
    than ``max_batches`` batches are needed. Batches still beyond ``max_batches`` at the ceiling are dropped and their
    files listed in ``overflow``.
    """
    if ceiling_chars <= 0:
        raise ValueError("No room left in the context window for the diff")
    files = parse_file_diffs(diff)
    kept = [f for f in files if not (f.binary or is_noise_path(f.path))]
    filtered = [f.path for f in files if f.binary or is_noise_path(f.path)]

    budget = min(target_chars, ceiling_chars)
    batches, cut_files = pack_batches(kept, budget)
    while len(batches) > max_batches and budget < ceiling_chars:
        budget = min(budget * 2, ceiling_chars)
        batches, cut_files = pack_batches(kept, budget)

    overflow: list[str] = []
    if len(batches) > max_batches:
        kept_paths = {p for b in batches[:max_batches] for p in b.paths}
        for batch in batches[max_batches:]:
            overflow.extend(p for p in batch.paths if p not in kept_paths and p not in overflow)
        batches = batches[:max_batches]
    return BatchPlan(batches, files, filtered, cut_files, overflow, budget)


def token_ceiling_chars(*, context_tokens: int, max_output_tokens: int, reserved_chars: int) -> int:
    """Largest diff batch, in characters, that fits the context window next to ``reserved_chars`` of other input."""
    usable_tokens = context_tokens * CONTEXT_SAFETY_RATIO - max_output_tokens
    return int(usable_tokens * CHARS_PER_TOKEN) - reserved_chars
