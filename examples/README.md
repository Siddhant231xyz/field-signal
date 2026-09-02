# Standalone ingestion experiment

This example asks `gpt-5.5` at `high` reasoning effort to turn every file under
`packet/` into the same three-file evidence-ledger format used by `data/`.
It is not imported by or integrated with `field_signal`.

The OpenAI client, agent instructions, tool loop, package installation, and shell
all execute as root inside one disposable Docker container. GPT-5.5 itself runs
on OpenAI's servers. Root is limited to the container: the runner does not use
`--privileged`, mount the Docker socket, mount the host home directory, or expose
the existing `data/` directory.

The host does not classify or route files by extension. The agent starts from the
input directory, inspects each file's magic bytes and container structure inside
Docker, then installs suitable parsers. The same `shell` tool can return image
artifacts for model vision after their binary MIME type has been confirmed.

## Setup

Start Docker Desktop or another Docker daemon. Set `OPENAI_API_KEY` in the
repository-root `.env`; the file is git-ignored. No host Python packages are
required because the OpenAI SDK is installed into the image.

## Run

```bash
python3 -m examples.run_containerized
```

Defaults:

- host input: `packet/`, mounted read-only at `/packet`
- generated output: `examples/data/`
- model: `gpt-5.5`
- reasoning effort: `high`
- container network: `bridge`, allowing root to install packages
- maximum agent/tool rounds: `200`, plus up to `8` validation-repair rounds

The run stages output outside `examples/data`, validates the JSON independently,
then promotes exactly `people.json`, `sources.json`, and `claims.json`. Only after
promotion does the host compare the generated ledger with `data/`. The reference
directory is never mounted into the container or shown to the model.

Use `--no-compare` to skip the reference evaluation. Use `--network none` when
the image already contains every required parser and package installation is not
needed. Check Docker without making an API call with:

```bash
python3 -m examples.run_containerized --check-only
```

## Security boundary

The packet is mounted read-only, but the container has outbound network access by
default so it can install arbitrary packages. That is appropriate for this local
experiment, not for untrusted multi-tenant uploads. A production runner should
install dependencies before mounting sensitive input, then process the packet
with networking disabled.

The launcher passes `.env` into the container so the OpenAI client can use the
API key. Model-requested shell subprocesses have `OPENAI_API_KEY` removed from
their environment, but because both processes share one root container this is
not a security boundary against a hostile command. A production design should
put the agent client and shell executor in separate containers, or give the
agent a short-lived internal API proxy, so packet-controlled shell activity can
never inspect the long-lived API credential.
