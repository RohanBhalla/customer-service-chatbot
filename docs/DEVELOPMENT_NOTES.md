# Development Notes

A running log of what was built, the commands used, issues hit and how they were fixed.
Newest steps go at the bottom of the step log. See also:
[`requirements.md`](requirements.md) (checklist) and [`progress.md`](progress.md) (resource table).

- **AWS account:** `088850687383` · **Region:** `us-east-1` · **CLI user:** `cc-hw1-dev`
- **GitHub:** https://github.com/RohanBhalla/customer-service-chatbot (private)
- **Live site:** http://cc-hw1-chatbot-frontend-088850687383.s3-website-us-east-1.amazonaws.com
- **API:** `POST https://hlvxdz60d2.execute-api.us-east-1.amazonaws.com/v1/chatbot`

## Status at a glance

| Step | Topic | Points | Status |
|------|-------|--------|--------|
| 1 | Frontend on S3 | 10 | Done |
| 2 | API Gateway + LF0 boilerplate | 15 | Done |
| 3 | Lex bot + LF1 + SQS | 20 | Done |
| 4 | Lex integrated into chat API | 10 | Done — browser check by user pending |
| 5 | Yelp scrape → DynamoDB | 15 | Done (1,198 restaurants) |
| 6 | LF2 + SES + EventBridge | 15 | In progress — LF2 + schedule live; waiting on SES verification for a real send |
| 7 | OpenSearch | 15 | Not started (do last; costs money) |
| EC | Conversation state | 10 | Not started |

## Architecture as built so far

```
Browser (S3 site) ──POST /chatbot──▶ API Gateway (v1) ──▶ LF0 ──RecognizeText──▶ Lex bot "DiningConcierge"
                                                                                      │ code hook
                                                                                      ▼
                                                                                     LF1 ──SendMessage──▶ SQS Q1 (dining-requests-q1)
```
DynamoDB `yelp-restaurants` (1,198 restaurants) is loaded but nothing reads it yet. LF2 + the 1-minute schedule exist (using a DynamoDB fallback for IDs). Not yet built: OpenSearch, extra-credit state table.

## Design decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Scope of location | Manhattan only (+ NYC aliases) | Assignment scrapes Manhattan; PDF example rejects New Delhi |
| Cuisines | Chinese, Japanese, Italian, Mexican, Indian, Thai | ≥5 required; Step 5 must scrape exactly these |
| Slots | Location, Cuisine, NumberOfPeople, DiningTime, Email | The 5 required by the PDF (its example also asks for a date/phone; the requirement list says email) |
| API auth | None | Starter builds the client with no credentials; SigV4 would need Cognito. Anyone with the URL can call it |
| Lambda integration | Lambda proxy | LF0 owns the response, including CORS headers |
| Session id | Random id stored in browser `localStorage`, sent in `messages[0].unstructured.id` | Swagger has no session field; Lex needs a stable id; reused for the extra credit |
| One IAM role per Lambda | `lf0-chat-api-role`, `lf1-lex-hook-role`, `lf2-queue-worker-role` | Least privilege per function |
| OpenSearch | Built last, deleted after testing | Billed hourly, not serverless |
| Repo visibility | Private | Coursework |

---

## Step log

### Step 0 — Repo and AWS account setup
**Done**
- Read the assignment PDF; scaffolded `customer-service-chatbot/` (`frontend/`, `api/`, `lambdas/lf0..lf2`, `scripts/`, `docs/`), `.gitignore`, `.env.example`, README, requirements checklist.
- Created a private GitHub repo and pushed.
- AWS: the old default CLI user `cloud-class-lab-user` was a limited assignment user. User created a new IAM user `cc-hw1-dev` with admin-style access in their own account, enabled root MFA, a budget alert and billing alerts, then overwrote the default CLI profile with the new keys.

