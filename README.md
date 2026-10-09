# Customer Service Chatbot — Dining Concierge

Cloud Computing and Big Data, Fall 2026 — Homework Assignment 1.

A serverless, microservice-driven Dining Concierge chatbot. Users chat through a web
frontend; an Amazon Lex bot collects dining preferences; a decoupled queue worker
emails restaurant suggestions (from Yelp data in DynamoDB + OpenSearch) via SES.

**Live chatbot:** http://cc-hw1-chatbot-frontend-088850687383.s3-website-us-east-1.amazonaws.com

Full assignment: [`docs/CC_Fall2026_Assignment1.pdf`](docs/CC_Fall2026_Assignment1.pdf)
Requirements checklist: [`docs/requirements.md`](docs/requirements.md)
Progress log: [`docs/progress.md`](docs/progress.md)
Development notes (issues, fixes, commands): [`docs/DEVELOPMENT_NOTES.md`](docs/DEVELOPMENT_NOTES.md)

## Architecture

```
User → S3 (frontend) → API Gateway → LF0 → Lex → LF1 (code hook) → SQS (Q1)
                                                                      ↓ poll (EventBridge, every 1 min)
                                         SES ← LF2 (queue worker) → OpenSearch (IDs by cuisine)
                                                              └──→ DynamoDB (name, address, ...)
Yelp API → DynamoDB "yelp-restaurants" + OpenSearch "restaurants"
Extra credit: DynamoDB state table remembers each user's last location + cuisine
```

## Repo layout

| Path | Purpose |
|------|---------|
| `frontend/` | Chat UI (from the starter repo), hosted on S3 |
| `api/` | Swagger spec + generated API Gateway SDK |
| `lambda-functions/lf0-chat-api/` | LF0 — API Gateway handler, calls Lex |
| `lambda-functions/lf1-lex-hook/` | LF1 — Lex dialog/fulfillment code hook, pushes to SQS |
| `lambda-functions/lf2-queue-worker/` | LF2 — pulls SQS, queries OpenSearch + DynamoDB, sends SES email |
| `other-scripts/` | Yelp scraper, DynamoDB/OpenSearch loaders |
| `docs/` | Assignment PDF, requirements, progress log |

## Working approach

We go one step at a time (see `docs/requirements.md`): confirm the plan, explain the
AWS concepts, build, then review before moving on. Secrets live in `.env` (git-ignored);
see `.env.example`.
