# GitHub publication guide / GitHub公開手順

This is the maintenance guide for the published repository at
<https://github.com/anpanmanj987-hub/agentcrashlab>. **The package is not uploaded to PyPI.** Package/trademark availability
has not been reserved. Forks can follow the same steps under their own account.

## 1. Local release check

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python scripts/demo.py --transport http --output artifacts/release-demo
python -m build
python scripts/smoke_wheel.py
```

The demo returns 0 if its known pass/fail pattern is correct. Two intentionally
broken naive runs must be FAIL. Individual `run` commands return 1 for business
check failure. `verify` checks integrity, not whether business checks passed.

Before making the repository public, inspect every file for secrets and customer
data. The included demo uses synthetic data only. Custom evidence is not
automatically anonymized. Review the MIT copyright attribution and project name
for your intended ownership, and read `SECURITY.md`.

## 2. Create the repository (owner action)

The following commands change your GitHub account. They are instructions only;
they are kept for forks and re-creations. Run from the extracted
`agentcrashlab/` folder after reviewing the source. They require Git and an
authenticated GitHub CLI. If you already have a repo, follow your own branch/PR
workflow rather than replacing it.

```bash
git init -b main
git add .
git commit -m "Initial AgentCrashLab 0.1.0 source release"
gh repo create agentcrashlab --public --source=. --remote=origin --push
```

Git uses your configured author identity. Do not copy a made-up author address.
In a browser, creating an empty repository and pushing with the commands GitHub
shows is equally valid. Choose the correct personal account or organization.

Suggested description:

> Fault-inject agent tool calls. Verify committed business outcomes, not success claims.

Suggested topics: `ai-agents`, `fault-injection`, `testing`, `idempotency`,
`reliability`, `python`, `llm`, `developer-tools`.

Enable private vulnerability reporting if your repository supports it. Review
GitHub Actions results across the matrix before tagging; a locally passing suite
is not a claim that GitHub CI already passed. Branch protection and permissions
are owner choices, not changes made by this source archive.

## 3. Demo, release and distribution

`site/index.html` is the executed HTTP comparison, self-contained and suitable for
static hosting. It does not execute agents in the visitor's browser. For GitHub
Pages, deploy the **contents of `site/`** using your selected Pages workflow; no
Pages deployment or public URL has been created here. `docs/assets/demo.gif` is
captured from the actual report UI, not an invented benchmark.

After CI is green, optionally tag `v0.1.0` and attach the built wheel and source
archive to a GitHub Release. Do not claim `pip install agentcrashlab` works from
PyPI until the package has actually been published under an available name.
Installation from this checkout or the provided local wheel works without that.
PyPI publishing, tokens and trusted publishing configuration are intentionally
not included in automated workflows.

## 4. Post-publication changes

Add the real project/repository URLs to `pyproject.toml`, README and citation
metadata only after they exist. Add genuine CI badges only for the real workflow.
Publish measured live-model trials separately from deterministic reference
policies. Do not add invented adoption figures, star counts or compliance claims.

### 日本語要点

この一式は公開用のソースコードです。GitHub/PyPIへの実際の公開は未実施です。
展開後、まず `python scripts/demo.py --transport http --open` で動作を確認し、
所有者名・ライセンス表記・秘密情報の有無を確認してから新規リポジトリへpushします。
GitHub Actionsの実行結果を確認した後にリリースタグを付けてください。
`site/index.html` はブラウザで動く静的な証跡ビューアで、モデルの実行環境ではありません。
