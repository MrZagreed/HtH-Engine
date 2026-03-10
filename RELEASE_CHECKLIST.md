# Safe Release Checklist (HtH Engine)

1. Ensure branch is `master` and working tree is clean:
   - `git branch --show-current`
   - `git status --short`

2. Run release guard:
   - `py -3.12 scripts/release_guard.py --create-archive`

3. Validate generated archive:
   - `dist/hth-engine-v<version>.zip`

4. Create annotated tag:
   - `git tag -a v<version> -m "HtH Engine v<version>"`

5. Push branch and tag:
   - `git push origin master`
   - `git push origin v<version>`

6. Create GitHub Release from tag `v<version>` and attach:
   - `dist/hth-engine-v<version>.zip`

Notes:
- Release guard fails if it detects tracked local artifacts or potential hardcoded secrets.
- `LICENSE` must be included in any redistribution.
