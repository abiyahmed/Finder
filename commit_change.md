# Step 1: Create an "amend!" commit that targets exactly that old commit
# --only ensures we don't touch staged files (there are none)
# --allow-empty is required since we're not changing content
git commit --allow-empty --only --fixup=amend:<old-commit-hash> --author="PR Writer <prwriter@rebirthexperts.com>" --no-edit

# Step 2: Automatically apply it (rewrites only that commit, no editor opens)
git rebase --autosquash --autostash <old-commit-hash>^



git show --no-patch --pretty=fuller <old-commit-hash>
To check the fix and get the new base sha.