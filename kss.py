#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
#     "flask",
#     "platformdirs",
#     "waitress",
# ]
# ///
from functools import cache
from json import dumps, load, loads
from logging import DEBUG, INFO, WARNING, Logger, basicConfig, getLogger
from os import chdir, getenv
from pathlib import Path
from sys import argv
from time import strftime, time
from typing import Any, Optional, Tuple

from flask import Flask, Response, jsonify, request
from flask.cli import FlaskGroup, is_running_from_reloader

logger: Logger = getLogger("kss")


# To disable registration when running:
# KSS_DISABLE_REGISTRATION=true ./kss.py serve
REGISTRATION_DISABLED: bool = (
    getenv("KSS_DISABLE_REGISTRATION", "false").lower() == "true"
)


@cache
def kss_root() -> Path:
    """Determine the root for storing progress and auth state.

    If the KSS_DIR environment variable is set, it will be used. Otherwise, a
    platform appropriate path for storing state is determined with platformdirs.

    linux: /home/aemiller/.local/share/kss
    macOS: /Users/aemiller/Library/Application Support/kss
    default: ~/.local/share/kss

    Returns:
        root: Path. Location to store all state for the kss server.
    """

    if path := getenv("KSS_DIR"):
        return Path(path)

    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir("kss", "adammillerio"))
    except ImportError:
        logger.debug("cannot import platformdirs package, defaulting to ~/.config/kss")

        if path := getenv("XDG_DATA_HOME"):
            return Path(path) / "kss"
        else:
            return Path.home() / ".local/share/kss"


def kss_dir(user: str) -> Path:
    """Get the path to a user's state files.

    Args:
        user: str. Request user.

    Returns:
        path: Path. Path to the directory holding this user's progress and auth.
    """

    return kss_root() / user


def kss_path(user: str, file_md5: str) -> Path:
    """Get the path to the user's state file for a given document.

    Progress is stored as a JSON file named with the provided document MD5 in
    a subfolder for the user.

    When syncing, the document MD5 is derived from either:

    Binary - An md5 digest of the file using koreader.frontend.util.partialMD5:
      example/partial_md5.py example/minimal-v3plus2.epub
      4022c5c21066253eb6b33997b959a18c

    Filename - An md5 sum of the document's filename
      echo -n 'minimal-v3plus2.epub' | example/md5name.py -
      35322b7036d0c3298eedde8c30429693

    Args:
        user: str. Logged in user pushing/pulling this state.
        file_md5: str. MD5 sum of either the document being synced, or it's filename.

    Returns:
        path: Path. Path to the file holding progress state as JSON.
    """

    return kss_dir(user) / f"{file_md5}.json"


def kss_auth_file(user: str) -> Path:
    """Get the path to the user's auth file.

    Auth info is stored as a JSON file in the user's subdirectory as auth.json.

    Args:
        user: str. User being authenticated or registered.

    Returns:
        auth: Path. Path to the file holding authorization info for this user.
    """

    return kss_dir(user) / "auth.json"


def kss_auth_headers() -> Tuple[Optional[str], Optional[str]]:
    """Retrieve the auth headers provided for the request.

    Returns:
        user: Optional[str]. Username retrieved from x-auth-user request header.
        password_md5: Optional[str]. Password md5 retrieved from x-auth-key
            request header.
    """

    if user := request.headers.get("x-auth-user", None):
        logger.debug(f"Got user from request: {user}")

    if password_md5 := request.headers.get("x-auth-key", None):
        logger.debug("Got password md5 from request")

    return (user, password_md5)


def kss_auth() -> Optional[str]:
    """Authorize a request to the server.

    The x-auth-user and x-auth-key request headers are compared with the
    auth.json file for the user if any.

    Returns:
        user: Optiona[str]. Request user retrieved from x-auth-user, or None if
            the user auth is invalid or non-existent.
    """

    user, password_md5 = kss_auth_headers()
    if not user:
        logger.debug("No x-auth-user header in request, cannot authenticate")
        return

    if not password_md5:
        logger.debug("No x-auth-key header in request, cannot authenticate")
        return

    auth_file = kss_auth_file(user)
    if not auth_file.exists():
        logger.debug(f"No user registered with name {user}")
        return

    with auth_file.open("r") as file:
        auth = load(file)

    if auth["x-auth-user"] == user and auth["x-auth-key"] == password_md5:
        return user
    else:
        logger.debug(f"provided authentication for {user} is invalid")


