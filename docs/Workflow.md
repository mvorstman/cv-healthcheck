Follow this workflow for every cv-healthcheck work session:

1. Before changing code
- Read current project docs first:
  - HANDOVER.md
  - README.md
  - ROADMAP.md
  - CHANGELOG.md
  - API_MAPPING.md
  - PROMPT.txt
- Check current git state:
  - git status
  - git branch
  - git log --oneline -5

2. During work
- Make small, focused changes.
- Preserve existing architecture.
- Do not overwrite unrelated work.
- Do not remove validation steps.
- Keep routes/templates thin.
- Keep business logic in service/modules, not Flask views.

3. Before committing
Run validation:

  python -m compileall src

If scripts changed:

  bash -n scripts/*.sh

If tests exist/relevant:

  python -m pytest

Also test relevant CLI commands or Flask routes when applicable.

4. Documentation updates
At the end of meaningful work, update relevant docs:
- CHANGELOG.md: what changed, validation results, commit hash
- HANDOVER.md: rolling forward note for the next session
- ROADMAP.md: only if direction or priorities changed
- API_MAPPING.md: only for validated API behavior
- README.md: only for user/developer-facing behavior
- PROMPT.txt: only if next-session context changed

Do not update docs just to create noise.

5. Git workflow
Use small clean commits.

Standard command:

  git add .
  git commit -m "<clear concise message>"
  git push

For release/version milestones:

  git tag <version>
  git push origin <version>

6. Handover format
At the end, always provide:

- Summary of completed work
- Files changed
- Validation performed and results
- Git commit hash
- Push status
- Open issues / next recommended step

7. Important behavior
- If validation fails, do not pretend success.
- Report the exact failing command and failure summary.
- Commit only if the user asked to commit or the workflow clearly calls for it.
- Never silently change architecture.
- Never treat Claude/ThirdParty notes as authoritative over project docs.