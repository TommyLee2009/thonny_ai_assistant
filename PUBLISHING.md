# Publishing to PyPI with Trusted Publishing

This project uses PyPI Trusted Publishing through GitHub Actions OIDC. The
publishing workflow does not use a long-lived PyPI API token.

Official references:

- [Creating a PyPI project with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Publishing with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [PyPI publisher management](https://pypi.org/manage/account/publishing/)
- [GitHub repository](https://github.com/TommyLee2009/thonny_ai_assistant)

## Current release coordinates

| Setting | Value |
| --- | --- |
| PyPI project name | `thonny-ai-assistant` |
| GitHub owner | `TommyLee2009` |
| GitHub repository | `thonny_ai_assistant` |
| Workflow file | `publish.yml` |
| GitHub environment | `pypi` |
| Package version | `0.6.3` |
| Release tag | `0.6.3` |

As of 2026-11-01, `thonny-ai-assistant` did not exist on PyPI. A pending
Trusted Publisher does **not** reserve the project name until the first
successful publication. Someone else could claim the name before that step.

## One-time PyPI setup

1. Sign in to PyPI and enable two-factor authentication.
2. Open [Account publishing settings](https://pypi.org/manage/account/publishing/).
3. Add a pending **GitHub Actions** publisher with:
   - PyPI project name: `thonny-ai-assistant`
   - Owner: `TommyLee2009`
   - Repository name: `thonny_ai_assistant`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
4. Save the pending publisher.

After the first publication, PyPI converts the pending publisher into a normal
project publisher.

## One-time GitHub setup

1. Open the repository's **Settings > Environments**.
2. Create an environment named `pypi`.
3. Add required reviewers if releases should need manual approval.
4. Optionally restrict deployment tags to the release-tag pattern you use.

The environment name in GitHub must match the environment configured in both
the workflow and the PyPI pending publisher.

## Repository cleanup before release

The currently uploaded repository tracks generated build files. Remove them
from Git tracking:

```powershell
git rm -r --cached build dist thonny_ai_assistant.egg-info
git rm -r --cached tests/__pycache__
git rm -r --cached thonnycontrib/thonny_ai_assistant/__pycache__
git rm publish_to_pypi.py
git add .gitignore .gitattributes .github/workflows/publish.yml
git add PUBLISHING.md README.md CHANGELOG.md
git commit -m "Add trusted PyPI publishing workflow"
git push origin main
```

`--cached` keeps local files but stops tracking them. The repository's
`.gitignore` prevents build outputs and Python caches from being added again.

If files have already been committed with secrets, deleting them from the
latest commit is not sufficient. Revoke the credential and rewrite repository
history before publishing.

## Publish the current version

The package version and release tag must match exactly. This project uses the
tag name without a leading `v`.

1. Confirm both `setup.py` and `pyproject.toml` contain version `0.6.3`.
2. Push the publishing workflow and cleanup commit to `main`.
3. Create and push tag `0.6.3` pointing to the source that should be published.
4. Draft a GitHub Release for tag `0.6.3` and publish it. This triggers the
   workflow automatically. If necessary, it can also be started manually with
   tag `0.6.3` from the Actions page.
5. The `Publish to PyPI` workflow will:
   - verify the tag and package versions match;
   - build a wheel and source distribution;
   - validate the package metadata with Twine;
   - request a short-lived OIDC credential;
   - upload the distributions to PyPI.
6. Confirm the result at
   <https://pypi.org/project/thonny-ai-assistant/>.

## Future releases

1. Update the version in both `setup.py` and `pyproject.toml`.
2. Run the tests and build the distributions.
3. Commit and push the version change.
4. Create an annotated tag with the same version:

   ```powershell
   git tag -a 0.6.4 -m "Release 0.6.4"
   git push origin 0.6.4
   ```

5. Publish a GitHub Release for that tag.

PyPI does not allow replacing an already uploaded file with the same filename.
Always publish a new version instead of reusing an existing one.

## Local preflight

```powershell
& "C:\Program Files\Thonny\python.exe" -m unittest discover -s tests -v
& "C:\Program Files\Thonny\python.exe" -m pip wheel . --no-deps --wheel-dir dist
& "C:\Program Files\Thonny\python.exe" -m pip install --upgrade twine
& "C:\Program Files\Thonny\python.exe" -m twine check dist/*
```

## Troubleshooting

- `invalid-publisher`: confirm the repository owner, repository name, workflow
  filename, and environment name exactly match PyPI.
- `id-token` permission error: keep `id-token: write` on the publish job.
- Version mismatch: the release tag and `pyproject.toml` version must match.
- File already exists: increment the package version; do not reuse a filename.
