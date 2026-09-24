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
| DynamoDB table | `yelp-restaurants` | us-east-1 | on-demand; key `BusinessID` (S); 1,198 items; attrs BusinessID, Name, Address, Coordinates, NumberOfReviews, Rating, ZipCode, Cuisine, insertedAtTimestamp |
| SQS queue (Q1) | `dining-requests-q1` | us-east-1 | https://sqs.us-east-1.amazonaws.com/088850687383/dining-requests-q1 ; retention 1 day, visibility timeout 60s |
| Lambda | `LF1` (python3.12) | us-east-1 | Lex code hook; env `QUEUE_URL`; `lambdas/lf1-lex-hook/lambda_function.py` |
| IAM role | `lf1-lex-hook-role` | global | basic exec + `sqs:SendMessage` on Q1 |
| IAM role | `lex-hw1-bot-role` | global | Lex V2 bot service role (Polly/Comprehend) |
| Lex V2 bot | `DiningConcierge` (id `R0153OSV9Z`) | us-east-1 | en_US; version 1; alias `prod` = `R4JQFJKHQG`; `TestBotAlias` (DRAFT) also hooked to LF1; built by `scripts/setup_lex_bot.py` |
| API Gateway REST API | `ai-customer-service-api` (id `hlvxdz60d2`) | us-east-1 | stage `v1`; `POST /chatbot` → LF0 (Lambda proxy), `OPTIONS` mock for CORS, auth NONE |
| Lambda | `LF0` (python3.12) | us-east-1 | `lambdas/lf0-chat-api/lambda_function.py`; env `LEX_BOT_ID`, `LEX_BOT_ALIAS_ID`, `LEX_LOCALE_ID` |
| IAM role | `lf0-chat-api-role` | global | Lambda trust + `AWSLambdaBasicExecutionRole` + inline `call-lex` (`lex:RecognizeText` on the prod alias) |
| S3 bucket (static website, public read) | `cc-hw1-chatbot-frontend-088850687383` | us-east-1 | http://cc-hw1-chatbot-frontend-088850687383.s3-website-us-east-1.amazonaws.com — index/error doc `chat.html`; redeploy with `scripts/deploy_frontend.sh` |

## Step 1 — Frontend on S3
- Starter copied into `frontend/`; Swagger spec in `api/swagger/swagger.yaml`.
- Bucket created, Block Public Access off, public-read bucket policy, website hosting on. Site returns HTTP 200.
- Chat will show errors until Step 2 replaces the placeholder `apigClient.js` with the generated SDK.

## Step 2 — API Gateway + LF0
- LF0 created (Python 3.12, role `lf0-chat-api-role`), returns the boilerplate message in the swagger `BotResponse` shape.
- Swagger imported into API Gateway (`hlvxdz60d2`), `POST /chatbot` wired to LF0 with Lambda proxy integration; `OPTIONS` MOCK returns CORS headers; LF0 also returns CORS headers. Deployed to stage `v1`.
- Invoke URL: https://hlvxdz60d2.execute-api.us-east-1.amazonaws.com/v1/chatbot
- SDK generated with `aws apigateway get-sdk`; only `apigClient.js` replaced in the frontend (starter `lib/` kept, since `chat.html` references its file names).
- Auth is NONE (the starter builds the client with no credentials).
- Gotcha: in zsh, `$R:lambda` is parsed as a `:l` modifier — use `${R}:lambda`.

## Step 3 — Lex + LF1 + SQS
- Intents: `GreetingIntent`, `ThankYouIntent`, `DiningSuggestionsIntent` (slots in order: Location, Cuisine, NumberOfPeople, DiningTime, Email).
- Custom slot types: `CuisineType` (Chinese, Japanese, Italian, Mexican, Indian, Thai — these are the cuisines Step 5 must scrape) and `LocationType` (original-value resolution, so unknown cities reach LF1 and get a friendly rejection).
- LF1: dialog hook validates location (Manhattan/NYC aliases only), cuisine, party size 1–20, email; fulfillment hook sends `{location, cuisine, diningTime, numberOfPeople, email}` to Q1 and confirms.
- Tested via `aws lexv2-runtime recognize-text` with the PDF's example conversation (New Delhi rejected → Manhattan accepted → message in Q1). Test messages purged from Q1.
- Gotchas: the Lex locale must be `NotBuilt` before adding slot types; a fresh bot version isn't describable for a few seconds; boto3 `list_bots` isn't pageable. Bot setup: `scripts/setup_lex_bot.py` (venv in `.venv`, git-ignored).
- LF0 still returns the boilerplate — it calls Lex in Step 4.

## Step 4 — Lex integrated into LF0
- LF0 calls Lex `RecognizeText`; session id from the browser goes in `messages[0].unstructured.id`. Details and test results in `DEVELOPMENT_NOTES.md`.

## Step 5 — Yelp → DynamoDB
- `scripts/scrape_yelp.py` → `scripts/restaurants.json` (git-ignored); `scripts/load_dynamodb.py` → table. 1,198 items. Details in `DEVELOPMENT_NOTES.md`.
