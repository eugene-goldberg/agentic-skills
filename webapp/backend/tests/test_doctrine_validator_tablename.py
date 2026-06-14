"""A36 fix #4 — unit tests for the tablename consistency parser + checker.

These tests exercise the pure parsing/check logic without touching git
or the filesystem (except via tmp_path for the integration check).
"""

from __future__ import annotations

from app.services.doctrine_validator import (
    _check_tablename_consistency,
    _parse_migration_table_names,
    _parse_models_for_tables,
)


# ─── _parse_models_for_tables ─────────────────────────────────────────────


def test_parse_models_default_tablename():
    """Class with table=True and no __tablename__ → lowercased class name."""
    src = """
class Item(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str
"""
    assert _parse_models_for_tables(src) == {"Item": "item"}


def test_parse_models_with_explicit_tablename():
    src = """
class WorkspaceMember(SQLModel, table=True):
    __tablename__ = "workspace_member"
    id: int = Field(default=None, primary_key=True)
"""
    assert _parse_models_for_tables(src) == {"WorkspaceMember": "workspace_member"}


def test_parse_models_camelcase_default():
    """CamelCase class name lowercases to one token (no separator)."""
    src = """
class WorkspaceMember(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
"""
    assert _parse_models_for_tables(src) == {"WorkspaceMember": "workspacemember"}


def test_parse_models_skips_non_table_classes():
    src = """
class WorkspaceBase(SQLModel):
    name: str

class Workspace(WorkspaceBase, table=True):
    id: int = Field(default=None, primary_key=True)

class WorkspaceCreate(WorkspaceBase):
    pass
"""
    # Only Workspace has table=True; the Base and Create variants don't.
    assert _parse_models_for_tables(src) == {"Workspace": "workspace"}


def test_parse_models_multiple_tables():
    src = """
class Item(SQLModel, table=True):
    pass

class User(SQLModel, table=True):
    __tablename__ = "users"
    pass
"""
    assert _parse_models_for_tables(src) == {"Item": "item", "User": "users"}


# ─── _parse_migration_table_names ─────────────────────────────────────────


def test_parse_migration_single_table():
    src = '''
def upgrade():
    op.create_table(
        "workspace",
        sa.Column("id", sa.Uuid(), nullable=False),
    )
'''
    assert _parse_migration_table_names(src) == {"workspace"}


def test_parse_migration_multiple_tables():
    src = '''
def upgrade():
    op.create_table("workspace", sa.Column("id", sa.Uuid()))
    op.create_table("workspace_member", sa.Column("id", sa.Uuid()))
'''
    assert _parse_migration_table_names(src) == {"workspace", "workspace_member"}


def test_parse_migration_handles_single_quotes():
    src = "op.create_table('item', sa.Column('id', sa.Integer()))"
    assert _parse_migration_table_names(src) == {"item"}


# ─── _check_tablename_consistency (integration) ──────────────────────────


def _write(tmp_path, rel: str, content: str):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return rel


def test_check_detects_workspacemember_mismatch(tmp_path):
    """The exact A36 documents_2 BL-0001 defect."""
    model_rel = _write(tmp_path, "backend/app/models.py", """
class WorkspaceMember(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
""")
    mig_rel = _write(
        tmp_path,
        "backend/app/alembic/versions/abc123_add_workspace.py",
        """
def upgrade():
    op.create_table('workspace_member', sa.Column('id', sa.Uuid()))
""",
    )
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [model_rel, mig_rel], acc)
    assert len(acc["missing"]) == 1
    msg = acc["missing"][0]
    assert "WorkspaceMember" in msg
    assert "workspacemember" in msg
    assert "workspace_member" in msg
    assert "A36" in msg


def test_check_passes_when_names_align(tmp_path):
    """Engineer correctly used __tablename__ override."""
    model_rel = _write(tmp_path, "backend/app/models.py", """
class WorkspaceMember(SQLModel, table=True):
    __tablename__ = "workspace_member"
    id: int = Field(default=None, primary_key=True)
""")
    mig_rel = _write(
        tmp_path,
        "backend/app/alembic/versions/abc123.py",
        "op.create_table('workspace_member', sa.Column('id', sa.Uuid()))",
    )
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [model_rel, mig_rel], acc)
    assert acc["missing"] == []


def test_check_passes_on_default_alignment(tmp_path):
    """Engineer used SQLModel default and migration matches it."""
    model_rel = _write(tmp_path, "backend/app/models.py", """
class Workspace(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
""")
    mig_rel = _write(
        tmp_path,
        "backend/app/alembic/versions/abc123.py",
        "op.create_table('workspace', sa.Column('id', sa.Uuid()))",
    )
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [model_rel, mig_rel], acc)
    assert acc["missing"] == []


def test_check_skips_when_only_model_changed(tmp_path):
    """No migration in diff → skip entirely (might be a non-schema BL)."""
    model_rel = _write(tmp_path, "backend/app/models.py", """
class WorkspaceMember(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
""")
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [model_rel], acc)
    assert acc["missing"] == []


