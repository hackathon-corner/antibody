import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from agent.validator import CandidateValidator, ValidationError
from contracts import Candidate

ALLOWED_PATH = "routes/search.ts"
BASE_COMMIT = "abc123"


def make_candidate(patch: str, base_commit: str = BASE_COMMIT) -> Candidate:
    return Candidate(
        candidate_id="c1",
        run_id="r1",
        base_commit=base_commit,
        patch=patch,
        content_hash="",
        origin="guild-agent",
    )


def diff(path: str) -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"


@pytest.fixture
def validator() -> CandidateValidator:
    return CandidateValidator(allowed_paths=(ALLOWED_PATH,), expected_base_commit=BASE_COMMIT)


def test_accepts_in_scope_patch(validator: CandidateValidator) -> None:
    candidate = make_candidate(diff(ALLOWED_PATH))
    result_hash = validator.validate(candidate)
    assert result_hash == validator.compute_hash(candidate.patch)


def test_hash_is_deterministic_and_content_bound(validator: CandidateValidator) -> None:
    a = make_candidate(diff(ALLOWED_PATH))
    b = make_candidate(diff(ALLOWED_PATH) + "\n")  # trivially different content
    assert validator.validate(a) != validator.validate(b)


def test_rejects_empty_patch(validator: CandidateValidator) -> None:
    with pytest.raises(ValidationError, match="no changed files"):
        validator.validate(make_candidate(""))


def test_rejects_stale_base_commit(validator: CandidateValidator) -> None:
    candidate = make_candidate(diff(ALLOWED_PATH), base_commit="stale-commit")
    with pytest.raises(ValidationError, match="stale base commit"):
        validator.validate(candidate)


def test_rejects_forbidden_path(validator: CandidateValidator) -> None:
    candidate = make_candidate(diff("tests/e2e/search.test.ts"))
    with pytest.raises(ValidationError, match="forbidden path"):
        validator.validate(candidate)


def test_rejects_multi_file_patch_with_one_forbidden_path(validator: CandidateValidator) -> None:
    patch = diff(ALLOWED_PATH) + diff("config/semgrep/rules.yml")
    with pytest.raises(ValidationError, match="forbidden path"):
        validator.validate(make_candidate(patch))


def test_accepts_multi_file_patch_when_all_paths_allowed() -> None:
    validator = CandidateValidator(
        allowed_paths=(ALLOWED_PATH, "routes/other.ts"),
        expected_base_commit=BASE_COMMIT,
    )
    patch = diff(ALLOWED_PATH) + diff("routes/other.ts")
    result_hash = validator.validate(make_candidate(patch))
    assert result_hash == validator.compute_hash(patch)


def test_rejects_malformed_diff_with_no_recognizable_path_header(validator: CandidateValidator) -> None:
    with pytest.raises(ValidationError, match="no changed files"):
        validator.validate(make_candidate("this is not a unified diff at all"))


def test_changed_paths_ignores_unrelated_plus_plus_plus_text(validator: CandidateValidator) -> None:
    # Guards the regex against false positives on content that merely
    # contains "+++ " without being a real diff header.
    patch = "some content\n+++ not a real header\nmore content\n"
    assert validator.changed_paths(patch) == frozenset()