**Issues**
- *Every AWS call returned AccessDenied* (`s3:CreateBucket`, all `list-*`) with the old user. Only `sts:GetCallerIdentity` worked. → Needed a properly permissioned user; nothing was worked around.
- Verifying the new user: my first permission-check loop failed with `Found invalid choice 's3 ls'` because a quoted command string was passed as one argument in zsh. → Wrapped the call in a shell function (`run() { aws "$@"; }`).

**Verify:** `aws sts get-caller-identity` shows `user/cc-hw1-dev`; all list calls return empty results.

### Step 1 — Frontend on S3
**Done**
- Cloned https://github.com/aditya491929/cloud-hw1-starter into `frontend/` (Swagger copied to `api/swagger/swagger.yaml`).
- Created the bucket and enabled website hosting (`scripts/deploy_frontend.sh` redeploys):
```
aws s3api create-bucket --bucket cc-hw1-chatbot-frontend-088850687383 --region us-east-1
aws s3api put-public-access-block --bucket <b> --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false
aws s3api put-bucket-policy --bucket <b> --policy '{... "Action":"s3:GetObject","Principal":"*","Resource":"arn:aws:s3:::<b>/*" ...}'
aws s3 website s3://<b>/ --index-document chat.html --error-document chat.html
aws s3 sync frontend/ s3://<b>/ --exclude README.md --exclude .gitkeep --delete
```

