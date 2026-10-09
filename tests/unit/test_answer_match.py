import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from server.answer_match import compare, extract_function, normalize

ANSWER = """export function searchProducts () {
  return (req, res) => {
    models.sequelize.query(`SELECT 1 WHERE x = :q`, { replacements: { q } })
  }
}"""

CANDIDATE_SAME = """import x from 'y'
// vuln-code-snippet start unionSqlInjectionChallenge
export function searchProducts () {
  return (req, res) => {
    models.sequelize.query(  `SELECT 1 WHERE x = :q`,
      { replacements: { q } })  // vuln-code-snippet vuln-line unionSqlInjectionChallenge
    if (notSolved()) { // vuln-code-snippet hide-start
      solve({ a: 1 })
    } // vuln-code-snippet hide-end
  }
}
// vuln-code-snippet end unionSqlInjectionChallenge
"""


@pytest.fixture
def codefixes(tmp_path):
    (tmp_path / "unionSqlInjectionChallenge_2_correct.ts").write_text(ANSWER)
    (tmp_path / "unionSqlInjectionChallenge_1.ts").write_text(ANSWER.replace(":q", "'${q}'"))
    return tmp_path


def test_extract_function_matches_braces():
    assert extract_function(CANDIDATE_SAME).rstrip().endswith("}")
    assert "import x" not in extract_function(CANDIDATE_SAME)
    assert extract_function("const a = 1") is None


def test_hidden_block_comments_and_whitespace_ignored(codefixes):
    best = compare(CANDIDATE_SAME, codefixes)[0]
    assert best.reference == "unionSqlInjectionChallenge_2_correct.ts" and best.exact


def test_different_fix_is_not_exact(codefixes):
    other = CANDIDATE_SAME.replace("{ replacements: { q } }", "{ bind: [q] }")
    assert not any(m.exact for m in compare(other, codefixes))


def test_normalize_strips_block_comments():
    assert normalize("a /* x */ b // y\n c") == "abc"


def test_missing_function_or_references_raise(tmp_path, codefixes):
    with pytest.raises(ValueError):
        compare("nothing here", codefixes)
    with pytest.raises(FileNotFoundError):
        compare(CANDIDATE_SAME, tmp_path / "empty")
