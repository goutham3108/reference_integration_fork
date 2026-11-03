"""Resolve locally verified source citations to pinned web links in the site."""

import re
from pathlib import Path
from urllib.parse import quote, urlsplit

from mkdocs.structure.files import File
from mkdocs.utils import get_relative_url


def on_files(files, *, config):
    docs = Path(config.config_file_path).resolve().parent
    package = docs / "node_modules" / "mermaid"
    for source, target in [
        (package / "dist" / "mermaid.min.js", "assets/mermaid.min.js"),
        (package / "LICENSE", "assets/mermaid-LICENSE.txt"),
    ]:
        if not source.is_file():
            raise FileNotFoundError(
                f"Missing local Mermaid asset {source}. Run: npm ci --prefix docs --ignore-scripts"
            )
        files.append(File.generated(config, target, content=source.read_bytes()))
    return files


def on_page_markdown(markdown, *, page, config, files):
    root = Path(config.config_file_path).resolve().parent.parent
    source = Path(page.file.abs_src_path)
    repository = config.extra["source_repository"]
    revision = config.extra["source_revision"]

    def replace(match):
        label, target = match.groups()
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path or parsed.path.startswith("/"):
            return match.group(0)
        resolved = (source.parent / parsed.path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Source citation escapes repository: {source}: {target}")
        if not resolved.exists():
            raise ValueError(f"Missing local citation: {source}: {target}")
        if resolved.is_relative_to(Path(config.docs_dir).resolve()):
            return match.group(0)
        if resolved.is_file() and resolved.is_relative_to(root / "docs"):
            relative = resolved.relative_to(root / "docs").as_posix()
            download = f"sources/{relative}.txt"
            if files.get_file_from_path(download) is None:
                files.append(File.generated(config, download, content=resolved.read_bytes()))
            return f"[{label}]({get_relative_url(download, page.url)})"
        path = resolved.relative_to(root).as_posix()
        kind = "tree" if resolved.is_dir() else "blob"
        url = f"{repository}/{kind}/{revision}/{quote(path)}"
        if parsed.fragment:
            url += f"#{parsed.fragment}"
        return f"[{label}]({url})"

    return re.sub(r"\[([^\]\n]+)\]\(([^()\s]+)\)", replace, markdown)
