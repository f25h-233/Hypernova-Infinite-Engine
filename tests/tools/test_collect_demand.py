from collect_demand import collect, read_sessions


LOG = """\
1 [main] INFO  com.fs.starfarer.StarfarerLauncher - 正在运行 Starsector
10 [main] INFO  com.fs.graphics.TextureLoader - Loading image [graphics/a.png]
20 [FR-Texture-Loader-1] INFO  com.fs.graphics.TextureLoader - Loading image [graphics/b.png]
30 [main] INFO  com.fs.starfarer.loading.CodexTextEntryLoader - Parsing entry
40 [main] INFO  com.fs.graphics.TextureLoader - Loading image [graphics/c.png]
1 [main] INFO  com.fs.starfarer.StarfarerLauncher - 正在运行 Starsector
5 [main] INFO  com.fs.graphics.TextureLoader - Loading image [graphics/d.png]
"""


def test_read_sessions(tmp_path):
    p = tmp_path / "starsector.log"
    p.write_text(LOG, encoding="utf-8")
    assert read_sessions(p) == [(1, 5), (6, 7)]


def test_collect_stops_at_anchor(tmp_path):
    p = tmp_path / "starsector.log"
    p.write_text(LOG, encoding="utf-8")
    records, summary = collect(p, session=1)
    assert [r["path"] for r in records] == ["graphics/a.png", "graphics/b.png"]
    assert records[1]["thread"] == "FR-Texture-Loader-1"
    assert records[0]["ms"] == 10
    assert summary["anchor_ms"] == 30
    assert summary["unique_paths"] == 2


def test_collect_all_sessions_without_anchor(tmp_path):
    p = tmp_path / "starsector.log"
    p.write_text(LOG, encoding="utf-8")
    records, summary = collect(p, until_anchor=False)
    assert len(records) == 4
    assert summary["sessions"] == 2
