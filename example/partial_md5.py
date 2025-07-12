#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
# ]
# ///
# Python implementation of koreader.frontend.util.partialMD5, originally from:
# https://git.sr.ht/~harmtemolder/koreader-calibre-plugin/tree/9c0577b85ec360589631d0cdc3b463e11db5f11f/item/fast_digest.py
# Example epub minimal-v3plus2.epub from:
# https://github.com/bmaupin/epub-samples
import hashlib
from io import BytesIO
from typing import BinaryIO

import click


def partial_md5(file: BinaryIO, step: int = 1024, size: int = 1024) -> str:
    m = hashlib.md5()

    sample = file.read(size)
    m.update(sample)

    for i in range(0, 10):
        file.seek(step << (2 * i), 0)

        sample = file.read(size)
        if sample:
            m.update(sample)
        else:
            break

    return m.hexdigest()


@click.command("md5digest")
@click.argument("file", nargs=1, required=True, type=click.File(mode="rb"))
def md5digest(file: BinaryIO) -> None:
    """calculate the partial md5 digest of a document

    From the root of a koreader installation with example/minimal-v3plus2.epub:
    ./luajit -e 'require("setupkoenv"); print(require("util").partialMD5("./minimal-v3plus2.epub"))'
    4022c5c21066253eb6b33997b959a18c

    From the HTTP inspector with example/minimal-v3plus2.epub opened:
    curl localhost:8080/koreader/ui/kosync/getFileDigest/
    ["4022c5c21066253eb6b33997b959a18c"]

    File via stdin:
    ./partial_md5.py - < minimal-v3plus2.epub
    4022c5c21066253eb6b33997b959a18c

    File via argument:
    ./partial_md5.py minimal-v3plus2.epub
    4022c5c21066253eb6b33997b959a18c
    """

    if not file.seekable():
        # If not seekable (ie stdin), just load it in entirely
        file = BytesIO(file.read())

    click.secho(partial_md5(file))


if __name__ == "__main__":
    md5digest()
