#!/usr/bin/env python3
"""Create a self-contained, unfinished priorities-review skeleton; never overwrite."""
import argparse
import html
import os
from pathlib import Path
import re
import stat
import sys

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "review-template.html"


def render(title, scope):
    values = {"TITLE": html.escape(title, quote=True), "SCOPE": html.escape(scope, quote=True)}
    return re.sub(r"\{\{(TITLE|SCOPE)\}\}", lambda match: values[match[1]], TEMPLATE.read_text(encoding="utf-8"))


def create(output, title, scope):
    output = Path(output).absolute()
    parent = output.parent
    if parent.is_symlink():
        raise ValueError("output parent must not be a symlink")
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("output parent must be yours and not group/world writable")
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render(title, scope))
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--output", required=True, help="new file in an existing task-owned private directory")
    args = parser.parse_args()
    create(args.output, args.title, args.scope)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
