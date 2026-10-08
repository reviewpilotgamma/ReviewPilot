"""Diff batching: parsing, noise filtering, splitting, packing, budget growth and the context ceiling."""

from __future__ import annotations

import pytest

from app.services.diff_batching import (
    UNPARSED_PATH,
    FileDiff,
    count_changed_lines,
    is_noise_path,
    pack_batches,
    parse_file_diffs,
    plan_batches,
    split_oversized,
    token_ceiling_chars,
)


def file_diff(path: str, lines: int = 3, hunks: int = 1, width: int = 20) -> str:
    out = [f"diff --git a/{path} b/{path}\n", "index 1111111..2222222 100644\n", f"--- a/{path}\n", f"+++ b/{path}\n"]
    for h in range(hunks):
        out.append(f"@@ -{h * 10 + 1},1 +{h * 10 + 1},{lines} @@\n")
        out.extend(f"+{path}-{h}-{i}-".ljust(width, "x") + "\n" for i in range(lines))
    return "".join(out)


def hunk_lines(diff: str) -> list[str]:
    return [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


# --------------------------------------------------------------------------- parsing
def test_parse_multi_file_diff():
    diff = file_diff("src/a.py") + file_diff("src/b.py", hunks=2)
    files = parse_file_diffs(diff)
    assert [f.path for f in files] == ["src/a.py", "src/b.py"]
    assert len(files[1].hunks) == 2
    assert files[0].header.startswith("diff --git a/src/a.py")
    assert "".join(f.text for f in files) == diff
    assert files[0].additions == 3 and files[0].deletions == 0


def test_parse_rename_mode_deletion_and_binary():
    diff = (
        "diff --git a/old.py b/new.py\nsimilarity index 100%\nrename from old.py\nrename to new.py\n"
        "diff --git a/run.sh b/run.sh\nold mode 100644\nnew mode 100755\n"
        "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"
    )
    files = parse_file_diffs(diff)
    assert [f.path for f in files] == ["new.py", "run.sh", "gone.py", "logo.png"]
    assert [f.binary for f in files] == [False, False, False, True]
    assert files[0].hunks == () and files[2].deletions == 1


def test_parse_ignores_preamble_and_handles_headerless_diff():
    assert [f.path for f in parse_file_diffs("From abc\nSubject: x\n" + file_diff("a.py"))] == ["a.py"]
    [pseudo] = parse_file_diffs("+just a line\n")
    assert pseudo.path == UNPARSED_PATH and pseudo.text == "+just a line\n"
    assert parse_file_diffs("  \n") == []


@pytest.mark.parametrize(
    ("path", "noise"),
    [
        ("package-lock.json", True),
        ("web/yarn.lock", True),
        ("go.sum", True),
        ("static/app.min.js", True),
        ("static/app.min.css", True),
        ("static/app.js.map", True),
        ("vendor/lib/x.go", True),
        ("web/node_modules/a/index.js", True),
        ("dist/bundle.js", True),
        ("src/build/out.py", True),
        ("src/builder/x.py", False),
        ("src/app.js", False),
        ("docs/lockfile.md", False),
    ],
)
def test_is_noise_path(path, noise):
    assert is_noise_path(path) is noise


# --------------------------------------------------------------------------- splitting and packing
def test_pack_respects_budget_and_keeps_files_whole():
    files = parse_file_diffs("".join(file_diff(f"f{i}.py") for i in range(10)))
    budget = len(files[0].text) * 3 + 10
    batches, cut = pack_batches(files, budget)
    assert cut == []
    assert len(batches) == 4
    assert all(len(b.text) <= budget for b in batches)
    assert [p for b in batches for p in b.paths] == [f"f{i}.py" for i in range(10)]


def test_oversized_file_split_at_hunks_with_header_repeated():
    [file] = parse_file_diffs(file_diff("big.py", lines=5, hunks=6))
    budget = len(file.header) + max(len(h) for h in file.hunks) * 2 + 1
    pieces, hard_cut = split_oversized(file, budget)
    assert not hard_cut
    assert len(pieces) == 3
    assert all(p.startswith(file.header) and len(p) <= budget for p in pieces)


def test_oversized_hunk_cut_on_lines():
    [file] = parse_file_diffs(file_diff("big.py", lines=50, hunks=1))
    budget = len(file.header) + 400
    pieces, hard_cut = split_oversized(file, budget)
    assert not hard_cut and len(pieces) > 1
    assert all(p.startswith(file.header + "@@ -1,1 +1,50 @@\n") and len(p) <= budget for p in pieces)
    assert sum(count_changed_lines(p) for p in pieces) == 50


def test_oversized_line_is_hard_cut_and_reported():
    diff = file_diff("app.bundle.js", lines=1, width=10_000)
    [file] = parse_file_diffs(diff)
    budget = len(file.header) + 3_000
    batches, cut = pack_batches([file], budget)
    assert cut == ["app.bundle.js"]
    assert len(batches) > 1


def test_every_hunk_line_appears_exactly_once():
    diff = "".join(file_diff(f"m{i}.py", lines=40, hunks=3) for i in range(8)) + file_diff("yarn.lock", lines=500)
    plan = plan_batches(diff, target_chars=2_500, ceiling_chars=10_000, max_batches=500)
    batched = [line for b in plan.batches for line in hunk_lines(b.text)]
    expected = [line for f in plan.files if f.path != "yarn.lock" for line in hunk_lines(f.text)]
    assert sorted(batched) == sorted(expected)
    assert plan.filtered == ["yarn.lock"]
    assert all("yarn.lock" not in b.text for b in plan.batches)


# --------------------------------------------------------------------------- plan_batches
def test_plan_grows_budget_to_fit_max_batches():
    diff = "".join(file_diff(f"f{i}.py", lines=10) for i in range(120))
    one = len(parse_file_diffs(diff)[0].text)
    plan = plan_batches(diff, target_chars=one, ceiling_chars=one * 100, max_batches=50)
    assert len(plan.batches) <= 50
    assert plan.budget_chars > one
    assert plan.overflow == []


def test_plan_lists_overflow_when_ceiling_reached():
    diff = "".join(file_diff(f"f{i}.py", lines=10) for i in range(10))
    one = len(parse_file_diffs(diff)[0].text)
    plan = plan_batches(diff, target_chars=one, ceiling_chars=one, max_batches=4)
    assert len(plan.batches) == 4
    assert plan.overflow == [f"f{i}.py" for i in range(4, 10)]


def test_plan_filters_binary_and_rejects_non_positive_ceiling():
    diff = file_diff("a.py") + "diff --git a/x.png b/x.png\nBinary files a/x.png and b/x.png differ\n"
    plan = plan_batches(diff, target_chars=10_000, ceiling_chars=10_000, max_batches=5)
    assert plan.filtered == ["x.png"] and len(plan.batches) == 1
    with pytest.raises(ValueError):
        plan_batches(diff, target_chars=10_000, ceiling_chars=0, max_batches=5)


def test_token_ceiling_chars():
    assert token_ceiling_chars(context_tokens=1_000_000, max_output_tokens=10_000, reserved_chars=30_000) == 2_640_000
    assert token_ceiling_chars(context_tokens=10_000, max_output_tokens=9_000, reserved_chars=0) == 0


def test_file_diff_text_round_trip():
    f = FileDiff("a.py", "h\n", ("@@ x\n+1\n",))
    assert f.text == "h\n@@ x\n+1\n" and f.changed_lines == 1
