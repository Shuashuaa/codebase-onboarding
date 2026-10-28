# atlas.json schema

Every top-level key is optional except `meta` and `nodes`. Empty sections are hidden in the viewer, so omit rather than pad.

## Contents
- meta
- nodes / edges (service map)
- flows
- apis
- auth
- data
- code
- run (setup, environments, config, pipeline)
- operate
- context (glossary, owners, decisions, hotspots)
- tour, first_tasks, gaps

---

## meta
```json
{
  "name": "ai-skill",
  "summary": "One paragraph: what the system does and for whom.",
  "repo": "https://github.com/org/ai-skill",
  "root": "/abs/path/at/scan/time",
  "generated_at": "2026-10-28T08:00:00Z",
  "stack": ["Next.js", "AWS Cognito", "API Gateway", "Lambda", "DynamoDB"],
  "scanner_version": "1"
}
```
`root` enables "open in editor" links in the viewer (vscode://file/...). Omit it if the atlas will be shared outside the dev's machine.

## nodes
```json
{
  "id": "orders-lambda",
  "label": "Orders API",
  "kind": "function",
  "layer": "compute",
  "provider": "aws",
  "tech": "Lambda · Node 20",
  "group": "orders",
  "source": ["services/orders/handler.ts", "serverless.yml"],
  "confidence": "declared",
  "notes": "Handles CRUD for orders. Cold start ~800ms."
}
```

`layer` decides the map column, left to right:

| layer | examples |
|---|---|
| `client` | web app, mobile app, CLI, browser extension |
| `identity` | Cognito, Entra ID, Auth0, Okta, Firebase Auth, Keycloak, NextAuth, custom JWT issuer |
| `edge` | API Gateway, ALB, CloudFront, Azure APIM, Front Door, nginx, ingress, GraphQL gateway |
| `compute` | Lambda, Azure Functions, Cloud Run, ECS/K8s service, Express/Django app, workers |
| `messaging` | SQS, SNS, EventBridge, Kafka, Service Bus, Pub/Sub, Step Functions, cron schedules |
| `data` | DynamoDB, RDS/Postgres, Cosmos DB, Mongo, Redis, S3/Blob, search indexes |
| `external` | Stripe, OpenAI/Anthropic, SendGrid, third-party APIs, other teams' services |
| `ops` | CloudWatch, App Insights, Datadog, Sentry, secrets managers, feature flags |

`kind`: free text but prefer `app`, `idp`, `gateway`, `cdn`, `function`, `service`, `worker`, `queue`, `topic`, `bus`, `schedule`, `workflow`, `table`, `database`, `cache`, `bucket`, `index`, `api`, `secret`, `monitor`.

`provider`: `aws`, `azure`, `gcp`, `self`, `saas`, or vendor name.

`confidence`: `declared` | `inferred`.

## edges
```json
{ "from": "web-app", "to": "cognito", "kind": "authenticates", "label": "SRP login → JWT", "confidence": "declared", "source": ["web/src/lib/auth.ts"] }
```
`kind`: `calls`, `authenticates`, `authorizes`, `routes`, `invokes`, `reads`, `writes`, `reads-writes`, `publishes`, `subscribes`, `triggers`, `depends-on`.

## flows
Ordered steps between node ids. Rendered as sequence diagrams.
```json
{
  "id": "login",
  "name": "User signs in",
  "trigger": "User submits /login form",
  "steps": [
    { "from": "web-app", "to": "cognito", "action": "InitiateAuth (SRP)", "detail": "Amplify Auth.signIn" },
    { "from": "cognito", "to": "web-app", "action": "id + access tokens", "detail": "Stored in memory, refresh in cookie" }
  ],
  "notes": "MFA optional per user pool config."
}
```

## apis
```json
{ "method": "POST", "path": "/orders", "handler": "orders-lambda", "auth": "Cognito JWT (orders:write)", "description": "Create order", "source": "serverless.yml" }
```
`handler` may be a node id or a file path.

## auth
```json
{
  "summary": "Users sign in via Cognito hosted UI; API Gateway verifies the JWT with a Cognito authorizer.",
  "providers": ["cognito"],
  "token": "JWT (id + access), 1h expiry, refresh 30d",
  "verified_at": ["api-gateway"],
  "roles": [ { "name": "admin", "grants": "All /admin routes", "source": "cognito group 'admins'" } ],
  "service_identities": [ { "who": "orders-lambda", "can": "dynamodb:PutItem on orders-table", "source": "serverless.yml iamRoleStatements" } ]
}
```

## data
```json
{
  "entities": [
    {
      "name": "Order",
      "store": "orders-table",
      "keys": "PK=USER#<id>, SK=ORDER#<ts>",
      "fields": ["status", "total", "items[]"],
      "owner": "orders-lambda",
      "access_patterns": ["List orders for user (query PK)", "Get order by id (GSI1)"]
    }
  ],
  "relations": [ { "from": "User", "to": "Order", "kind": "1-n" } ]
}
```

## code
```json
{
  "layout": "Monorepo: web/ (Next.js), services/ (one folder per Lambda), infra/ (Terraform)",
  "entry_points": [ { "path": "web/src/app/page.tsx", "purpose": "Landing page" } ],
  "modules": [ { "path": "services/orders", "purpose": "Orders domain", "depends_on": ["packages/shared"] } ]
}
```

## run
```json
{
  "prerequisites": ["Node 20", "AWS CLI with dev profile"],
  "setup": [ { "step": "Install deps", "command": "pnpm install", "notes": "", "verified": true } ],
  "environments": [ { "name": "dev", "url": "https://dev.example.com", "deploy": "auto on merge to main", "notes": "" } ],
  "config": [ { "key": "NEXT_PUBLIC_USER_POOL_ID", "where": "web/.env.example", "secret": false, "purpose": "Cognito pool" } ],
  "pipeline": [ { "stage": "test", "tool": "GitHub Actions", "does": "lint + unit tests", "source": ".github/workflows/ci.yml" } ]
}
```

`verified` is set only in deep mode, when the step was actually run and worked. Leave it out otherwise; the viewer labels the list as taken from repo files.

## operate
```json
{
  "logs": [ { "what": "Lambda logs", "where": "CloudWatch /aws/lambda/orders-*" } ],
  "metrics": [ { "what": "API latency", "where": "Datadog dashboard 'Orders'" } ],
  "alarms": [ { "name": "orders-5xx", "condition": ">1% 5xx over 5m", "notifies": "#oncall" } ],
  "runbooks": [ { "symptom": "Login loops", "check": "Cognito app client callback URLs", "fix": "Add env URL to allowed callbacks" } ]
}
```

## context
```json
{
  "glossary": [ { "term": "Skill", "meaning": "A packaged prompt + tools unit sold to tenants" } ],
  "owners": [ { "area": "services/billing", "owner": "@payments-team", "source": "CODEOWNERS" } ],
  "decisions": [ { "title": "Use DynamoDB single-table", "date": "2024-03", "summary": "...", "source": "docs/adr/0003.md" } ],
  "hotspots": [ { "path": "services/orders/handler.ts", "reason": "42 commits in 6 months, 9 TODOs" } ]
}
```

## tour, first_tasks, gaps
```json
"tour": [ { "title": "Start at the front door", "body": "Markdown-free short text.", "focus": ["web-app", "web/src/app/layout.tsx"] } ],
"first_tasks": [ { "title": "Run the app locally", "why": "Exercises setup docs", "pointer": "run.setup" } ],
"gaps": [ "Who owns the reporting Lambda?", "Prod URL not found in repo" ]
```
`focus` entries that match a node id highlight that node on the map; others render as file paths.
