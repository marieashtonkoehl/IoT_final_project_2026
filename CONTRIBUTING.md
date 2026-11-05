# How we work in this repo

This is our team's shared guide to the repository: how work is planned, where code goes, and how a change gets from someone's laptop into the project. Keep it open while working; if something here is unclear or out of date, fix it in a pull request.

---

## 1. The big picture in one minute

Think of the project like a shared kitchen:

| GitHub thing | Kitchen version | What it is for us |
|---|---|---|
| **Repository (repo)** | The kitchen | All our code and docs, in one place |
| **`main` branch** | The finished dishes on the counter | The version that always works. Nobody cooks directly on it |
| **Branch** | Your own cutting board | A private copy where you work on one task without disturbing others |
| **Commit** | A photo of your progress | A saved step, with a short note of what changed |
| **Pull request (PR)** | "Can someone taste this before we serve it?" | A request to move your branch's work into `main`, reviewed by a teammate |
| **Issue** | An order ticket | One task, bug, or user story — with a number like `#12` |
| **Project board** | The ticket rail | Shows every ticket and whether it is *To do*, *In progress*, *In review* or *Done* |
| **Milestone** | Today's menu | The group of issues we plan to finish in one sprint |

The cycle for **every** piece of work:

```
Pick an issue → make a branch → commit → push → open a PR → teammate reviews → merge → issue closes automatically
```

---

## 2. Sprints and deadlines

| Sprint | Dates | Goal |
|---|---|---|
| Sprint 1 | 3 Nov → **17 Nov** (Sprint Review 1) | Repo + board set up, architecture, every sensor and actuator tested |
| Sprint 2 | 17 Nov → **3 Dec** (Sprint Review 2) | One full flow live: button press → database → dashboard |
| Sprint 3 | 3 Dec → **11 Dec** (MVP + release `v1.0`) | Locker cycle, alerts, analytics, map, documentation |
| Demo | week of 14 Dec | 15-min live demo |

Each sprint is a **milestone** on GitHub. An issue in the milestone "Sprint 2" is planned for Sprint 2.

⚠️ The instructor follows the **commit history** — small, regular commits from everyone count more than a big push in the last week. Commits after the `v1.0` tag on 11 Dec are not graded.

---

## 3. Issues — what to work on

### Reading an issue

Every issue has:

- **Title** — what to do, short.
- **Description** — the goal and a **"Done when"** checklist. When every box is ticked, the issue is finished.
- **Labels** — coloured tags that say *what kind* of work it is (see below).
- **Milestone** — which sprint it belongs to.
- **Assignee** — who is doing it. One person per issue.
- **"Part of #n"** — the user story it helps to deliver.

### Labels

| Label | Meaning |
|---|---|
| `user-story` | A feature described from a user's point of view ("As a visitor, I…"). Big; split into smaller task issues |
| `device` | Code that runs on the Raspberry Pi and talks to sensors/actuators (`device/`) |
| `backend` | The API, rules, database writes, external APIs (`backend/`) |
| `frontend` | The web page and the map (`frontend/`) |
| `data` | Database, Grafana dashboards, analytics |
| `infra` | Setup work: repo, board, Docker, systemd services, release |
| `documentation` | README, wiki, diagrams, reports |
| `test` | Trying out hardware or checking that something works |
| `bug` | Something that used to work or should work, but doesn't |
| `stretch` | Nice extra — only once the planned work is done |
| `priority:high` | Needed for the next Sprint Review — do first |
| `priority:med` | Needed for the MVP |
| `priority:low` | Improves the project but the MVP works without it |
| `good first issue` | Small, self-contained — a good one to start with |

### Creating a new issue

Found a bug or a missing task? Create an issue rather than keeping a private list.

1. Go to the repo → **Issues** tab → **New issue**.
2. Pick a template (**Task** or **Bug**), fill it in.
3. On the right: add **labels**, the **milestone** (sprint), and yourself as **assignee** if you'll do it.
4. **Submit**. Then add it to the board (see section 4) if it isn't added automatically.

---

## 4. The project board

The board is at **Projects** (top of the repo) → *Pollinator Station*, or directly: <https://github.com/users/marieashtonkoehl/projects/5>.

Views (tabs at the top of the board):

- **Board** — all cards by status
- **Sprints** — table grouped by milestone (one sprint at a time)
- **My tasks** — only the cards assigned to you

| Column | Meaning | Who moves it |
|---|---|---|
| **Backlog** | Planned, not in the current sprint yet | — |
| **To do** | In this sprint, not started | — |
| **In progress** | Someone is working on it right now | You, when you start |
| **In review** | A pull request is open and waiting for a reviewer | You, when you open the PR |
| **Done** | Merged into `main` | Moves automatically when the PR closes the issue |

Rules of thumb:

