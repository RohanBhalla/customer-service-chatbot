#!/usr/bin/env bash
# Sync frontend/ to the S3 website bucket.
set -euo pipefail
BUCKET="${FRONTEND_BUCKET:-cc-hw1-chatbot-frontend-088850687383}"
cd "$(dirname "$0")/.."
aws s3 sync frontend/ "s3://$BUCKET/" --exclude "README.md" --exclude ".gitkeep" --delete --only-show-errors
echo "http://$BUCKET.s3-website-us-east-1.amazonaws.com"
