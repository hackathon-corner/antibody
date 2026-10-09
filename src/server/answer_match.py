"""Compare a candidate's repaired function with upstream's reference answers (Q4 in docs/collab.md).

Juice Shop ships answers for its coding challenges in `data/static/codefixes/`. For
this target, `unionSqlInjectionChallenge_*.ts` hold the `searchProducts` function
with one fix each (`_2_correct` is the accepted one). A candidate that reproduces one
of them must be disclosed in the report. A match does not make the repair wrong, and
a non-match does not prove the agent never saw the answers.

Normalization strips upstream's `vuln-code-snippet` markers, the hidden challenge-solving
block between `hide-start` and `hide-end`, comments, and all whitespace.
`exact` is the signal. `similarity` is context only: every reference shares most of the
function with the vulnerable original, so all of them score around 0.9 even without a fix.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

CHALLENGE_GLOB = "unionSqlInjectionChallenge_*.ts"
FUNCTION = "searchProducts"

# Upstream hides whole lines: from the line holding hide-start through the line holding hide-end.
_HIDDEN = re.compile(r"^[^\n]*//\s*vuln-code-snippet hide-start.*?//\s*vuln-code-snippet hide-end[^\n]*$", re.S | re.M)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class AnswerMatch:
    reference: str
    exact: bool
    similarity: float


def extract_function(source: str, name: str = FUNCTION) -> str | None:
    """Return `export function <name> ... }` by brace matching, or None if absent."""
    start = source.find(f"export function {name}")
    if start < 0:
        return None
    open_at = source.find("{", start)
    depth = 0
    for i in range(open_at, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    return None


def normalize(code: str) -> str:
    code = _HIDDEN.sub("", code)
    code = _BLOCK_COMMENT.sub("", code)
    code = _LINE_COMMENT.sub("", code)
    return _WS.sub("", code)


def compare(candidate_file: str, codefix_dir: str | Path) -> list[AnswerMatch]:
    """Compare the candidate's searchProducts with each reference answer, best match first."""
    fn = extract_function(candidate_file)
    if fn is None:
        raise ValueError(f"candidate has no `export function {FUNCTION}`")
    ours = normalize(fn)
    refs = sorted(Path(codefix_dir).glob(CHALLENGE_GLOB))
    if not refs:
        raise FileNotFoundError(f"no {CHALLENGE_GLOB} under {codefix_dir}")
    matches = []
    for ref in refs:
        ref_fn = extract_function(ref.read_text()) or ref.read_text()
        theirs = normalize(ref_fn)
        matches.append(AnswerMatch(ref.name, ours == theirs, round(difflib.SequenceMatcher(None, ours, theirs).ratio(), 4)))
    return sorted(matches, key=lambda m: (not m.exact, -m.similarity))