def test_check_skips_when_only_migration_changed(tmp_path):
    """No model in diff → skip entirely (might be a data-fix migration)."""
    mig_rel = _write(
        tmp_path,
        "backend/app/alembic/versions/abc123.py",
        "op.create_table('workspace_member', sa.Column('id', sa.Uuid()))",
    )
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [mig_rel], acc)
    assert acc["missing"] == []


def test_check_reports_missing_migration_for_declared_model(tmp_path):
    """Engineer added a table=True class but no matching op.create_table."""
    model_rel = _write(tmp_path, "backend/app/models.py", """
class NewThing(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
""")
    mig_rel = _write(
        tmp_path,
        "backend/app/alembic/versions/abc123.py",
        "op.create_table('something_else', sa.Column('id', sa.Uuid()))",
    )
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(tmp_path, [model_rel, mig_rel], acc)
    assert len(acc["missing"]) == 1
    assert "newthing" in acc["missing"][0].lower()


# ─── A36b: base_ref scoping (incremental-BL false-positive fix) ──────────


def _git_init_with_baseline(tmp_path, model_body: str, mig_files: dict[str, str]):
    """Initialize a git repo, commit a baseline models.py + migrations
    representing 'prior BLs', and return the baseline ref name."""
    import subprocess as sp
    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sp.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    _write(tmp_path, "backend/app/models.py", model_body)
    for rel, body in mig_files.items():
        _write(tmp_path, rel, body)
    sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)
    # Branch off so that base_ref ('main') and HEAD diverge once the
    # BL commit lands — matches real agent-worktree layout.
    sp.run(["git", "checkout", "-q", "-b", "agent/bl"], cwd=tmp_path, check=True)
    return "main"


def test_a36b_incremental_bl_does_not_flag_prior_models(tmp_path):
    """A36b: an incremental BL adds ONE new table=True class + ONE new
    migration. Pre-existing models (added on prior BLs, present at HEAD
    but unchanged in this diff) MUST NOT be flagged as missing.

    Reproduces and pins the BL-0004 false-positive that killed
    run-20260531T211839Z-1f47e6: 5 prior tables (User, ClientUser,
    PortalInvitation, PortalAuditLog, Item) were reported missing
    when only PortalAccessGrant was new.
    """
    import subprocess as sp
    # Baseline: 2 prior tables and their migrations
    baseline_models = """
class User(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)

class ClientUser(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
"""
    baseline_migs = {
        "backend/app/alembic/versions/0001_user.py":
            "op.create_table('user', sa.Column('id', sa.Uuid()))",
        "backend/app/alembic/versions/0002_clientuser.py":
            "op.create_table('clientuser', sa.Column('id', sa.Uuid()))",
    }
    base_ref = _git_init_with_baseline(tmp_path, baseline_models, baseline_migs)

    # New BL: add ONE new table + ONE new migration only
    new_models = baseline_models + """
class PortalAccessGrant(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
"""
    _write(tmp_path, "backend/app/models.py", new_models)
    new_mig = _write(
        tmp_path,
        "backend/app/alembic/versions/0003_portalaccessgrant.py",
        "op.create_table('portalaccessgrant', sa.Column('id', sa.Uuid()))",
    )
    sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-q", "-m", "BL: PortalAccessGrant"], cwd=tmp_path, check=True)

    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(
        tmp_path,
        ["backend/app/models.py", new_mig],
        acc,
        base_ref=base_ref,
    )
    # Pre-A36b this would emit 2 false positives (User, ClientUser).
    # Post-A36b: zero — PortalAccessGrant is new AND matches.
    assert acc["missing"] == [], (
        f"A36b regression: false-positive(s) on pre-existing tables: {acc['missing']}"
    )


def test_a36b_incremental_bl_still_catches_real_mismatch(tmp_path):
    """A36b must NOT mask a real mismatch on a NEW class — the
    workspacemember case (A36 original) still fires when scoped."""
    import subprocess as sp
    baseline_models = """
class User(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
"""
    base_ref = _git_init_with_baseline(
        tmp_path,
        baseline_models,
        {"backend/app/alembic/versions/0001_user.py":
            "op.create_table('user', sa.Column('id', sa.Uuid()))"},
    )

    # New BL adds WorkspaceMember (default tablename: workspacemember)
    # but migration uses snake_case workspace_member — real A36 defect.
    new_models = baseline_models + """
class WorkspaceMember(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
"""
    _write(tmp_path, "backend/app/models.py", new_models)
    new_mig = _write(
        tmp_path,
        "backend/app/alembic/versions/0002_wsm.py",
        "op.create_table('workspace_member', sa.Column('id', sa.Uuid()))",
    )
    sp.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-q", "-m", "BL: WorkspaceMember mismatch"], cwd=tmp_path, check=True)

    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check_tablename_consistency(
        tmp_path,
        ["backend/app/models.py", new_mig],
        acc,
        base_ref=base_ref,
    )
    assert len(acc["missing"]) == 1
    msg = acc["missing"][0]
    assert "WorkspaceMember" in msg
    assert "workspace_member" in msg
    # User must NOT be flagged (pre-existing).
    assert not any("User" in m and "WorkspaceMember" not in m
                   for m in acc["missing"])
