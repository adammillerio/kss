#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
# ]
# ///
# Python implementation of md5sum for filenames, originally from:
# https://gist.github.com/vnetman/c620fbb204d4c9062a30cb562bc44f87
# Example epub minimal-v3plus2.epub from:
# https://github.com/bmaupin/epub-samples
import hashlib
from io import BytesIO
from typing import BinaryIO

import click


def md5(file: BinaryIO) -> str:
    sum = hashlib.md5()
    while True:
        data = file.read(4096)
        if not data:
            break

        sum.update(data)

    return sum.hexdigest()


@click.command("md5name")
@click.argument("file", nargs=1, required=True, type=click.File(mode="rb"))
def md5name(file: BinaryIO) -> None:
    """calculate the md5 sum of a document's filename

    Coreutils equivalent:
    echo -n 'minimal-v3plus2.epub' | md5sum
    35322b7036d0c3298eedde8c30429693

    From the root of a koreader installation:
    ./luajit -e 'require("setupkoenv"); print(require("ffi/sha2").md5("minimal-v3plus2.epub"))'
    35322b7036d0c3298eedde8c30429693

    From the HTTP inspector with example/minimal-v3plus2.epub opened:
    curl localhost:8080/koreader/ui/kosync/getFileNameDigest/
    ["35322b7036d0c3298eedde8c30429693"]

    Filename via stdin:
    echo -n 'minimal-v3plus2.epub' | ./md5name.py -
    35322b7036d0c3298eedde8c30429693

    Filename via path:
    ./md5name.py ./minimal-v3plus2.epub
    35322b7036d0c3298eedde8c30429693
    """

    if not file.seekable():
        # If not seekable (ie stdin), just load it in entirely
        file = BytesIO(file.read())

    click.secho(md5(file))


if __name__ == "__main__":
    md5name()
