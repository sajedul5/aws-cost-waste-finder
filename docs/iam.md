# IAM: scanning a client account

`cwf` only needs read access. The client creates one IAM role in their account, you assume it
with `--role-arn`, and they can delete it when the work is done. No access keys are shared.

## Files

| File | What it is |
|---|---|
| `iam/read-only-policy.json` | Minimum permissions for every check: only `Describe*`/`Get*` actions and `pricing:GetProducts`. The `CwfBillOptional` statement (`ce:GetCostAndUsage`, `ce:GetCostForecast`) is only for `cwf bill`; remove it if the client doesn't want to share bill data. A test (`tests/test_iam_policy.py`) fails if the code calls anything not listed here. |
| `iam/trust-policy.example.json` | Who may assume the role: your (consultant) account, and only with the agreed external ID. Placeholders only. |

## Client setup (AWS CLI, in the client account)

1. Agree on an external ID (a random string, e.g. `uuidgen`). Fill in the trust policy:
   replace `<CONSULTANT-ACCOUNT-ID>` with **your** account ID and `<EXTERNAL-ID>` with the string.
2. Create the role and attach the policy:
   ```sh
   aws iam create-role --role-name CwfReadOnly \
     --assume-role-policy-document file://trust-policy.json --max-session-duration 3600
   aws iam put-role-policy --role-name CwfReadOnly \
     --policy-name CwfReadOnly --policy-document file://read-only-policy.json
   ```
3. Send you the role ARN (`arn:aws:iam::<CLIENT-ACCOUNT-ID>:role/CwfReadOnly`).

## Run the scan (your machine)

Your own credentials (profile, SSO or `.env`) need `sts:AssumeRole` on that role ARN.
```sh
cwf scan --all-regions --role-arn arn:aws:iam::<CLIENT-ACCOUNT-ID>:role/CwfReadOnly \
  --external-id <EXTERNAL-ID>
```
For the 3-month bill trend (Cost Explorer, ~$0.02 per run, charged to the **client** account):
```sh
cwf bill --role-arn arn:aws:iam::<CLIENT-ACCOUNT-ID>:role/CwfReadOnly --external-id <EXTERNAL-ID>
```
In an AWS Organizations member account, Cost Explorer shows that account only; in the
management account it covers all linked accounts.

The session lasts 1 hour (a full scan takes well under a minute). The report never shows the role
ARN or account ID. Keep reports in `reports/` (gitignored) and never commit client data.

## Remove access (client)

```sh
aws iam delete-role-policy --role-name CwfReadOnly --policy-name CwfReadOnly
aws iam delete-role --role-name CwfReadOnly
```
