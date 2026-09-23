# Progress Log

Record each step: what was built, AWS resources created (names/ARNs/regions), decisions, and review notes.

## Setup — 2026-09-23
- Repo scaffolded with `frontend/`, `api/`, `lambdas/{lf0,lf1,lf2}`, `scripts/`, `docs/`.
- Requirements and step plan in `docs/requirements.md` (includes extra credit).
- AWS CLI configured. Account `088850687383`, region `us-east-1`. The old `cloud-class-lab-user` had almost no permissions, so the default profile now uses IAM user `cc-hw1-dev` (AdministratorAccess-style access, personal account).
- Root MFA and a cost budget: set up by user.

## AWS resources created
| Resource | Name | Region | Notes |
|----------|------|--------|-------|
| S3 bucket (static website, public read) | `cc-hw1-chatbot-frontend-088850687383` | us-east-1 | http://cc-hw1-chatbot-frontend-088850687383.s3-website-us-east-1.amazonaws.com — index/error doc `chat.html`; redeploy with `scripts/deploy_frontend.sh` |

## Step 1 — Frontend on S3
- Starter copied into `frontend/`; Swagger spec in `api/swagger/swagger.yaml`.
- Bucket created, Block Public Access off, public-read bucket policy, website hosting on. Site returns HTTP 200.
- Chat will show errors until Step 2 replaces the placeholder `apigClient.js` with the generated SDK.
