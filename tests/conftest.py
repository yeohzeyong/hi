import pytest

from auction_tracker import db


@pytest.fixture(autouse=True)
def _isolated_comps_dir(tmp_path, monkeypatch):
    """Tests must never write market comps into the real data/ folder."""
    monkeypatch.setattr(db, "COMPS_DIR", tmp_path / "comps")


@pytest.fixture(autouse=True)
def _isolated_forum_dir(tmp_path, monkeypatch):
    from auction_tracker import forum
    monkeypatch.setattr(forum, "FORUM_DIR", tmp_path / "forum")
