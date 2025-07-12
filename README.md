# kss

koreader simple sync - a single-file python server for the progress sync plugin

This is a Python based implementation of the KOReader Sync Server: https://github.com/koreader/koreader-sync-server

It is designed to be simple and can be run on any computer on the same network as your eReader in order to sync document progress between one or more other devices running KOReader.

For info on the plugin, see the official wiki: https://github.com/koreader/koreader/wiki/Progress-sync

## Install

The quickest way to start using kss is with the [uv](https://github.com/astral-sh/uv) package manager, which can install and manage Python and it's dependencies for kss:

```bash
# See uv docs for other installation options
# https://docs.astral.sh/uv/getting-started/installation/#standalone-installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

The `uv` tool can be used to quickly run Python programs in anonymous
virtual environments using [script metadata](https://docs.astral.sh/uv/guides/scripts/):

```bash
# Or download the zip file from GitHub and extract it
git clone https://github.com/adammillerio/kss.git
cd kss
# Can also be run directly as ./kss.py
uv run kss.py serve --port 8080 --host 0.0.0.0
```

This will start the sync server on HTTP port 8080 listening on all interfaces. You may need to adjust firewall configuration on the device for it to be reachable by your eReader.

The default `serve` command runs KSS using the [Waitress](https://github.com/Pylons/waitress) WSGI server via the [Flask](https://github.com/pallets/flask) web framework. It can also be started directly via the `waitress-serve` command:

```bash
uvx --with 'flask' --from 'waitress' waitress-serve --port 8080 --host 0.0.0.0 kss:app
```


Or the Flask development server, [Werkzeug](https://github.com/pallets/werkzeug):

```bash
uvx flask --app 'kss:app' run --port 8080 --host 0.0.0.0
```

Other Flask CLI commands are embedded under `./kss.py flask`.

## Usage

### Configuration

After starting the server, open a document in KOReader and go to the Tools menu (Wrench icon) and open the options for Progress Sync.

By default this plugin will sync to the managed server at https://sync.koreader.rocks . To change this, select "Custom sync server" and set it to the base URL of the kss instance.

For example, on a kss server with the local IP 192.168.1.4 listening on port 8080, the custom sync server should be set to `http://192.168.1.4:8080`

While kss does use a production WSGI server, I wouldn't recommend running it on the public internet. Running the server on my local network and syncing my devices while they are connected to it has worked fine for me. If you do choose to expose it to the internet, be sure to use HTTPS and disable registration.

### Login and Registration

To create an account, you can select Login and register a new user, then login with the credentials. After this, the Progress Sync plugin should be connected.

User authentication information is stored as `auth.json` in their respective directory.

**Note:** KOReader uses a bare MD5 hash to store both the document ID and user password when sending requests to the server. MD5 has been considered insecure for a while now and can be cracked pretty quickly on modern systems. You may want to consider running kss with an SSL certificate, especially if you are exposing it to the internet.

After registering, the kss server can be restarted with the `KSS_DISABLE_REGISTRATION` environment variable set to `true` in order to avoid further user registrations:

```bash
KSS_DISABLE_REGISTRATION=true ./kss.py serve --port 8080 --host 0.0.0.0
```

When this is set, all requests to `/users/create` will return a 403 with an error message indicating that registration is disabled.

### Pushing and Pulling State

After logging in, document progress state can be pushed or pulled manually via the progress sync menu. It can also be configured to automatically do this, but it also requires automatic connection to WiFi.

### Document Matching

The only setting that is really relevant to kss itself is the "Document matching method". This is the method used to derive the document ID that identifies what is being synced. This can be either:

Binary - An md5 digest of the file using koreader.frontend.util.partialMD5:

```
example/partial_md5.py example/minimal-v3plus2.epub
4022c5c21066253eb6b33997b959a18c
```

Filename - An md5 sum of the document's filename

```
echo -n 'minimal-v3plus2.epub' | example/md5name.py -
35322b7036d0c3298eedde8c30429693
```

There are pros and cons to both. Binary is more unique, but the hash will change if the file itself is modified at all. Filename is easier to manage, but if two files have the same name, their state will collide. Personally, I use filenames for identification.

### Storage

Document state is stored as a JSON file in the kss state dir. The filename is the document ID (MD5 hash) provided by KOReader and is stored in a subdirectory for the user making the request.

For example, with document identification set to Filename, the `minimal-v3plus2.epub` file's progress would be stored as `aemiller/35322b7036d0c3298eedde8c30429693.json`.

kss uses [platformdirs](https://github.com/tox-dev/platformdirs) to derive a good place to store sync state:

* macOS: `/Users/aemiller/Library/Application Support/kss`
* Linux: `/home/aemiller/.local/share/kss` (or `XDG_DATA_HOME` if set)
* windows: `C:\Documents and Settings\aemiller\Application Data\Local Settings\adammillerio\kss`

If `platformdirs` is not installed or cannot determine a directory, then the default `~/.local/share` directory will be used instead.

To override this, set the `KSS_DIR` environment variable to the desired path when starting kss.

## Development

### Type Checking

Ensure no type errors are present with [pyre](https://github.com/facebook/pyre-check):

```bash
uvx --with-requirements requirements.txt --from pyre-check pyre check
ƛ No type errors found
```

**Note**: Pyre daemonizes itself on first run for faster subsequent executions. Be sure to shut it down with `uv run pyre stop` when finished.

### Formatting

Format code with the [ruff](https://github.com/astral-sh/ruff) formatter:

```bash
uv run ruff format
3 files left unchanged
```

## See Also

### Other Servers

These servers were extremely helpful in implementing kss:

* [koreader/koreader-sync-server](https://github.com/koreader/koreader-sync-server) - Official server, requires a Redis server for state storage
* [myelsukov/koreader-sync](https://github.com/myelsukov/koreader-sync) - Another Python/Flask based sync server
* [kosync-dotnet](https://github.com/jberlyn/kosync-dotnet) - A C#/.NET based sync server with some additional user management functions

### Resources

* [bmaupin/epub-samples](https://github.com/bmaupin/epub-samples) - `example/minimal-v3plus2.epub` is from this repo
* [kosync.koplugin](https://github.com/koreader/koreader/tree/master/plugins/kosync.koplugin) - Source for the sync client, including an API spec
* [KOReader Docs](https://koreader.rocks/doc/index.html) - Developer documentation for KOReader itself
