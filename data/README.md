# Competition data (not committed)

Everything in this folder except this README is gitignored. Rule 2.4.b forbids redistributing competition data to anyone outside the competition, so it never goes into git.

## Needed now

- `HARNESS_README.md`
- `tasks.jsonl`
- `sample_submission/`
- `docker/`
- `sandbox/setup.py`
- the starter notebook, "Getting Started - Gemma 4 Developer Agent"

The full dataset is about 22 GB (snapshots, graphs, embeddings, wheels). It isn't needed locally yet.

## Download with the Kaggle CLI

`uvx` runs the Kaggle CLI without adding it to the project, and it uses your existing credentials in `~/.kaggle`.

```bash
cd ~/workspaces/kaggle/gemma
COMP=gemma-4-developer-agent

uvx kaggle competitions files $COMP --page-size 200        # lists the exact file paths
uvx kaggle competitions download $COMP -f HARNESS_README.md -p data
uvx kaggle competitions download $COMP -f tasks.jsonl -p data

# For each file under sample_submission/, docker/ and sandbox/ in the listing:
uvx kaggle competitions download $COMP -f sample_submission/<file> -p data/sample_submission

# The starter notebook:
uvx kaggle kernels pull ryanholbrook/getting-started-gemma-4-developer-agent -p data
```

- Single files sometimes arrive zipped (for example `tasks.jsonl.zip`); unzip them in place.
- If the CLI gives trouble, the competition's Data tab has a download button for each file.
- These commands follow a participant's notes for Kaggle CLI 2.x. They haven't been tested from here.
