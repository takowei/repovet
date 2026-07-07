import pytest

from repovet.errors import InputError
from repovet.targets import parse_target, read_batch_file


def test_parse_valid_gh_target():
    t = parse_target("gh:psf/requests")
    assert t.kind == "gh"
    assert t.owner == "psf"
    assert t.repo == "requests"
    assert t.slug == "psf/requests"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "psf/requests",  # missing gh: prefix
        "npm:left-pad",  # unsupported prefix in M0
        "gh:no-slash-here",
        "gh:/missing-owner",
        "gh:owner/",
    ],
)
def test_parse_invalid_target_raises(raw):
    with pytest.raises(InputError):
        parse_target(raw)


def test_read_batch_file_skips_blank_and_comments(tmp_path):
    f = tmp_path / "targets.txt"
    f.write_text("gh:psf/requests\n\n# a comment\ngh:fastapi/fastapi\n")
    assert read_batch_file(str(f)) == ["gh:psf/requests", "gh:fastapi/fastapi"]


def test_read_batch_file_missing_raises():
    with pytest.raises(InputError):
        read_batch_file("/no/such/file.txt")


def test_read_batch_file_empty_raises(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("\n# only comments\n")
    with pytest.raises(InputError):
        read_batch_file(str(f))
