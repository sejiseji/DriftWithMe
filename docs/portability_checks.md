# Portability and commit identity checks

Run `.venv/bin/python scripts/check_all.py` before preparing a commit. The portability step checks tracked and nonignored untracked UTF-8 text, plus text inside ZIP payloads embedded in the generated HTML, for concrete personal home paths. Relative archive entry names are also required. Placeholder examples such as `/Users/<username>/project` remain valid.

The approved public Git identity is `sejiseji` with `47272134+sejiseji@users.noreply.github.com`. The check reads effective author and committer identities, including environment overrides, and checks author, committer, and identity trailers on commits ahead of the configured upstream. A missing upstream is reported as an incomplete check. It does not change Git configuration or install hooks.

This is a local review aid, not an enforcement boundary: run it in each environment before committing and again before pushing. An explicit author option or a later environment change can still override a previously checked identity. Already published history is deliberately outside the default check; rewriting it requires a separate decision.

The path check targets personal home directories, not all absolute operating-system paths. It does not inspect binary image metadata, every compressed format, hidden remote references, forks, caches, or secrets in general. Failures report locations and categories without printing the matched personal path or mismatched identity.

Private production helpers outside the repository accept `--repo <checkout>` (or `DRIFT_WITH_ME_REPO`) and optional `--work-root <workspace>`. Their normal workspace is resolved from the helper module's location, independent of the shell's current directory. These flags only select locations; existing helpers that modify, commit, or push files retain their original behavior and must not be run as verification commands.
