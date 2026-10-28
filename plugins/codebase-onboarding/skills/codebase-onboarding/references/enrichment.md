# Enrichment hints by stack

Read only the sections matching the detected stack. Each lists where hidden edges usually live — the connections config files don't declare.

## Contents
- Universal techniques
- AWS
- Azure
- GCP
- Containers / Kubernetes
- Frontend frameworks
- Backend frameworks
- Auth providers

---

## Universal techniques

- **Env var → resource.** Most compute→data edges hide in env vars: `TABLE_NAME`, `QUEUE_URL`, `BUCKET`, `DATABASE_URL`, `*_ENDPOINT`. Grep code for the env var name to find which handler uses it, then add the edge.
- **SDK client construction.** Grep for client constructors (`new DynamoDBClient`, `boto3.client(`, `BlobServiceClient`, `new PrismaClient`, `createClient(`). The file that builds a client is the node that talks to that resource.
- **Outbound HTTP.** Grep `fetch(`, `axios`, `requests.`, `HttpClient` with base URLs → `external` nodes or service→service edges.
- **Flows.** Start at a UI action (button handler or form submit), follow the API call to its route, then the handler, then every SDK call it makes. Each hop is a step.
- **Glossary.** Domain nouns that appear as folder names, table names and type names but aren't generic tech words. Ask the user for meanings you can't infer.
- **Hotspots.** `git log --since=6.months --name-only --pretty=format: | sort | uniq -c | sort -rn | head` plus TODO/FIXME counts. scan.py does this when `.git` exists.

## AWS

| Look in | Reveals |
|---|---|
| `serverless.yml` `functions.*.events` | API Gateway routes, SQS/SNS/S3/schedule triggers |
| `serverless.yml` `provider.iam` / `iamRoleStatements` | Which Lambdas may touch which tables/queues (strong evidence for edges) |
| `template.yaml` (SAM) `Policies`, `Events` | Same as above |
| CDK: `table.grantReadWriteData(fn)`, `queue.grantSendMessages(fn)`, `new LambdaIntegration(fn)` | Declared edges — treat grants as `declared` |
| Terraform `aws_lambda_permission`, `aws_api_gateway_integration`, `aws_lambda_event_source_mapping` | Wiring between gateway/queues and functions |
| API Gateway authorizers (`authorizer: aws_iam` / Cognito / custom Lambda) | Where tokens are verified |
| `amplify/` folder, `aws-exports.js`, `amplifyconfiguration.json` | Frontend → Cognito/AppSync/S3 wiring |
| Step Functions definitions (`*.asl.json`) | Workflow steps — good flow material |

Single-table DynamoDB: read key-building helpers (`PK: \`USER#${id}\``) to fill `keys` and `access_patterns`.

## Azure

| Look in | Reveals |
|---|---|
| `host.json`, `function.json`, `[FunctionName]` attributes, `app.http(` (v4 Node) | Azure Functions and their triggers/bindings |
| Bindings (`CosmosDBInput`, `queueTrigger`, `blobOutput`) | Declared data edges |
| Bicep/ARM (`Microsoft.ApiManagement`, `Microsoft.Web/sites`) | APIM → app wiring |
| `@azure/msal-browser`, `msal-react`, `Microsoft.Identity.Web`, `appsettings.json` `AzureAd` section | Entra ID tenant/client config, scopes |
| `local.settings.json` (names only) | Connection setting names → resources |

## GCP

Cloud Run/Functions in `cloudbuild.yaml`, `service.yaml`, Terraform `google_*`. Pub/Sub push subscriptions point at Cloud Run URLs — that's a messaging→compute edge. Firebase: `firebase.json`, `firestore.rules` (great auth-rule material).

## Containers / Kubernetes

- docker-compose `depends_on` and env URLs (`postgres://db:5432`) give edges.
- K8s: `Service` selectors map to `Deployment`s; `Ingress` rules are the edge layer; `ConfigMap`/`Secret` names list config keys.
- Helm `values.yaml` often holds the real topology.

## Frontend frameworks

- Next.js: `app/` or `pages/` routes; `app/api/*` and `pages/api/*` are compute nodes inside the frontend — model as a separate `compute` node ("Next.js API routes") when non-trivial. `middleware.ts` often enforces auth.
- React SPA: find the API client module (`src/api`, `services/`), its base URL env var, and auth interceptor.
- Vue/Nuxt: `nuxt.config`, `server/api/*`, Pinia stores holding tokens.

## Backend frameworks

- Express/Fastify/Nest: router files, auth middleware/guards, DI modules.
- Django/DRF: `urls.py`, `settings.py` (`DATABASES`, `AUTHENTICATION_BACKENDS`), models → entities.
- FastAPI: routers, `Depends(...)` auth dependencies, SQLAlchemy models.
- Spring: `@RestController`, `application.yml`, `@Entity`.
- .NET: `Program.cs` service registration, `[Authorize]`, EF `DbContext`.

## Auth providers

For every provider, capture: issuer, client/app id **names** (not values), token type and lifetime, where the token is verified (gateway authorizer, middleware, each service), and how roles/groups map to permissions.

- Cognito: user pool vs identity pool (identity pool = temporary AWS creds directly from browser — important edge to S3/DynamoDB that bypasses API Gateway).
- Entra ID: single vs multi-tenant, app roles vs scopes, on-behalf-of flows to downstream APIs.
- Auth0/Okta/Clerk: rules/actions that enrich tokens; custom claims namespaces.
- NextAuth/Auth.js: providers list, session strategy (JWT vs database), callbacks that add claims.
