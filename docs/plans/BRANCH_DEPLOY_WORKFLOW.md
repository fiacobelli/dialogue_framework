# Branch and Deployment Workflow

This repository contains two related production apps:

- Microsite app: active work starts from `bernard-dev`, stable deploys use `bernard-main`.
- Screening app: active work starts from `bernard-sdoh-screening-dev`, stable deploys use `bernard-sdoh-screening-main`.

The older branches, `bernard` and `bernard-sdoh-screening`, are retained as historical/current baselines. New work should move to the `*-dev` branches.

## Branch Roles

| App | Development branch | Stable deploy branch | Legacy baseline |
| --- | --- | --- | --- |
| Microsite | `bernard-dev` | `bernard-main` | `bernard` |
| Screening | `bernard-sdoh-screening-dev` | `bernard-sdoh-screening-main` | `bernard-sdoh-screening` |

## Required Workflow

1. Make code changes only on the matching `*-dev` branch.
2. Test locally before deployment.
3. Commit and push the `*-dev` branch.
4. Merge the tested `*-dev` branch into the matching `*-main` branch.
5. Push the `*-main` branch.
6. Pull the matching `*-main` branch on EC2.
7. Restart only the affected service.
8. Run health checks before calling the deploy complete.

## When Fixing Something

Use this decision rule first:

- Microsite fix: work on `bernard-dev`, deploy from `bernard-main`.
- Screening fix: work on `bernard-sdoh-screening-dev`, deploy from `bernard-sdoh-screening-main`.

Never start a fix on a `*-main` branch. The `*-main` branches are stable deployment branches only.

The normal repair sequence is:

1. Switch to the correct `*-dev` branch.
2. Make the smallest clean fix.
3. Run local tests or manual localhost testing.
4. Commit and push the `*-dev` branch.
5. Merge the tested `*-dev` branch into the matching `*-main` branch.
6. Push the `*-main` branch.
7. Pull the `*-main` branch on EC2.
8. Restart only the affected service.
9. Run local EC2 health checks.
10. Run public URL checks.

If local testing fails, stay on the `*-dev` branch and keep fixing there. Do not merge into `*-main` until the fix is stable.

## Microsite Commands

```bash
git checkout bernard-dev
# make changes
# test locally
git add <changed-files>
git commit -m "Describe microsite change"
git push origin bernard-dev

git checkout bernard-main
git merge --ff-only bernard-dev
git push origin bernard-main
```

EC2 deploy branch:

```bash
cd /home/ubuntu/transplant-microsite
git checkout bernard-main
git pull --ff-only
sudo systemctl restart microsite
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5001/
curl -sS -o /dev/null -w "%{http_code}\n" https://ludi.a4hlab.org/microsite
```

## Screening Commands

```bash
git checkout bernard-sdoh-screening-dev
# make changes
# test locally
git add <changed-files>
git commit -m "Describe screening change"
git push origin bernard-sdoh-screening-dev

git checkout bernard-sdoh-screening-main
git merge --ff-only bernard-sdoh-screening-dev
git push origin bernard-sdoh-screening-main
```

EC2 deploy branch:

```bash
cd /home/ubuntu/sdoh-screening
git checkout bernard-sdoh-screening-main
git pull --ff-only
sudo systemctl restart sdoh
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
curl -sS -o /dev/null -w "%{http_code}\n" https://ludi.a4hlab.org/
```

## Rules

- Do not deploy directly from a `*-dev` branch.
- Do not make manual production edits on EC2 unless it is an emergency hotfix.
- If an emergency hotfix is made on EC2, copy it back into the correct local branch and commit it immediately.
- Keep deployment branches boring: only tested work should land in `*-main`.
- Before switching EC2 branches, always check `git status --short --branch`.
- Preserve unrelated untracked files unless they are explicitly reviewed and removed.
- If a branch switch or merge is not fast-forward, stop and inspect before resolving it manually.

## Current EC2 Mapping

Target production mapping:

| Server path | Service | Branch |
| --- | --- | --- |
| `/home/ubuntu/transplant-microsite` | `microsite` | `bernard-main` |
| `/home/ubuntu/sdoh-screening` | `sdoh` | `bernard-sdoh-screening-main` |
