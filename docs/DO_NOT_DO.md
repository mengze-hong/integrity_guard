# Do Not Do

Use this guardrail list during development, demos, backups, and release prep. If a change appears to require one of these actions, stop and get explicit review first.

## Research Integrity

- Do not fabricate citations, venues, DOIs, authors, page ranges, datasets, baselines, metrics, or experimental results.
- Do not treat AI output as verified evidence. Any AI-generated fix, rewrite, BibTeX entry, claim, number, or recommendation must be checked against the project files or an authoritative source before it is applied.
- Do not apply AI fixes directly to user work without showing the proposed change and preserving a clear review path.

## Repository Hygiene

- Do not commit `.env`, `data/secrets.enc`, uploaded user files under `uploads/`, or `.cursor/plans`.
- Do not mix unrelated files into the same change. Keep documentation, tests, feature work, generated data, and local experiments separated unless the release owner explicitly asks for a bundled change.
- Do not edit `.cursor/plans` as part of routine implementation or release work.

## Secrets And Credentials

- Do not write LLM API keys, internal LLM endpoints, JWT secrets, admin credentials, payment provider keys, private keys, bearer tokens, or webhook secrets into tracked files.
- Do not use placeholders that resemble real secrets in committed docs, tests, fixtures, screenshots, or changelog entries.
- Do not move secrets from ignored files into tracked config as a workaround for local setup. Document the required environment variable instead.

## Public Exposure

- Do not expose an un-hardened development server through a temporary public tunnel provider or any similar public forwarding service.
- Do not demo a public URL until authentication, rate limits, secret posture, upload limits, cleanup behavior, and logs have been reviewed.
- Do not paste provider-specific tunnel commands or forbidden provider names into tracked files. Keep the policy generic so scans remain stable.
