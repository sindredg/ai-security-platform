# Repository settings and signed commits: operator procedure

Status: Implemented on 2026-10-17. The settings were made in the web interface that day and read back with the command in step 7. On 2026-10-20 two checks were added to `protect-main` with [Add a required check](#add-a-required-check), and read back, on 2026-10-23 one more, on 2026-10-25 one more here and two on the targets repository, on 2026-10-26 one more here, and on 2026-10-27 step 4's deletion of merged branches in both repositories, read back with step 7, and "Approved commit" on the targets repository. Steps 8 to 11 were run on 2026-10-17, with the results in the [milestone 3a worklog](../worklogs/0004-edge-network-and-monitoring.md#the-fail-side-on-github). On 2026-10-17 steps 4 to 11 were run as written, through the API, on the new [targets repository](https://github.com/sindredg/ai-security-platform-test), with its own list of checks in step 5 ([worklog](../worklogs/0004-edge-network-and-monitoring.md#the-targets-repositorys-settings)). Steps 1 to 3 were not repeated: the key and the allowed signers file were already in place.

The repository is the approval channel, so its settings are part of the system ([pipeline](../components/pipeline.md#repository-settings), [ADR 0024](../decisions/0024-the-targets-in-their-own-repository-and-signed-commits.md)). These steps set up commit signing on the workstation, the allowed signers file, squash-only merges, the two rulesets, and then prove the fail side.

## Inputs and access

| Input | Notes |
| --- | --- |
| Administrator on the repository | `REPLACE_WITH_OWNER/REPLACE_WITH_REPO` below. Rulesets need it |
| `gh` signed in with the `repo`, `workflow`, and `admin:ssh_signing_key` scopes | `gh auth status` lists them |
| Git 2.34 or later and OpenSSH 8.2 or later on the workstation | SSH signing |
| An SSH key for signing, with a passphrase | `REPLACE_WITH_SIGNING_KEY` is its private half. Keep it apart from the cloud credentials |
| A checkout of this repository | The workflow and the script come from `main` |

## Signing on the workstation

1. Make Git sign every commit with the key.

   ```bash
   git config --global gpg.format ssh
   git config --global user.signingkey REPLACE_WITH_SIGNING_KEY.pub
   git config --global commit.gpgsign true
   ```

   Expected: no output. The next commit asks for the passphrase, or takes the key from a running `ssh-agent`.

2. Register the public half on the GitHub account as a signing key.

   ```bash
   gh ssh-key add REPLACE_WITH_SIGNING_KEY.pub --type signing --title aisec-commit-signing
   gh api users/REPLACE_WITH_OWNER/ssh_signing_keys --jq '.[].key'
   ```

   Expected: the key text printed by the second command equals the first two fields of `REPLACE_WITH_SIGNING_KEY.pub`. Commits signed with it now show as verified on GitHub.

3. Name the key in `.github/allowed_signers`, in a pull request signed with it.

   ```bash
   printf '%s %s\n' REPLACE_WITH_OWNER "$(cut -d' ' -f1,2 REPLACE_WITH_SIGNING_KEY.pub)" > .github/allowed_signers
   git -c gpg.ssh.allowedSignersFile=.github/allowed_signers log -1 --format='%G? %GS'
   ```

   Expected: after the commit, `G REPLACE_WITH_OWNER`. Replacing the key later is the same step, with the new key's line, in a pull request signed with the old key ([credentials](../security/credentials.md)).

## Repository settings

4. Allow squash merges only, and have GitHub delete a pull request's branch when it merges.

   ```bash
   gh api -X PATCH repos/REPLACE_WITH_OWNER/REPLACE_WITH_REPO \
     -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
     -F delete_branch_on_merge=true \
     --jq '{allow_squash_merge,allow_merge_commit,allow_rebase_merge,delete_branch_on_merge}'
   ```

   Expected: `{"allow_merge_commit":false,"allow_rebase_merge":false,"allow_squash_merge":true,"delete_branch_on_merge":true}`. A rebase merge would put commits on `main` that GitHub does not sign.

5. Create the ruleset on the default branch. "Commit signatures" can be added only after the job has run once, so open any signed pull request first and let it run.

   ```bash
   cat > protect-main.json <<'JSON'
   {
     "name": "protect-main",
     "target": "branch",
     "enforcement": "active",
     "bypass_actors": [],
     "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
     "rules": [
       {"type": "deletion"},
       {"type": "non_fast_forward"},
       {"type": "required_signatures"},
       {"type": "pull_request", "parameters": {
         "allowed_merge_methods": ["squash"],
         "required_approving_review_count": 0,
         "dismiss_stale_reviews_on_push": false,
         "require_code_owner_review": false,
         "require_last_push_approval": false,
         "required_review_thread_resolution": false}},
       {"type": "required_status_checks", "parameters": {
         "strict_required_status_checks_policy": false,
         "required_status_checks": [
           {"context": "Terraform format and validate", "integration_id": 15368},
           {"context": "Checkov", "integration_id": 15368},
           {"context": "Trivy", "integration_id": 15368},
           {"context": "Secret scan", "integration_id": 15368},
           {"context": "ShellCheck", "integration_id": 15368},
           {"context": "Ruff", "integration_id": 15368},
           {"context": "Tool service image", "integration_id": 15368},
           {"context": "Tool service tests", "integration_id": 15368},
           {"context": "Kubernetes manifests", "integration_id": 15368},
           {"context": "Log copier tests", "integration_id": 15368},
           {"context": "Squid configuration", "integration_id": 15368},
           {"context": "Dispatch tests", "integration_id": 15368},
           {"context": "Dispatch image", "integration_id": 15368},
           {"context": "Tool service dependency scan", "integration_id": 15368},
           {"context": "Collector tests", "integration_id": 15368},
           {"context": "Commit signatures", "integration_id": 15368},
           {"context": "Evidence pages", "integration_id": 15368}]}}
     ]
   }
   JSON
   gh api -X POST repos/REPLACE_WITH_OWNER/REPLACE_WITH_REPO/rulesets --input protect-main.json --jq '{id,name,enforcement}'
   ```

   Expected: the new ruleset's ID, `protect-main`, `active`. `15368` is the GitHub Actions app: a status with the same name from anything else does not count. The required checks are the [pipeline page's](../components/pipeline.md#checks-on-every-pull-request) list without the converter dependency scan. When a check is added there, it is added here. For the targets repository, the list is its own nine: Terraform format and validate, Checkov, Trivy, Secret scan, ShellCheck, Commit signatures, Quadlet units, Ruff, and Approved commit ([pipeline](../components/pipeline.md#the-targets-repository)).

6. Create the ruleset that refuses unsigned commits on every branch.

   ```bash
   gh api -X POST repos/REPLACE_WITH_OWNER/REPLACE_WITH_REPO/rulesets --input - --jq '{id,name,enforcement}' <<'JSON'
   {"name": "signed-commits", "target": "branch", "enforcement": "active", "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
    "rules": [{"type": "required_signatures"}]}
   JSON
   ```

   Expected: the new ruleset's ID, `signed-commits`, `active`. On the live repository this ruleset is named `signed-comits`. Nothing reads the name.

7. Read everything back.

   ```bash
   R=repos/REPLACE_WITH_OWNER/REPLACE_WITH_REPO
   for id in $(gh api $R/rulesets --jq '.[].id'); do
     gh api $R/rulesets/$id --jq '{name,enforcement,include:.conditions.ref_name.include,bypass:.bypass_actors,rules:[.rules[].type]}'
   done
   gh api $R/rules/branches/main --jq '[.[]|select(.type=="required_status_checks")|.parameters.required_status_checks[]|"\(.context)@\(.integration_id)"]'
   gh api $R --jq '{allow_squash_merge,allow_merge_commit,allow_rebase_merge,delete_branch_on_merge,push_protection:.security_and_analysis.secret_scanning_push_protection.status}'
   ```

   Expected: two rulesets, both `active` with an empty bypass list. `protect-main` on `~DEFAULT_BRANCH` with `deletion`, `non_fast_forward`, `pull_request`, `required_status_checks`, `required_signatures`. The second on `~ALL` with `required_signatures` only. Seventeen checks, each `@15368`, or nine on the targets repository. Squash only, merged branches deleted, and push protection `enabled`.

### Add a required check

A new job in the checks workflow becomes required by adding it to `protect-main`. Run it after the job has passed on `main` once, so a pull request has a run to wait for, or while the pull request that adds the job is the only one open and its run has passed. Any other open pull request never runs the job, and is blocked until it takes the workflow from `main`.

```bash
R=repos/REPLACE_WITH_OWNER/REPLACE_WITH_REPO
ID=$(gh api $R/rulesets --jq '.[] | select(.name == "protect-main") | .id')
gh api $R/rulesets/$ID > protect-main-before.json
jq --arg check "REPLACE_WITH_JOB_NAME" '{name, target, enforcement, conditions, bypass_actors,
  rules: [.rules[] | if .parameters == null then {type} else {type, parameters} end
    | if .type == "required_status_checks"
      then .parameters.required_status_checks += [{context: $check, integration_id: 15368}] else . end]}' \
  protect-main-before.json > protect-main-new.json
diff <(jq -S '{name, target, enforcement, conditions, bypass_actors, rules: [.rules[] | if .parameters == null then {type} else {type, parameters} end]}' protect-main-before.json) \
  <(jq -S . protect-main-new.json)
gh api -X PUT $R/rulesets/$ID --input protect-main-new.json --jq '[.rules[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context]'
```

Expected: the diff shows the one added check and nothing else. The PUT returns the list with it at the end. Then run step 7, and add the check to step 5's list.

Used on 2026-10-20 for "Dispatch tests" and "Dispatch image", on 2026-10-23 for "Tool service dependency scan", while its pull request was the only one open, on 2026-10-25 for "Collector tests", while the only open pull request had passed it, and on 2026-10-26 for "Evidence pages", with the `jq` step done in Python, while its own pull request was the only one open and had passed it. On the targets repository, on 2026-10-25 for "Quadlet units" and "Ruff", and on 2026-10-27 for "Approved commit", each time with no pull request open.

## The fail side

Run from a clean `main`. Each test leaves a pull request or a branch behind that steps 11 removes. In the steps, `R` is set as in step 7 and `MAIN` is `$(git rev-parse origin/main)`.

8. A pull request with a commit GitHub signs is blocked.

   ```bash
   gh api $R/git/refs -f ref=refs/heads/test/signature-api-commit -f sha=$MAIN
   gh api graphql --input - <<JSON
   {"query":"mutation(\$i:CreateCommitOnBranchInput!){createCommitOnBranch(input:\$i){commit{oid signature{wasSignedByGitHub state}}}}",
    "variables":{"i":{"branch":{"repositoryNameWithOwner":"REPLACE_WITH_OWNER/REPLACE_WITH_REPO","branchName":"test/signature-api-commit"},
     "expectedHeadOid":"$MAIN","message":{"headline":"test: commit made through the API"},
     "fileChanges":{"additions":[{"path":"docs/signature-test-1.md","contents":"$(printf 'Not for merge.\n' | base64 -w0)"}]}}}}
   JSON
   gh api $R/pulls -f head=test/signature-api-commit -f base=main -f title="test: signature check fail side" --jq .number
   ```

   Expected: `wasSignedByGitHub: true`, state `VALID`, then a pull request number. When its checks finish, "Commit signatures" has failed with `FAILED <hash> E`, and

   ```bash
   gh api $R/pulls/REPLACE_WITH_PR --jq .mergeable_state
   ```

   prints `blocked`. A draft is blocked anyway, so the pull request is opened ready for review.

9. An unsigned push is refused.

   ```bash
   git switch -c test/signature-unsigned
   echo 'Not for merge.' > docs/signature-test-2.md
   git add docs/signature-test-2.md
   git -c commit.gpgsign=false commit -m "test: unsigned commit"
   git push origin test/signature-unsigned
   gh api $R/branches/test/signature-unsigned
   ```

   Expected: `push declined due to repository rule violations` and `Commits must have verified signatures`, then `Branch not found (HTTP 404)`.

10. A job with the required check's name does not satisfy it. Repeat step 8 on the branch `test/signature-spoofed-job`, with this file as the addition at `.github/workflows/spoof.yml`:

    ```yaml
    name: spoof
    on:
      pull_request:
    permissions: {}
    jobs:
      spoof:
        name: Commit signatures
        runs-on: ubuntu-26.04
        steps:
          - run: "true"
    ```

    Expected: two runs named "Commit signatures", one failure and one success. Then re-run the passing one alone, so that it finishes last:

    ```bash
    gh run rerun REPLACE_WITH_SPOOF_RUN_ID
    gh api $R/pulls/REPLACE_WITH_PR --jq .mergeable_state
    ```

    Expected: `blocked` after the re-run finishes. If it prints `clean`, the check can be faked: stop and do not merge anything until the design changes.

11. Clean up.

    ```bash
    git switch main && git branch -D test/signature-unsigned
    for n in REPLACE_WITH_PR_NUMBERS; do gh api -X PATCH $R/pulls/$n -f state=closed --jq '"\(.number) \(.state) merged=\(.merged)"'; done
    for b in test/signature-api-commit test/signature-spoofed-job; do gh api -X DELETE $R/git/refs/heads/$b; done
    ```

    Expected: each pull request `closed merged=false`, and `gh api $R/branches/<branch>` returns 404 for both branches.

## Notes

- The REST contents endpoint makes commits GitHub does not sign when called with a user's token. The ruleset in step 6 refuses them with HTTP 409. Step 8 uses GraphQL because that path does get GitHub's signature, which is what a stolen token would use.
- Dependabot's pull requests fail the check by design. The operator makes the same change in a signed pull request.