def kss_error(http_code: int, /, message: str, code: int) -> Tuple[Response, int]:
    """Return an error for a request.

    Errors are returned as JSON based on these definitions:
    https://github.com/koreader/koreader-sync-server/blob/master/config/errors.lua

    Args:
        http_code: int. HTTP response code to send.
        message: str. Error message.
        code: int. Error code for KOReader.

    Returns:
        error_response: Response. JSON as a Flask response object.
        http_code: int.
    """

    # {"message": "Unauthorized", "code": "2001"}
    error = {"message": message, "code": code}
    logger.debug(f"sending error message: {error}")
    return jsonify(error), http_code


def kss_response(http_code: int, /, **kwargs: Any) -> Tuple[Response, int]:
    """Return a response for a request.

    Response data is an arbitrary set of key/value pairs returned as JSON, which
    are used by the kosync plugin, based on definitions here:
    https://github.com/koreader/koreader-sync-server/blob/master/app/controllers/1/syncs_controller.lua

    Args:
        http_code: int. HTTP response code to send.

    Returns:
        response: Response. JSON as a Flask response object.
        http_code: int.
    """

    logger.debug(f"sending response: {kwargs}")
    return jsonify(**kwargs), http_code


app = Flask(__name__)


@app.route("/users/create", methods=["POST"])
def register() -> Tuple[Response, int]:
    if REGISTRATION_DISABLED:
        logger.debug("Registration disabled, ignoring request")
        return kss_error(403, message="User registration disabled", code=3001)

    # {"username":"aemiller", "password": "3858f62230ac3c915f300c664312c63f"}
    if not request.is_json:
        return kss_error(403, message="Invalid request", code=2003)

    # echo -n 'foobar' | example/md5name.py -
    # 3858f62230ac3c915f300c664312c63
    # {"username":"aemiller", "password": "3858f62230ac3c915f300c664312c63f"}
    js = request.get_json()

    user = js.get("username", "")
    if user and isinstance(user, str):
        logger.debug(f"Received registration request for user {user}")
    else:
        return kss_error(403, message="Invalid request", code=2003)

    password_md5 = js.get("password", "")
    if not password_md5 or not isinstance(password_md5, str):
        logger.debug(f"No password md5 provided for user {user}, cannot register")
        return kss_error(403, message="Invalid request", code=2003)

    auth_file = kss_auth_file(user)
    if auth_file.exists():
        logger.debug(f"Auth file for {user} already present at {auth_file}")
        return kss_error(402, message="Username is already registered", code=2002)

    if not auth_file.parent.exists():
        logger.debug(f"Creating dir for {user} at {auth_file.parent}")
        auth_file.parent.mkdir(parents=True)

    logger.debug(f"Writing auth file for {user} at {auth_file}")
    auth_file.write_text(dumps({"x-auth-user": user, "x-auth-key": password_md5}))

    # {"username": "aemiller"}
    return kss_response(201, username=user)


@app.route("/users/auth")
def login() -> Tuple[Response, int]:
    if kss_auth():
        # {"authorized": "OK"}
        return kss_response(200, authorized="OK")
    else:
        return kss_error(401, message="Unauthorized", code=2001)


@app.route("/syncs/progress", methods=["PUT"])
def push() -> Tuple[Response, int]:
    user = kss_auth()
    if not user:
        return kss_error(401, message="Unauthorized", code=2001)

    if not request.is_json:
        return kss_error(403, message="Invalid request", code=2003)

    # {"device_id":"6B344CE498AE402096F5AEB4154C1DBB","percentage":0.4045,
    #  "document":"22b3308b1618273ad77a98fe29ca4600","device":"KindlePaperWhite3",
    #  "progress":"/body/DocFragment[26]/body/section/p[5]/text().0"}
    js = request.get_json()

    if document := js.get("document", None):
        if percentage := js.get("percentage", None):
            try:
                js["percentage"] = float(percentage)
            except Exception:
                js["percentage"] = None

        js.setdefault("progress", None)
        js.setdefault("device", None)
        js.setdefault("device_id", None)

        # Add unix timestamp to current state ie 1751935136
        js["timestamp"] = int(time())

        logger.debug(f"Got progress from request (with timestamp): {js}")

        # ~/.local/share/kss/aemiller/22b3308b1618273ad77a98fe29ca4600.json
        path = kss_path(user, document)
        if not path.parent.exists():
            # mkdir -pv ~/.local/share/aemiller
            logger.debug(f"Creating dir for {user} at {path.parent}")
            path.parent.mkdir(parents=True)

        logger.debug(f"Writing document progress for {user} at: {path}")
        path.write_text(dumps(js))

        # {"document": "22b3308b1618273ad77a98fe29ca4600", "timestamp": 1751935136}
        return kss_response(200, document=document, timestamp=js["timestamp"])
    else:
        return kss_error(403, message="Field 'document' not provided.", code=2004)