- Have **at most 1–2 cards** in *In progress* at once.
- Drag your card as soon as its state changes — the board is how we (and the instructor) see progress.
- Use the **filter / group by Milestone** view to see one sprint at a time.

---

## 5. Branches

`main` is protected: nobody pushes to it directly. All work happens on a branch.

### Naming

```
<type>/<issue-number>-<short-description>
```

| Type | Use for | Example |
|---|---|---|
| `feature/` | New functionality | `feature/14-button-cooldown` |
| `fix/` | Fixing a bug | `fix/31-led-bar-off-by-one` |
| `docs/` | Documentation only | `docs/22-wiring-table` |
| `test/` | Hardware tests | `test/6-pir-sensor` |
| `chore/` | Setup, config, tidy-up | `chore/1-repo-structure` |

Lowercase, words joined with `-`, always the issue number.

---

## 6. Step by step: from issue to merged code

The commands below are for the terminal (Mac: **Terminal** app; Pi: SSH). GitHub Desktop or VS Code can do the same with buttons.

### One-time setup (per computer)

```bash
# tell git who you are (use the email of your GitHub account)
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"

# get a copy of the repo
git clone https://github.com/marieashtonkoehl/IoT_final_project_2026.git
cd IoT_final_project_2026
```

### Every time you start a task

```bash
# 1. go to main and get the latest version
git switch main
git pull

# 2. make your branch for the issue (example: issue #14)
git switch -c feature/14-button-cooldown
```

Move the issue's card to **In progress**.

### While working — commit often

```bash
git status                       # see what changed
git add device/station.py        # pick the files to save (or: git add .)
git commit -m "Add cooldown check to button handler (#14)"
```

Good commit messages:

- Start with a verb: *Add*, *Fix*, *Update*, *Remove*, *Test*.
- Say **what** changed, briefly. Mention the issue: `(#14)`.
- Working together on one laptop? Credit your partner by adding a last line:

```
Add cooldown check to button handler (#14)

Co-authored-by: Partner Name <partner-email@example.com>
```

(Leave the empty line before `Co-authored-by`. Use the email of their GitHub account.)

### Upload your branch

```bash
git push -u origin feature/14-button-cooldown    # first time
git push                                          # after that
```

### Open a pull request

1. On GitHub, a yellow bar appears: **"Compare & pull request"** → click it.
2. Fill in the template. In the description write **`Closes #14`** — this closes the issue automatically when the PR is merged.
3. On the right: choose a **Reviewer** (a teammate).
4. **Create pull request**. Move the card to **In review**.

### Review someone else's PR

1. Open the PR → **Files changed** tab.
2. Read the changes. Comment on a line with the **+** button.
3. If you can, try it: `git fetch` then `git switch <their-branch>` and run it.
4. **Review changes** → *Approve* or *Request changes*, with a short comment.

Reviews are about the code, not the person — "maybe rename `x` to `light_pct`?" is a normal review comment.

### Merge

When the PR is approved and has no conflicts:

1. Click **Squash and merge** (puts the whole PR into `main` as one clean commit).
2. Click **Delete branch**.
3. On your computer:

```bash
git switch main
git pull
git branch -d feature/14-button-cooldown
```

The issue closes and the card moves to **Done**. 🎉

---

## 7. When things go sideways

| Situation | What to do |
|---|---|
| "Your branch is behind main" | `git switch main && git pull && git switch <your-branch> && git merge main` |
| Merge conflict | Git marks the file with `<<<<<<<`, `=======`, `>>>>>>>`. Keep the right lines, delete the markers, then `git add <file>` and `git commit`. Ask a teammate if unsure — it's normal |
| Committed to `main` by mistake (not pushed) | `git switch -c feature/<n>-name` (keeps your work on a new branch), then `git switch main && git reset --hard origin/main` |
| Forgot what branch you're on | `git status` (first line) |
| Accidentally committed a password/token | Tell the team immediately, **regenerate the token** (deleting the commit isn't enough on a public repo) |

---

## 8. Secrets and settings

- Passwords, tokens and API keys go in a file called **`.env`** — never in the code.
- `.env` is listed in `.gitignore`, so git ignores it.
- `.env.example` shows which settings exist, **without** real values. When you add a new setting, add it there too.

---

## 9. Code style (short)

- Python: clear names (`soil_moisture_pct`, not `sm`), a docstring at the top of each file, comments for anything non-obvious.
- One sensor or actuator → one small, testable function.
- Every hardware piece gets a test script in `device/tests/`.
- Keep the README and wiki up to date in the same PR as the code change.

---

## 10. Checklist before a Sprint Review

- [ ] All issues for the sprint are on the board and in the right column
- [ ] Everything finished is merged into `main`
- [ ] Every member has commits in this sprint
- [ ] The system runs from `main` on the Pi
- [ ] README / wiki reflect what was built
