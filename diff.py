"""Turn two line-per-content-element snapshots into a short, readable
summary of what actually changed."""

import difflib


def summarize(old_text: str, new_text: str, max_lines: int = 12) -> list:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    raw = difflib.unified_diff(old_lines, new_lines, lineterm="", n=0)
    changed = [
        line for line in raw if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]

    # Repeated boilerplate (a CTA button appearing 6 times, say) produces the
    # same changed-line pair 6 times over — dedupe by content, keep order,
    # note how many times each occurred.
    counts = {}
    order = []
    for line in changed:
        if line not in counts:
            order.append(line)
        counts[line] = counts.get(line, 0) + 1

    deduped = [f"{line}  (×{counts[line]})" if counts[line] > 1 else line for line in order]
    return deduped[:max_lines]