**Issues**
- *Command hung for 120s.* A stray `cat > /tmp/dummy` line I left in the script waited on stdin. → Killed it, confirmed the bucket and public-access setting had applied (policy hadn't), reran the remaining steps.

**Verify:** site returns HTTP 200, title "Chatbot Concierge".
**Notes:** the site is HTTP only (S3 website endpoints don't do HTTPS) — fine for this assignment. Bucket is public by design; only static files.

### Step 2 — API Gateway + LF0 boilerplate
**Done**
- IAM role `lf0-chat-api-role` (Lambda trust + `AWSLambdaBasicExecutionRole`).
- LF0 (Python 3.12) returns "I'm still under development. Please come back later." in the Swagger `BotResponse` shape, with CORS headers.
- Imported `swagger.yaml` (`aws apigateway import-rest-api`), then manually added: `POST /chatbot` → LF0 (`AWS_PROXY`), `OPTIONS` MOCK method for CORS preflight, Lambda invoke permission for API Gateway, deployment to stage `v1`.
- Generated the JS SDK (`aws apigateway get-sdk --sdk-type javascript`) and replaced **only** `frontend/assets/js/sdk/apigClient.js`.

**Issues**
1. *`put-integration` failed: "AWS ARN for integration must contain path or action".* In zsh, `$R:lambda` is parsed as `$R` plus the `:l` (lowercase) modifier, mangling the ARN. → Use `${R}:lambda`.
2. *`create-deployment` failed: "No integration defined for method"* — a consequence of #1.
3. *OPTIONS CORS headers got wiped.* A diagnostic call to `put-integration-response` with no `--response-parameters` reset them to null. → Reapplied from a JSON file (`--response-parameters file://cors.json`) and redeployed. Lesson: never run put-* as a "check".
4. *Generated SDK `lib/` differs from the starter's* (newer CryptoJS layout; `chat.html` references the starter's file names like `hmac-sha256.js`). → Kept the starter `lib/`, replaced only `apigClient.js` (what the starter README says).

**Verify:** `curl -X OPTIONS` returns 200 with `access-control-allow-*`; `curl -X POST` returns the boilerplate JSON.

### Step 3 — Lex bot, LF1, SQS
**Done**
- SQS queue `dining-requests-q1` (retention 1 day, visibility timeout 60 s).
- LF1 (Python 3.12, env `QUEUE_URL`, role `lf1-lex-hook-role` with `sqs:SendMessage` on Q1): handles all three intents.
  - Dialog hook validates Location (Manhattan + NYC aliases), Cuisine (the 6), NumberOfPeople (1–20), Email (regex), re-asking with `ElicitSlot`.
  - Fulfillment hook sends `{location, cuisine, diningTime, numberOfPeople, email}` to Q1 and confirms.
- Lex V2 bot `DiningConcierge` (id `R0153OSV9Z`, locale `en_US`, NLU threshold 0.4), service role `lex-hw1-bot-role`. Custom slot types `CuisineType` (TopResolution) and `LocationType` (OriginalValue, so unknown cities such as "New Delhi" reach LF1 and get the friendly rejection). Version 1 published; alias `prod` = `R4JQFJKHQG`; `TestBotAlias` (DRAFT) also hooked to LF1 so the console Test pane runs the code hook. Lambda permission grants `lexv2.amazonaws.com` invoke on LF1 for `bot-alias/R0153OSV9Z/*`.
- Bot built by `scripts/setup_lex_bot.py` (uses the git-ignored `.venv` with boto3).

**Issues**
1. *boto3 not installed locally.* → `python3 -m venv .venv && .venv/bin/pip install boto3 requests` (`scripts/requirements.txt`).
2. *`OperationNotPageableError: list_bots`.* → Manual `nextToken` loop.
3. *`CreateSlotType ... BotLocale is in Creating state`.* → Added a wait for locale status `NotBuilt`. The partial bot from that run was deleted (`delete-bot --skip-resource-in-use-check`) and the script rerun.
4. *`DescribeBotVersion ResourceNotFoundException` right after `create_bot_version`* (eventual consistency). → Treat "not found" as "not visible yet" in the wait loop. This run had already built the bot; the alias, code hook attachment and Lambda permission were finished **by hand** with the CLI. The patched script has not been run start to finish.
5. *Test messages in Q1.* Testing pushed fake requests (including `test@example.com`); purged with `aws sqs purge-queue` so LF2 won't email stale requests later. Purge after every test that reaches fulfillment.
6. *Email validation.* For "not-an-email", Lex's built-in `AMAZON.EmailAddress` rejected it and re-prompted before LF1 saw it; LF1's regex is a backstop.

**Verify**
- 7 direct LF1 invocations with hand-built Lex events (greeting, thanks, New Delhi, valid, bad email, party of 99, fulfillment).
- PDF example conversation via `aws lexv2-runtime recognize-text`; correct JSON in Q1.

### Step 4 — Lex integrated into the chat API
**Done**
- LF0 rewritten: extracts `messages[0].unstructured.text`, calls `lexv2-runtime.recognize_text` (bot `R0153OSV9Z`, alias `R4JQFJKHQG`, locale `en_US`), returns Lex's message contents as `BotResponse.messages`. Config via env vars `LEX_BOT_ID`, `LEX_BOT_ALIAS_ID`, `LEX_LOCALE_ID`. Returns Swagger-shaped `Error` 400 for bad input and 500 if Lex fails; falls back to a generic message if Lex returns none.
- `lf0-chat-api-role` got inline policy `call-lex` (`lex:RecognizeText` on the `prod` alias ARN only).
- Session id: `chat.js` now creates `web-<time>-<random>` once, stores it in `localStorage`, and sends it as `messages[0].unstructured.id`. LF0 sanitises it to Lex's allowed characters (`[0-9a-zA-Z._:-]`, ≤100) and falls back to a random id if missing.
- Frontend redeployed.

**Issues:** none new. (IAM changes can take a few seconds to propagate; the first API test passed without retries.)

**Verify**
- Full multi-turn conversation through the real API URL with one session id: greeting → New Delhi rejected → Manhattan → Italian → 4 → 8pm → email → fulfilled → "thanks". Message correct in Q1, then purged.
- `{}` body → 400 "Invalid request body"; blank text → 400 "Message text is empty".
- **Not yet verified in a real browser** (CORS from the S3 origin was verified with curl preflight in Step 2). User to open the site and run the conversation.

### Step 5 — Yelp scrape → DynamoDB
**Done**
- Tested the Yelp Fusion key first with one search (HTTP 200). Response headers showed **300 calls/day**, resetting at 00:00 UTC — so results are cached locally and re-runs are avoided.
- DynamoDB table `yelp-restaurants`: on-demand billing, hash key `BusinessID` (S).
- `scripts/scrape_yelp.py`: for each of the 6 cuisines, searches `term="<cuisine> restaurants"` + Yelp `categories` alias (`indpak` for Indian), starting with "Manhattan, NY" (4 pages × 50) and falling back to 16 neighborhood queries until 200 are collected. Keeps only Manhattan zips (100xx–102xx) with coordinates. Dedupes on BusinessID across all cuisines (a restaurant is kept under the first cuisine that found it). Guard stops at 250 API calls. Writes `scripts/restaurants.json` (git-ignored).
- `scripts/load_dynamodb.py`: reads the JSON (floats parsed as `Decimal`, since DynamoDB has no float type), stamps `insertedAtTimestamp` (UTC ISO-8601), writes with `batch_writer`. Re-runnable (keyed by BusinessID).
- Item shape: `BusinessID, Name, Address, Coordinates{latitude,longitude}, NumberOfReviews, Rating, ZipCode, Cuisine, insertedAtTimestamp`. `Cuisine` is extra (not in the PDF list) — needed to load OpenSearch in Step 7.

**Issues**
1. *`create-table` failed with `zsh: no matches found: TableDescription.[TableName,TableStatus]`.* zsh treats unquoted `[...]` as a glob. The command never ran. → Quote JMESPath queries: `--query 'TableDescription.[TableName,TableStatus]'`.
2. *Two duplicate listings.* Validation found 2 restaurants with the same name + address under different Yelp ids (Bawarchi Indian Cuisine, 1546 Madison Ave; Aamber Indian Vegan, 2636 Broadway). The PDF says no duplicates, so they were dropped from the cache and the scraper now also dedupes on (name, address). Result: Indian = 198, others 200.

**Verify**
- Scrape: 6 × 200 = 1,200 in 55 API calls (quota used ≈ 56 of 300 that day), all fields present, coordinates inside Manhattan, ids unique.
- Live DynamoDB scan: 1,198 items; per cuisine 200/200/200/200/198/200; 0 items missing `insertedAtTimestamp`.

**Notes:** the key lives only in `.env` (git-ignored, confirmed with `git check-ignore`); scripts read it at run time and never print it.

### Step 6 — LF2 queue worker, SES, EventBridge (in progress)
**Done**
- SES (sandbox: 200 emails/day, 1/s): started verification of the sender address from `.env` (`aws sesv2 create-email-identity`). A verification email is sent to it; the link must be clicked before sending works. In sandbox the recipient must be verified too (using the same address as sender and recipient is simplest).
- LF2 (Python 3.12, 60 s timeout, role `lf2-queue-worker-role`): each run receives up to 10 messages from Q1 (2 s long-poll), and for each one gets random restaurant IDs for the cuisine, fetches details from DynamoDB (`BatchGetItem`), formats and sends the email through SES, and only then deletes the message. On failure the message is left to reappear after the 60 s visibility timeout; after 3 receives it is dropped so one bad message can't loop for a day.
- ID lookup has two paths: OpenSearch `_search` with a `random_score` function query (used when `OPENSEARCH_ENDPOINT` is set; uses only `urllib`, so no packaging of extra libraries) and a DynamoDB scan filtered by cuisine (temporary fallback until Step 7).
- Email text follows the PDF ("Hello! Here are my Japanese restaurant suggestions for 2 people, at 7:00 PM: 1. Name, located at address … Enjoy your meal!") plus rating/review count. No date is collected by the bot, so the email says "at <time>" rather than "today at".
- EventBridge rule `lf2-every-minute` (`rate(1 minute)`) → LF2, with a Lambda permission for `events.amazonaws.com` scoped to that rule. (Chose classic EventBridge rules over Scheduler: no extra IAM role needed.)
- `lf2-queue-worker-role` least-privilege policy: `sqs:ReceiveMessage/DeleteMessage/GetQueueAttributes` on Q1, `dynamodb:BatchGetItem/GetItem/Scan` on `yelp-restaurants`, `ses:SendEmail` on the sender identity only.

**Issues**
1. *JMESPath `not()` doesn't exist* in an `aws sesv2 get-account --query` I wrote (read-only; reran with `ProductionAccessEnabled`).
2. *Rating showed as `4` instead of `4.0`* in local output → format with `:.1f`.
3. *No log group after creating the rule.* LF2 had not yet been invoked by the schedule (rules can take a minute or two to start). Confirmed the rule/target/permission were correct, invoked LF2 manually once (queue empty, safe), then saw scheduled runs at 21:38:16 and 21:39:16 UTC — every minute.

**Verify so far**
- Local test with real AWS credentials: lookup for `japanese`/`indian`/`thai` returns correct-cuisine restaurants; details fetched; email text formatted correctly (singular/plural, 12-hour time).
- Scheduled runs succeed with `processed=0 failed=0 received=0` on the empty queue.
- **Not yet verified:** an actual SES send and the full chat → email flow (blocked on SES verification).

**Cost note:** the rule invokes LF2 ~1,440 times/day (free-tier territory, but it never stops). Disable it when not testing: `aws events disable-rule --name lf2-every-minute` (re-enable with `enable-rule`).

---

## Known limitations / things to revisit
- API has no auth; anyone with the URL can invoke Lex through it (each call costs a tiny amount).
- Starter `chat.js` inserts message text into the page as raw HTML (user text and bot text are not escaped).
- `scripts/setup_lex_bot.py` was patched after failures and hasn't been run cleanly from scratch.
- Lex version 1 is what the `prod` alias serves. **Changes to the DRAFT bot are not live until a new version is created and the alias is updated** (or LF0 is pointed at `TestBotAlias`/DRAFT while iterating).
- Diagnostic/test calls that reach fulfillment put real messages in Q1.

## Useful commands
```bash
# who am I / region
aws sts get-caller-identity; aws configure get region

# redeploy frontend
scripts/deploy_frontend.sh

# redeploy a Lambda (example: LF0)
(cd lambdas/lf0-chat-api && zip -q /tmp/lf0.zip lambda_function.py)
aws lambda update-function-code --function-name LF0 --zip-file fileb:///tmp/lf0.zip

# redeploy the API after changes
aws apigateway create-deployment --rest-api-id hlvxdz60d2 --stage-name v1

# talk to the bot directly
aws lexv2-runtime recognize-text --bot-id R0153OSV9Z --bot-alias-id R4JQFJKHQG \
  --locale-id en_US --session-id test-1 --text "Hello"

# peek at / clear the queue
aws sqs receive-message --queue-url https://sqs.us-east-1.amazonaws.com/088850687383/dining-requests-q1 --visibility-timeout 0
aws sqs purge-queue --queue-url https://sqs.us-east-1.amazonaws.com/088850687383/dining-requests-q1

# Lambda logs
aws logs tail /aws/lambda/LF0 --since 10m
```
**zsh gotcha:** write `${VAR}:text`, not `$VAR:text` (`:l`, `:u`, `:t` … are modifiers).

## Cost and cleanup
- Cheap/idle: S3, API Gateway, Lambda, SQS, Lex (per request), DynamoDB on-demand.
- **OpenSearch is billed hourly** — create it last and delete it as soon as testing/grading demo is done.
- Teardown order when finished: OpenSearch domain → EventBridge schedule → Lambdas → API Gateway → Lex bot → SQS → DynamoDB tables → S3 bucket (empty first) → IAM roles → (optional) deactivate `cc-hw1-dev` access keys.
