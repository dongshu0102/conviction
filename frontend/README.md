# Conviction Web

Minimal Next.js frontend covering the "glanceable" core: Daily Brief,
portfolio valuation with allocation chart, watchlist with live prices.
Deliberately not a full rebuild of every API feature — research reports,
risk deep-dives, and alert management stay API/MCP-only for now (see the
product decision this was built from).

**Honest limitation**: written and manually reviewed for syntax, but
never actually run through `npm install`/`next build` — this sandbox has
no network access. The real first test is yours, same as the MCP server
earlier this session.

## Auth model — read this before deploying

There's no password yet. `/login` collects a name and calls the existing
`POST /api-keys` bootstrap endpoint, storing the returned key in
`localStorage`. This is consistent with the backend's own documented
MVP limitation (unauthenticated `user_id`), not a new gap — but it's
worth being clear-eyed that anyone with access to the browser has full
access to whatever account that key belongs to.

## 1. Local development

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000`. By default it points at the deployed
production API (`p8xpcshdn9.us-east-1.awsapprunner.com`) — set
`NEXT_PUBLIC_API_URL=http://localhost:8000` in a `.env.local` file if you
want it hitting your local backend instead.

**If `npm install` or `npm run dev` fails**, paste the exact error —
given this was never run, that's the most likely place for a real
problem to surface.

## 2. Deploy the CORS fix to the backend first

The frontend calls the API from a different origin (browser), which
requires CORS — already added to `src/api/main.py` in this same update.
Sync, commit, and push that change through the existing flow so CI/CD
deploys it:

```bash
git add src/api/main.py
git commit -m "Enable CORS for the web frontend"
git push
```

## 3. Build and push the frontend image (same pattern as the backend)

```bash
cd frontend
aws ecr create-repository --profile fininsight-deploy --repository-name fininsight-web --region us-east-1

aws ecr get-login-password --profile fininsight-deploy --region us-east-1 | \
  docker login --username AWS --password-stdin 512768499510.dkr.ecr.us-east-1.amazonaws.com

docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://p8xpcshdn9.us-east-1.awsapprunner.com \
  -t 512768499510.dkr.ecr.us-east-1.amazonaws.com/fininsight-web:latest .

docker push 512768499510.dkr.ecr.us-east-1.amazonaws.com/fininsight-web:latest
```

## 4. Create the App Runner service

Simpler than the backend's — this service only makes outbound HTTPS
calls to the public API, so **no VPC connector is needed** (avoiding
that whole class of networking issue from the backend deployment):

```bash
aws apprunner create-service --profile fininsight-deploy \
  --service-name fininsight-web \
  --source-configuration '{
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::512768499510:role/AppRunnerECRAccessRole"
    },
    "ImageRepository": {
      "ImageIdentifier": "512768499510.dkr.ecr.us-east-1.amazonaws.com/fininsight-web:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": { "Port": "8000" }
    },
    "AutoDeploymentsEnabled": false
  }'
```

Reuses `AppRunnerECRAccessRole` from the backend — same role, same
permission (pull from ECR), nothing new to create there.

## 5. Wait, then get the URL

```bash
sleep 90
aws apprunner describe-service --profile fininsight-deploy \
  --service-arn <ARN_FROM_STEP_4_RESPONSE> \
  --query 'Service.{Status:Status,Url:ServiceUrl}'
```

Once `Status` shows `RUNNING`, visit `https://<Url>` — that's the real
end-to-end test.

## What's deliberately not built yet

- Real authentication (password, sessions) — same MVP gap as the API itself
- Research report browsing, risk deep-dives, alert management — API/MCP-only for now
- Auto-deploy CI/CD for this service — currently manual, same as the backend's Stage 4-6 originally was before we wired GitHub Actions; worth doing the same OIDC extension here once this is confirmed working
