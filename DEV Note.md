# Git push note

Use one folder with two local branches:

```text
main   = private/backstage
public = source-only/origin
```

Ignore profiles:

```text
Z_gitignoreSaves/For_Backstage/.gitignore
Z_gitignoreSaves/For_Main/.gitignore
```

## New PC / owner setup

Run this once when the private repository is not on the computer:

```powershell
git clone https://github.com/xprgroupcorporation/SnapCursorX_BACKSTAGE.git SnapCursorX
cd SnapCursorX
git remote rename origin backstage
git remote add origin https://github.com/xprgroupcorporation/SnapCursorX.git
git fetch --all
git branch --set-upstream-to=backstage/main main
git switch -c public --track origin/main
git switch main
```

After creating `public`, do not use `commit-tree`, manually create commit hashes, or force-push.

## Pull private updates

```powershell
git switch main
git pull backstage main
```

## Public contributor setup

Contributors without private-repository access should clone the public repository:

```powershell
git clone https://github.com/xprgroupcorporation/SnapCursorX.git SnapCursorX
cd SnapCursorX
git pull origin main
```

## Push private/backstage

```powershell
git switch main
Copy-Item Z_gitignoreSaves/For_Backstage/.gitignore .gitignore -Force
git rm -r --cached .
git add .
git commit -m "V0.9.0 Completed Fr this time"
git push backstage main
```

## Push public/origin

Commit and push `main` first. The worktree must be clean before switching branches.

```powershell
git switch public
git merge --squash main
Copy-Item Z_gitignoreSaves/For_Main/.gitignore .gitignore -Force
git rm -r --cached .
git add .
git diff --cached --name-status
git commit -m "V0.9.0 Completed Fr this time"
git push origin public:main
git switch main
```

note: press q if stuck

`git rm --cached` removes files from Git tracking only. It does not delete local files.
Review the staged file list before every public commit.

## Dev Note


