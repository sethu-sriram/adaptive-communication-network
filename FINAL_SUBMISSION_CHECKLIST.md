# Project 30 — final submission checklist

## Packaging
- This archive intentionally excludes the local `venv/`, Python caches, and compiled `.pyc` files. Recreate the environment using the README and `requirements.txt`.
- Existing `results/` data, logs, tables, and charts are preserved; no reported values were recalculated or changed during packaging.
- Before uploading to GitHub, inspect the repository visibility and make sure no credentials, personal tokens, or unrelated files are included.

## Required local checks
1. Activate your environment and run `python3 tests/test_loopback.py`.
2. Run `python3 tests/test_controller_logic.py` in the environment where OS-Ken is installed.
3. Perform the link-down and silent black-hole demos described in README.md.
4. Run the three-client demo (`experiment.py --clients 3`) and preserve its logs.
5. If anything fails, save the complete error output; do not label the test as passed.

## Report finalization
- Replace `[fill in GitHub URL]` on the report cover with the actual repository URL.
- Confirm the report's source-file list matches the archive. The concurrent-client test is provided by `experiment.py --clients 3`; there is no separate `demo_t7.py` in this archive.
- Keep the report's existing results as the authoritative final values, per the project owner's instruction.
- Export the final DOCX to PDF and visually check page breaks, table widths, captions, and page numbers.