@app.route("/syncs/progress/<document>")
def pull(document: str) -> Tuple[Response, int]:
    user = kss_auth()
    if not user:
        return kss_error(401, message="Unauthorized", code=2001)

    path = kss_path(user, document)
    if not path.exists():
        # {"document": "22b3308b1618273ad77a98fe29ca4600"}
        logger.debug(f"No recorded progress for document {document}")
        return kss_response(200, document=document)

    js = loads(path.read_text())
    logger.debug(f"loaded existing progress state: {js}")

    res = {}
    if percentage := js.get("percentage", None):
        try:
            res["percentage"] = float(percentage)
        except Exception:
            logger.debug(f"unable to parse percentage {percentage}")

    # This is implemented the same as the reference server, which also loosely
    # assembles the state from available values in redis
    if progress := js.get("progress", None):
        res["progress"] = progress

    if device := js.get("device", None):
        res["device"] = device

    if device_id := js.get("device_id", None):
        res["device_id"] = device_id

    if timestamp := js.get("timestamp", None):
        try:
            res["timestamp"] = int(timestamp)
        except Exception:
            logger.debug(f"unable to parse timestamp {timestamp}")

    # {"device_id":"6B344CE498AE402096F5AEB4154C1DBB","percentage":0.4045,
    #  "document":"22b3308b1618273ad77a98fe29ca4600","device":"KindlePaperWhite3",
    #  "progress":"/body/DocFragment[26]/body/section/p[5]/text().0",
    #  "timestamp": "1751935136"}
    return kss_response(200, **res)


if __name__ == "__main__":
    import click

    @app.after_request
    def after_request(response: Response) -> Response:
        # Closely mimics werkzeug, which uses http.server.BaseHTTPRequestHandler
        # INFO:kss:127.0.0.1 - - [11/Jul/2025 12:33:59] "GET /users/auth? HTTP" 200 OK -
        # INFO:werkzeug:127.0.0.1 - - [11/Jul/2025 12:33:59] "GET /users/auth HTTP/1.0" 200 -
        logger.info(
            '%s - - [%s] "%s %s %s" %s -',
            request.remote_addr,
            strftime("%d/%b/%Y %H:%M:%S"),
            request.method,
            f"{request.path}"
            + (f"?{request.query_string.decode()}" if request.query_string else ""),
            request.scheme.upper(),
            response.status,
        )

        return response

    def create_app() -> Flask:
        logger.info("starting koreader simple sync using werkzeug development server")
        logger.info(f"storing user state at {kss_root()}")

        parent = Path(argv[0]).parent

        # cd /home/aemiller/kss && uvx flask --app 'kss:app' run --port 8437
        command = argv[2:]
        maybe_args = f" {' '.join(command)}" if command else ""
        maybe_uv = "uvx " if getenv("UV", None) else ""
        logger.info(
            f"cd {parent.absolute()} && {maybe_uv}flask --app 'kss:app'{maybe_args}",
        )

        chdir(parent)
        return app

    @click.group("kss")
    def kss() -> None:
        pass

    # pyre-ignore[56]
    @kss.group("flask", cls=FlaskGroup, create_app=create_app)
    def kss_flask() -> None:
        if is_running_from_reloader() and app.debug:
            basicConfig(level=DEBUG)
            getLogger("werkzeug").setLevel(DEBUG)
        else:
            basicConfig(level=INFO)
            getLogger("werkzeug").setLevel(WARNING)

    @kss.command(
        "serve",
        help="Run kss using the waitress wsgi server",
        context_settings={"ignore_unknown_options": True},
        add_help_option=False,
    )
    @click.option("--debug", is_flag=True, help="enable debug mode")
    @click.argument("command", nargs=-1, type=click.UNPROCESSED)
    def kss_serve(debug: bool, command: Tuple[str, ...]) -> None:
        level = DEBUG if debug else INFO
        basicConfig(level=level)
        getLogger("waitress").setLevel(level)

        logger.info("starting koreader simple sync using waitress wsgi server")
        logger.info(f"storing user state at {kss_root()}")

        try:
            from waitress.runner import run
        except ImportError:
            click.secho("could not import the waitress package", err=True, fg="red")
            raise click.exceptions.Exit(1)

        parent = Path(argv[0]).parent

        # cd /Users/aemiller/kss && uvx --with 'flask' --from 'waitress' waitress-serve --port 8437 kss:app
        maybe_args = f" {' '.join(command)} " if command else " "
        maybe_uv = "uvx --with 'flask' --from 'waitress' " if getenv("UV", None) else ""
        logger.info(
            f"cd {parent.absolute()} && {maybe_uv}waitress-serve{maybe_args}kss:app",
        )

        chdir(parent)
        run(argv=(argv[0],) + command + ("kss:app",))

    kss()
