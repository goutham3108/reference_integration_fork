"""Focused tests for handbook generation and source/site validation."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import handbook
import site_hooks


class HandbookTest(unittest.TestCase):
    def test_site_parser_collects_assets_and_ids(self) -> None:
        page = handbook.SitePage()
        page.feed('<h1 id="topic">Topic</h1><a href="other.html#part">Next</a><script src="asset.js"></script>')
        self.assertEqual(page.ids, {"topic"})
        self.assertEqual(page.targets, ["other.html#part", "asset.js"])

    def test_site_check_accepts_links_and_rejects_missing_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory)
            site = docs / "_handbook_site"
            site.mkdir()
            index = site / "index.html"
            index.write_text('<a href="next.html#part">Next</a><script src="asset.js"></script>')
            (site / "next.html").write_text('<h1 id="part">Part</h1>')
            (site / "asset.js").write_text("")
            with patch.object(handbook, "DOCS", docs), contextlib.redirect_stdout(io.StringIO()):
                handbook.validate_site()
                index.write_text('<a href="next.html#missing">Bad anchor</a>')
                with self.assertRaisesRegex(SystemExit, "missing anchor"):
                    handbook.validate_site()

    def test_consolidation_rewrites_chapter_and_source_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / "docs"
            pages = docs / "handbook"
            pages.mkdir(parents=True)
            (pages / "first.md").write_text("# First\n\n[Next](second.md) [Source](../../MODULE.bazel)\n")
            (pages / "second.md").write_text("# Second\n\nSecond summary.\n")
            with patch.object(handbook, "DOCS", docs), patch.object(handbook, "PAGES", pages), patch.object(
                handbook, "ORDER", ["first", "second"]
            ):
                handbook.consolidate()
            generated = (docs / "document.md").read_text()
            self.assertIn('[Next](#chapter-second)', generated)
            self.assertIn('[Source](../MODULE.bazel)', generated)
            self.assertIn('<a id="chapter-second"></a>', generated)

    def test_site_source_hook_pins_existing_repository_files(self) -> None:
        config = SimpleNamespace(
            config_file_path=str(handbook.DOCS / "mkdocs.yml"),
            docs_dir=str(handbook.PAGES),
            extra={"source_repository": "https://example.invalid/repository", "source_revision": "revision"},
        )
        page = SimpleNamespace(
            file=SimpleNamespace(abs_src_path=str(handbook.PAGES / "index.md")),
            url="index.html",
        )
        result = site_hooks.on_page_markdown(
            "[Module](../../MODULE.bazel)", page=page, config=config, files=None
        )
        self.assertEqual(result, "[Module](https://example.invalid/repository/blob/revision/MODULE.bazel)")
        with self.assertRaisesRegex(ValueError, "Missing local citation"):
            site_hooks.on_page_markdown(
                "[Missing](../../handbook-test-does-not-exist)", page=page, config=config, files=None
            )


if __name__ == "__main__":
    unittest.main()
