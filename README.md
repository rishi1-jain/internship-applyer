# Internship Pilot

A private, single-user internship workspace. Discover roles, automatically prepare tailored application packets, review them, then use the browser companion to fill the actual form. You perform the final site review and submission.

## Start whenever you want to apply

Requires **Python 3.10 or newer**. Download this repository with GitHub's **Code → Download ZIP** and extract it, or clone it:

```sh
git clone https://github.com/rishi1-jain/internship-applyer.git
cd internship-applyer
```

- **macOS:** double-click `Start Internship Pilot.command`, or run `sh start.sh` in Terminal.
- **Linux:** run `sh start.sh`.
- **Windows:** double-click `start.bat` (requires Python's `py` launcher), or use the manual setup below.

The launcher creates a local Python virtual environment and installs the required package on first use. Then open **http://127.0.0.1:8765**. Keep the terminal process running for monitoring. Stop it with Control-C. Run the launcher again whenever you want to use the app; it preserves your local work.

For a manual setup:

```sh
python3 -m venv .venv
# macOS/Linux:
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
# Windows equivalents: .venv\Scripts\python.exe -m pip install -r requirements.txt
#                      .venv\Scripts\python.exe server.py
```

If the port is occupied, use the existing server or stop it first. `--port` can change the dashboard port; the companion currently requires 8765.

## Your private profile and applications

This repository contains application source and fictional test fixtures. Your resume, contact details, drafts, downloaded PDFs, database, and pairing token are excluded from Git. A fresh checkout starts with a blank profile: paste your resume and enter your information in **My profile & resume**.

If you already used the local app, continue using its existing folder to retain your profile and drafts. To move your setup to a fresh checkout, stop both app instances and privately copy the old `data/` folder into the new folder. Never upload `data/` to GitHub. Each checkout has separate data unless you set `PILOT_DATA_DIR`.

## First use

1. **My profile & resume**: enter or confirm your resume, expected graduation, contact information, and preferences. Phone and eligibility answers are intentionally blank. Edit stale facts before preparing drafts. The app does not verify your credentials.
2. **Company watchlist**: six verified Greenhouse board identifiers are preloaded: Cloudflare, Databricks, Figma, Scale AI, Pinterest, and Roblox. Add more Greenhouse, Lever (global/EU), or Ashby boards with the company’s board slug. Run **Check boards now**.
3. Hourly monitoring, automatic draft preparation, and macOS notifications are enabled by default. Configure them in the watchlist. Polls run while the server is running and the Mac is awake; this version does not install an always-on login service. macOS may suppress notifications based on system settings. Activity retains all discoveries and errors. Browser notifications are optional and require an open dashboard.
4. **Application queue**: examine each packet’s tailored resume, base-resume comparison, matched/missing keywords, original posting, and saved answers. Edit and save. Confirm your review and approve for filling.
5. Install the companion in Chrome or Edge using **Load unpacked** and the `extension` directory. Pair it with the token under **Browser companion** in the dashboard. This is a manual setup step; it has not been installed automatically.
6. Open the packet’s application link and navigate to its form. Click the extension, choose the approved packet, and fill it. Inspect the report, actual form, and resume upload. Complete remaining fields, submit on the company site, then mark the packet submitted in the dashboard.

## Working features

- Persistent SQLite storage for profile, company boards, listings, application snapshots, and activity.
- Greenhouse and Lever feed monitoring with pagination for Lever, deduplication, closure/reopening detection, per-board errors, and retry on later scans. An incomplete or failed board scan does not close its jobs.
- Ashby adapter implemented against its documented public feed and covered with fixtures. Live Ashby access returned HTTP 403 in this environment; it remains unverified here. A failed board displays its error rather than simulated listings.
- Broad technical title preferences; optional location keywords. Titles must explicitly contain intern, internship, co-op, or placement. This is a company watchlist, not a search engine over every employer. Some roles require graduate study or work authorization; eligibility is for you to verify.
- Automatic preparation of new matching listings. Repeated checks preserve your edits and do not create duplicate packets. Pausing automatic preparation preserves existing drafts.
- **Local tailoring without a model/API key:** score the posting against a fixed skills vocabulary and prioritize verbatim bullets inside the same experience/project group. No new skills, titles, metrics, experience, or eligibility answers are generated. It does not paraphrase or perform semantic AI rewriting. Keyword coverage is not an ATS score or probability of an interview.
- Editable per-job resume and answers, saved profile snapshots, PDF/text export, explicit approval, and approval revocation after packet edits or detected description/URL changes. Profile edits affect future packets only. Download uses the saved version.
- Chrome/Edge Manifest V3 companion with active-tab access only and local-server host permission. It fills standard text fields, exact custom question answers, exact select options, and recognizable PDF resume inputs. Existing answers and files are preserved. It never clicks submit, checkboxes, radio buttons, or consent controls.
- Packets are bound to the selected job URL and identity. A Greenhouse legacy-host redirect is supported. Unexpected job identifiers, paths, and application-site redirects are refused. For a custom careers page that redirects to another ATS, import the final application URL as a new posting and prepare/review that packet.

## Practical limits

This is a working local first version, not a universal unattended application agent. Workday, LinkedIn, Indeed, and other unsupported systems accept manual posting import; form filling depends on recognizable controls. CAPTCHA, login, rich dropdown widgets, cross-origin iframes, essay questions without saved answers, consent, and legal disclosures may require manual entry. Some sites hide their file inputs; upload the exported PDF yourself if it is not recognized. External job sites have not received your resume or application during development. The companion has automated DOM-fixture tests, but has not been validated on a submitted real application.

The PDF renderer provides clean selectable text and supports multiple pages for longer resumes. Review the export before using it. Your base resume stays in local storage. Generated exports are never committed.

Public feeds generally establish discovery time, not the precise moment a job opened. A posting that disappears is marked closed; availability must be checked on the company site. Current title/location preferences filter the dashboard; saved packets remain accessible. Profile updates do not retroactively regenerate existing packets. Edit an existing packet to update its facts.

## Data and access

The service binds only to `127.0.0.1`. Profile and resume data stay under `data/`; only public company feeds are requested externally. No analytics, external fonts, AI requests, cloud sync, or email delivery. Employers see your information when you use the companion on their page or manually upload it; some sites may process form fields before you submit.

The local database is not encrypted. Its directory is owner-only. Protect it with your Mac account and disk encryption. The extension pairing token is stored in `data/extension-token`; keep it private. The extension stores it in browser local extension storage. To revoke it, stop the server, replace the token file with a new random token, and restart; pair the companion again. Loopback host/origin checks prevent ordinary cross-site webpage access. This is designed for a trusted personal computer, not a shared or multi-user server. Back up `data/` while the server is stopped; exclude it from source control and public archives.

## Verification

The backend integration tests use an isolated temporary database and mock job feeds. They cover approval gating, immutable profile snapshots, edited-packet revocation, job closure/reopening, feed errors, duplicate prevention, relevance boundaries, PDF facts, origin/token checks, and submission tracking. The companion tests use synthetic forms, never real job applications.

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
npm ci
npm test
```

Node dependencies are only for developer tests; running the app does not require Node or npm. UI QA includes live discovery, draft review, profile/watchlist views, and the desktop layout. Responsive CSS is included; mobile browser testing remains outstanding.

## Implementation

- `server.py`: loopback HTTP API, SQLite schema, monitor worker, adapters, approval state.
- `pdf_resume.py`: PDF renderer.
- `static/`: dependency-free dashboard.
- `extension/`: Chrome/Edge companion; no submission endpoint or submit action.
- `tests/`: workflow/security/regression and synthetic form tests.

Primary API references: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board), [Lever Postings API](https://github.com/lever/postings-api), [Ashby Public Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api), [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab).
