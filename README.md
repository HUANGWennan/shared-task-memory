# Shared Task Memory

A Python gateway for the open-source MCP Memory server. MCP clients on the same machine can use one local knowledge graph for preferences, decisions, and task checkpoints. Searches return up to three previews by default. Opening a task returns its latest checkpoint, with full history available on request.

## Setup

Install Python 3.9+ and Node.js 24+ and make both available on your PATH. From the repository directory, run:

```sh
npm ci
mkdir -p data
python3 shared_memory.py status
```

Configure each MCP client to launch `python3 /absolute/path/to/memory_gateway.py` as a stdio server. Set `MEMORY_FILE_PATH` in each client's server environment to the same absolute path, for example `/absolute/path/to/shared-task-memory/data/memory.jsonl`. The command-line helper defaults to that repository's `data/memory.jsonl` unless you set the environment variable.

```sh
python3 shared_memory.py remember --name fact:example --kind fact --text "Synthetic example"
python3 shared_memory.py search example
python3 shared_memory.py open fact:example
```

Use `open --history` to see earlier task checkpoints. Store real memory files outside version control and share access only with clients you trust.
