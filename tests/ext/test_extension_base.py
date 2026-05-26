"""Validate ExtensionBase as a convenient default."""

from stag.ext import ExtensionBase, InitContext, Violation


class MyExt(ExtensionBase):
    name = "myext"
    version = "0.1"

    def default_aliases(self) -> dict[str, str]:
        return {"do": "myext do-the-thing"}


def test_inherited_defaults():
    ext = MyExt()
    assert ext.name == "myext"
    assert ext.default_aliases() == {"do": "myext do-the-thing"}
    assert ext.validate(handle=None) == []  # type: ignore[arg-type]


def test_violation_dataclass():
    v = Violation(extension="git", kind="non_descendant", message="msg", details={"sha": "abc"})
    assert v.extension == "git"
    assert v.details == {"sha": "abc"}


def test_init_context_dataclass():
    ctx = InitContext(run_id="run_x", run_dir="/tmp/foo", options={"ext_git_no_hooks": True})
    assert ctx.run_id == "run_x"
    assert ctx.options["ext_git_no_hooks"] is True
