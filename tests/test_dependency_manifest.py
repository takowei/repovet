from repovet.dependency_manifest import (
    parse_package_json_dependencies,
    parse_pyproject_dependencies,
    parse_requirements_txt,
)


def test_requirements_txt_extracts_names_ignoring_version_specifiers():
    content = """
        requests>=2.31.0
        django==4.2 ; python_version >= '3.8'
        click
        # a comment
        -r other.txt
        -e git+https://example.com/foo.git#egg=foo
    """
    names = parse_requirements_txt(content)
    assert names == ["requests", "django", "click"]


def test_requirements_txt_skips_blank_lines():
    assert parse_requirements_txt("\n\n  \n") == []


def test_pyproject_dependencies_pep621():
    content = """
[project]
name = "demo"
dependencies = ["requests>=2.31", "click"]

[project.optional-dependencies]
dev = ["pytest>=7.0", "ruff"]
"""
    names = parse_pyproject_dependencies(content)
    assert names == ["requests", "click", "pytest", "ruff"]


def test_pyproject_with_no_project_table_returns_empty():
    assert parse_pyproject_dependencies("[tool.other]\nx = 1\n") == []


def test_pyproject_malformed_toml_returns_empty_not_raise():
    assert parse_pyproject_dependencies("this is not [ valid toml") == []


def test_package_json_dependencies_and_dev_dependencies():
    content = """
    {
        "name": "demo",
        "dependencies": {"lodash": "^4.17.0", "express": "^4.18.0"},
        "devDependencies": {"jest": "^29.0.0"}
    }
    """
    names = parse_package_json_dependencies(content)
    assert set(names) == {"lodash", "express", "jest"}


def test_package_json_malformed_returns_empty_not_raise():
    assert parse_package_json_dependencies("{not valid json") == []
