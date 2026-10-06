# Requirements & Step Plan

Points total 110 (100 + 10 extra credit). Steps are ordered by dependency, not by the PDF's
numbering: OpenSearch is built **last** among the AWS resources because it is billed hourly
(not serverless) — the PDF explicitly warns about this.

Legend: `[ ]` todo · `[x]` done and reviewed

---

## Step 1 — Frontend on S3 (10 pts) — PDF §1
- [x] Clone/adapt starter: https://github.com/aditya491929/cloud-hw1-starter into `frontend/`
- [x] Repurpose it to talk to our chatbot API
- [x] Create S3 bucket with static website hosting enabled
- [x] Upload frontend; site loads from the S3 website endpoint

## Step 2 — API Gateway + LF0 boilerplate (15 pts) — PDF §2
- [x] Get Swagger spec: https://github.com/aditya491929/cloud-hw1-starter/blob/master/swagger/swagger.yaml (visualize at editor.swagger.io)
- [x] Create LF0 Lambda implementing the spec's request/response model
- [x] LF0 returns boilerplate: "I'm still under development. Please come back later."
- [x] Import Swagger into API Gateway; wire methods to LF0
- [x] Enable CORS on API methods
- [x] Generate the API Gateway JavaScript SDK and use it in the frontend
- [x] End-to-end: frontend → API → LF0 → reply shown in chat

## Step 3 — Lex bot + LF1 code hook + SQS (20 pts) — PDF §3
- [x] Create SQS queue **Q1**
- [x] Create Lex bot (note: Lex V2 is the current console)
- [x] Intents: `GreetingIntent`, `ThankYouIntent`, `DiningSuggestionsIntent`
- [x] Create LF1 and attach as Lex code hook
- [x] GreetingIntent → "Hi there, how can I help?"; ThankYouIntent → "You're welcome."
- [x] DiningSuggestionsIntent collects: Location, Cuisine, Dining Time, Number of people, Email
- [x] Validate slots (e.g. reject unsupported locations — only Manhattan; validate cuisine)
- [x] Push collected info to Q1
- [x] Confirm to user the request was received and they'll be emailed
- [x] Train and test (built via script; tested with the Lex runtime API; console test pane also available on TestBotAlias)

## Step 4 — Integrate Lex into the chat API (10 pts) — PDF §4
- [x] LF0 uses the AWS SDK (boto3) to call Lex: extract text from API request → send to Lex → wait → return Lex response as API response
- [x] End-to-end test through the API (curl, multi-turn); browser check on the live site by the user pending

## Step 5 — Yelp scrape → DynamoDB (15 pts) — PDF §5
- [x] Yelp API key
- [x] 6 cuisines, ~200 restaurants each, 1,198 total, Manhattan (Indian has 198 after removing 2 duplicate listings)
- [x] No duplicates (dedupe on Business ID)
- [x] DynamoDB table `yelp-restaurants`
- [x] Store: Business ID, Name, Address, Coordinates, Number of Reviews, Rating, Zip Code
- [x] Each item has `insertedAtTimestamp`

## Step 6 — Suggestions module LF2 + SES + EventBridge (15 pts) — PDF §7
- [x] Create LF2 as queue worker: pull message from Q1
- [x] Get random restaurant recommendation(s) for the cuisine from OpenSearch (IDs)
- [x] Look up name/address/etc. in DynamoDB `yelp-restaurants`
- [x] Format and email via SES (verified sender; end-to-end chat → email received) to the address in the SQS message (verify sender/recipient in SES sandbox)
- [x] EventBridge Scheduler / CloudWatch Events rule invoking LF2 every 1 minute
- [x] Filter by cuisine only (no neighborhood filtering needed)

## Step 7 — OpenSearch (15 pts) — PDF §6 — **do last, delete when done**
- [x] Create OpenSearch domain — cost-saving settings: Standard create, Dev/Test, no standby / 1 AZ, 1 data node `t3.small.search` or `t3.medium.search`, fine-grained access control with a master user
- [x] Index `restaurants`, type `Restaurant`
- [x] Store only `RestaurantID` and `Cuisine` per restaurant
- [x] Load data from the Step 5 scrape
- [x] Test LF2 end-to-end (confirmed via logs + email) — **domain still running, delete pending user decision**

## Extra Credit — Conversation state (10 pts)
- [x] DynamoDB table (e.g. `user-search-state`) storing each user's last location + cuisine (and the last recommendation)
- [x] When a returning user requests the same location + cuisine as their previous search, ask whether they want the same recommendation as last time
- [x] Needs a stable user/session id from the frontend through LF0 → Lex → LF1

---

## Final deliverables checklist
- [x] Everything works end to end (chat → email received), including the extra-credit reuse flow
- [x] Code committed to GitHub
- [ ] OpenSearch domain shut down after grading demo/testing

## Notes
- The PDF's example interaction asks for a *phone number* but the requirements say **Email** — we collect email (SES).
- Sample email format: "Hello! Here are my Japanese restaurant suggestions for 2 people, for today at 7pm: 1. ..., 2. ..., 3. ... Enjoy your meal!"
