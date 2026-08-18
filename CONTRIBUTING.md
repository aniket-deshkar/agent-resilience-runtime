# Contributing

Run `ruff check .`, `ruff format --check .`, `pytest`, and `python -m build`. Classification changes require tests proving which failures retry and which remain terminal.

Keep provider integrations optional and deterministic tests credential-free. Never commit credentials, captured prompts, virtual environments, caches, or build output.

