#!/usr/bin/env python3
"""Draft an onboarding atlas.json from a repository.

Stack-agnostic, stdlib-only (uses PyYAML when installed for IaC parsing).
Finds what configuration *declares*; the agent enriches the rest.

Usage: python3 scan.py <repo> [-o <repo>/docs/onboarding/atlas.json]
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

SCANNER_VERSION = "1"

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt", ".svelte-kit", ".venv", "venv", "env",
    "__pycache__", ".terraform", "vendor", "target", ".serverless", "coverage", ".aws-sam", "cdk.out",
    ".turbo", ".cache", ".idea", ".vscode", "out", ".output", "bin", "obj", ".gradle", ".pytest_cache",
    ".mypy_cache", "Pods", ".expo", "storybook-static",
}
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".java", ".kt", ".cs", ".rb", ".php", ".vue", ".svelte", ".rs"}
MAX_FILES = 60000
MAX_READ = 400_000

try:
    import yaml  # type: ignore

    class _Loader(yaml.SafeLoader):
        pass

    def _tag(loader, suffix, node):
        key = "Ref" if suffix == "Ref" else "Fn::" + suffix
        if isinstance(node, yaml.ScalarNode):
            val = loader.construct_scalar(node)
            if suffix == "GetAtt" and isinstance(val, str):
                val = val.split(".")
            return {key: val}
        if isinstance(node, yaml.SequenceNode):
            return {key: loader.construct_sequence(node, deep=True)}
        return {key: loader.construct_mapping(node, deep=True)}

    _Loader.add_multi_constructor("!", _tag)

    def load_yaml_all(text):
        try:
            return [d for d in yaml.load_all(text, Loader=_Loader) if d is not None]
        except Exception:
            return []
    HAVE_YAML = True
except ImportError:  # pragma: no cover
    HAVE_YAML = False

    def load_yaml_all(text):
        return []


# --------------------------------------------------------------------------- signatures
# package -> (id, label, layer, kind, provider)
JS_FRONTEND = {
    "next": "Next.js", "nuxt": "Nuxt", "@angular/core": "Angular", "@sveltejs/kit": "SvelteKit",
    "svelte": "Svelte", "@remix-run/react": "Remix", "astro": "Astro", "react-native": "React Native",
    "expo": "Expo", "vue": "Vue", "react": "React", "solid-js": "Solid", "electron": "Electron",
}
JS_BACKEND = {
    "@nestjs/core": "NestJS", "express": "Express", "fastify": "Fastify", "koa": "Koa", "hono": "Hono",
    "@hapi/hapi": "hapi", "@apollo/server": "Apollo GraphQL", "apollo-server": "Apollo GraphQL",
}
AUTH = {
    # js
    "aws-amplify": ("cognito", "AWS Cognito", "aws"), "@aws-amplify/auth": ("cognito", "AWS Cognito", "aws"),
    "amazon-cognito-identity-js": ("cognito", "AWS Cognito", "aws"),
    "@aws-sdk/client-cognito-identity-provider": ("cognito", "AWS Cognito", "aws"),
    "aws-jwt-verify": ("cognito", "AWS Cognito", "aws"),
    "@azure/msal-browser": ("entra-id", "Microsoft Entra ID", "azure"), "@azure/msal-react": ("entra-id", "Microsoft Entra ID", "azure"),
    "@azure/msal-node": ("entra-id", "Microsoft Entra ID", "azure"), "@azure/msal-angular": ("entra-id", "Microsoft Entra ID", "azure"),
    "next-auth": ("authjs", "NextAuth / Auth.js", "self"), "@auth/core": ("authjs", "NextAuth / Auth.js", "self"),
    "@auth0/nextjs-auth0": ("auth0", "Auth0", "saas"), "@auth0/auth0-react": ("auth0", "Auth0", "saas"), "auth0-js": ("auth0", "Auth0", "saas"),
    "@clerk/nextjs": ("clerk", "Clerk", "saas"), "@clerk/clerk-react": ("clerk", "Clerk", "saas"),
    "@supabase/supabase-js": ("supabase-auth", "Supabase Auth", "saas"),
    "@okta/okta-auth-js": ("okta", "Okta", "saas"), "@okta/okta-react": ("okta", "Okta", "saas"),
    "keycloak-js": ("keycloak", "Keycloak", "self"), "firebase": ("firebase-auth", "Firebase Auth", "gcp"),
    # python
    "msal": ("entra-id", "Microsoft Entra ID", "azure"), "django-allauth": ("allauth", "django-allauth", "self"),
    "firebase-admin": ("firebase-auth", "Firebase Auth", "gcp"), "auth0-python": ("auth0", "Auth0", "saas"),
    "python-keycloak": ("keycloak", "Keycloak", "self"),
}
AUTH_HINTS = {"jsonwebtoken", "jose", "passport", "pyjwt", "python-jose", "djangorestframework-simplejwt", "express-jwt"}
SDK = {
    "@aws-sdk/client-dynamodb": ("dynamodb", "DynamoDB", "data", "table", "aws"),
    "@aws-sdk/lib-dynamodb": ("dynamodb", "DynamoDB", "data", "table", "aws"),
    "@aws-sdk/client-s3": ("s3", "S3", "data", "bucket", "aws"),
    "@aws-sdk/client-sqs": ("sqs", "SQS", "messaging", "queue", "aws"),
    "@aws-sdk/client-sns": ("sns", "SNS", "messaging", "topic", "aws"),
    "@aws-sdk/client-eventbridge": ("eventbridge", "EventBridge", "messaging", "bus", "aws"),
    "@aws-sdk/client-sfn": ("step-functions", "Step Functions", "messaging", "workflow", "aws"),
    "@aws-sdk/client-secrets-manager": ("secrets-manager", "Secrets Manager", "ops", "secret", "aws"),
    "@aws-sdk/client-ssm": ("ssm", "SSM Parameter Store", "ops", "secret", "aws"),
    "@aws-sdk/client-bedrock-runtime": ("bedrock", "Amazon Bedrock", "external", "api", "aws"),
    "@aws-sdk/client-ses": ("ses", "SES email", "external", "api", "aws"),
    "@aws-sdk/client-kinesis": ("kinesis", "Kinesis", "messaging", "queue", "aws"),
    "@azure/cosmos": ("cosmos-db", "Cosmos DB", "data", "database", "azure"),
    "@azure/storage-blob": ("blob-storage", "Blob Storage", "data", "bucket", "azure"),
    "@azure/service-bus": ("service-bus", "Service Bus", "messaging", "queue", "azure"),
    "@azure/keyvault-secrets": ("key-vault", "Key Vault", "ops", "secret", "azure"),
    "@azure/openai": ("azure-openai", "Azure OpenAI", "external", "api", "azure"),
    "@google-cloud/firestore": ("firestore", "Firestore", "data", "database", "gcp"),
    "@google-cloud/storage": ("gcs", "Cloud Storage", "data", "bucket", "gcp"),
    "@google-cloud/pubsub": ("pubsub", "Pub/Sub", "messaging", "topic", "gcp"),
    "@prisma/client": ("sql-db", "SQL database", "data", "database", "self"),
    "pg": ("postgres", "PostgreSQL", "data", "database", "self"), "postgres": ("postgres", "PostgreSQL", "data", "database", "self"),
    "mysql2": ("mysql", "MySQL", "data", "database", "self"), "mongoose": ("mongodb", "MongoDB", "data", "database", "self"),
    "mongodb": ("mongodb", "MongoDB", "data", "database", "self"), "redis": ("redis", "Redis", "data", "cache", "self"),
    "ioredis": ("redis", "Redis", "data", "cache", "self"), "typeorm": ("sql-db", "SQL database", "data", "database", "self"),
    "sequelize": ("sql-db", "SQL database", "data", "database", "self"), "drizzle-orm": ("sql-db", "SQL database", "data", "database", "self"),
    "kafkajs": ("kafka", "Kafka", "messaging", "topic", "self"), "amqplib": ("rabbitmq", "RabbitMQ", "messaging", "queue", "self"),
    "@elastic/elasticsearch": ("elasticsearch", "Elasticsearch", "data", "index", "self"),
    "stripe": ("stripe", "Stripe", "external", "api", "saas"), "openai": ("openai", "OpenAI API", "external", "api", "saas"),
    "@anthropic-ai/sdk": ("anthropic", "Anthropic API", "external", "api", "saas"),
    "@sendgrid/mail": ("sendgrid", "SendGrid", "external", "api", "saas"), "twilio": ("twilio", "Twilio", "external", "api", "saas"),
    "@sentry/node": ("sentry", "Sentry", "ops", "monitor", "saas"), "@sentry/nextjs": ("sentry", "Sentry", "ops", "monitor", "saas"),
    "@sentry/react": ("sentry", "Sentry", "ops", "monitor", "saas"), "dd-trace": ("datadog", "Datadog", "ops", "monitor", "saas"),
    "@datadog/browser-rum": ("datadog", "Datadog", "ops", "monitor", "saas"),
    "applicationinsights": ("app-insights", "Application Insights", "ops", "monitor", "azure"),
    "@opentelemetry/api": ("otel", "OpenTelemetry", "ops", "monitor", "self"),
    "@apollo/client": ("graphql-api", "GraphQL API", "edge", "api", "self"),
    "@aws-appsync/utils": ("appsync", "AppSync", "edge", "gateway", "aws"),
    # python
    "boto3": ("aws-sdk", "AWS services (boto3)", "external", "api", "aws"),
    "sqlalchemy": ("sql-db", "SQL database", "data", "database", "self"), "psycopg2": ("postgres", "PostgreSQL", "data", "database", "self"),
    "psycopg2-binary": ("postgres", "PostgreSQL", "data", "database", "self"), "psycopg": ("postgres", "PostgreSQL", "data", "database", "self"),
    "asyncpg": ("postgres", "PostgreSQL", "data", "database", "self"), "pymongo": ("mongodb", "MongoDB", "data", "database", "self"),
    "motor": ("mongodb", "MongoDB", "data", "database", "self"), "celery": ("celery", "Celery workers", "messaging", "queue", "self"),
    "azure-cosmos": ("cosmos-db", "Cosmos DB", "data", "database", "azure"), "azure-storage-blob": ("blob-storage", "Blob Storage", "data", "bucket", "azure"),
    "azure-servicebus": ("service-bus", "Service Bus", "messaging", "queue", "azure"),
    "google-cloud-firestore": ("firestore", "Firestore", "data", "database", "gcp"), "google-cloud-pubsub": ("pubsub", "Pub/Sub", "messaging", "topic", "gcp"),
    "anthropic": ("anthropic", "Anthropic API", "external", "api", "saas"), "sentry-sdk": ("sentry", "Sentry", "ops", "monitor", "saas"),
    "langchain": ("llm", "LLM provider (LangChain)", "external", "api", "saas"),
}
PY_BACKEND = {"django": "Django", "flask": "Flask", "fastapi": "FastAPI", "starlette": "Starlette", "aiohttp": "aiohttp", "streamlit": "Streamlit"}
PY_SDK_DUPES = {"redis": ("redis", "Redis", "data", "cache", "self"), "stripe": SDK["stripe"], "openai": SDK["openai"]}

CFN_TYPES = {
    "AWS::Serverless::Function": ("compute", "function", "Lambda"), "AWS::Lambda::Function": ("compute", "function", "Lambda"),
    "AWS::DynamoDB::Table": ("data", "table", "DynamoDB"), "AWS::DynamoDB::GlobalTable": ("data", "table", "DynamoDB"),
    "AWS::Serverless::SimpleTable": ("data", "table", "DynamoDB"), "AWS::S3::Bucket": ("data", "bucket", "S3"),
    "AWS::SQS::Queue": ("messaging", "queue", "SQS"), "AWS::SNS::Topic": ("messaging", "topic", "SNS"),
    "AWS::Events::Rule": ("messaging", "schedule", "EventBridge rule"), "AWS::Events::EventBus": ("messaging", "bus", "EventBridge"),
    "AWS::Cognito::UserPool": ("identity", "idp", "Cognito user pool"), "AWS::Cognito::IdentityPool": ("identity", "idp", "Cognito identity pool"),
    "AWS::ApiGateway::RestApi": ("edge", "gateway", "API Gateway REST"), "AWS::Serverless::Api": ("edge", "gateway", "API Gateway REST"),
    "AWS::ApiGatewayV2::Api": ("edge", "gateway", "API Gateway HTTP"), "AWS::Serverless::HttpApi": ("edge", "gateway", "API Gateway HTTP"),
    "AWS::CloudFront::Distribution": ("edge", "cdn", "CloudFront"), "AWS::AppSync::GraphQLApi": ("edge", "gateway", "AppSync"),
    "AWS::StepFunctions::StateMachine": ("messaging", "workflow", "Step Functions"), "AWS::Serverless::StateMachine": ("messaging", "workflow", "Step Functions"),
    "AWS::RDS::DBInstance": ("data", "database", "RDS"), "AWS::RDS::DBCluster": ("data", "database", "Aurora"),
    "AWS::ElastiCache::CacheCluster": ("data", "cache", "ElastiCache"), "AWS::ElastiCache::ReplicationGroup": ("data", "cache", "ElastiCache"),
    "AWS::SecretsManager::Secret": ("ops", "secret", "Secrets Manager"), "AWS::ECS::Service": ("compute", "service", "ECS service"),
    "AWS::ElasticLoadBalancingV2::LoadBalancer": ("edge", "gateway", "Load balancer"), "AWS::Kinesis::Stream": ("messaging", "queue", "Kinesis"),
    "AWS::OpenSearchService::Domain": ("data", "index", "OpenSearch"), "AWS::Amplify::App": ("client", "app", "Amplify Hosting"),
}
TF_TYPES = {
    "aws_lambda_function": ("compute", "function", "Lambda", "aws"), "aws_dynamodb_table": ("data", "table", "DynamoDB", "aws"),
    "aws_s3_bucket": ("data", "bucket", "S3", "aws"), "aws_sqs_queue": ("messaging", "queue", "SQS", "aws"),
    "aws_sns_topic": ("messaging", "topic", "SNS", "aws"), "aws_cloudwatch_event_rule": ("messaging", "schedule", "EventBridge rule", "aws"),
    "aws_cognito_user_pool": ("identity", "idp", "Cognito user pool", "aws"), "aws_api_gateway_rest_api": ("edge", "gateway", "API Gateway REST", "aws"),
    "aws_apigatewayv2_api": ("edge", "gateway", "API Gateway HTTP", "aws"), "aws_cloudfront_distribution": ("edge", "cdn", "CloudFront", "aws"),
    "aws_lb": ("edge", "gateway", "Load balancer", "aws"), "aws_alb": ("edge", "gateway", "Load balancer", "aws"),
    "aws_ecs_service": ("compute", "service", "ECS service", "aws"), "aws_db_instance": ("data", "database", "RDS", "aws"),
    "aws_rds_cluster": ("data", "database", "Aurora", "aws"), "aws_elasticache_cluster": ("data", "cache", "ElastiCache", "aws"),
    "aws_sfn_state_machine": ("messaging", "workflow", "Step Functions", "aws"), "aws_secretsmanager_secret": ("ops", "secret", "Secrets Manager", "aws"),
    "aws_appsync_graphql_api": ("edge", "gateway", "AppSync", "aws"), "aws_kinesis_stream": ("messaging", "queue", "Kinesis", "aws"),
    "aws_amplify_app": ("client", "app", "Amplify Hosting", "aws"),
    "azurerm_linux_function_app": ("compute", "function", "Azure Functions", "azure"), "azurerm_windows_function_app": ("compute", "function", "Azure Functions", "azure"),
    "azurerm_function_app": ("compute", "function", "Azure Functions", "azure"), "azurerm_linux_web_app": ("compute", "service", "App Service", "azure"),
    "azurerm_container_app": ("compute", "service", "Container App", "azure"), "azurerm_api_management": ("edge", "gateway", "API Management", "azure"),
    "azurerm_cosmosdb_account": ("data", "database", "Cosmos DB", "azure"), "azurerm_storage_account": ("data", "bucket", "Storage account", "azure"),
    "azurerm_servicebus_queue": ("messaging", "queue", "Service Bus queue", "azure"), "azurerm_servicebus_topic": ("messaging", "topic", "Service Bus topic", "azure"),
    "azurerm_mssql_database": ("data", "database", "Azure SQL", "azure"), "azurerm_postgresql_flexible_server": ("data", "database", "PostgreSQL", "azure"),
    "azurerm_redis_cache": ("data", "cache", "Azure Cache for Redis", "azure"), "azurerm_key_vault": ("ops", "secret", "Key Vault", "azure"),
    "azurerm_frontdoor": ("edge", "cdn", "Front Door", "azure"), "azurerm_static_web_app": ("client", "app", "Static Web App", "azure"),
    "azuread_application": ("identity", "idp", "Entra ID app registration", "azure"),
    "google_cloud_run_service": ("compute", "service", "Cloud Run", "gcp"), "google_cloud_run_v2_service": ("compute", "service", "Cloud Run", "gcp"),
    "google_cloudfunctions_function": ("compute", "function", "Cloud Functions", "gcp"), "google_cloudfunctions2_function": ("compute", "function", "Cloud Functions", "gcp"),
    "google_pubsub_topic": ("messaging", "topic", "Pub/Sub", "gcp"), "google_storage_bucket": ("data", "bucket", "Cloud Storage", "gcp"),
    "google_sql_database_instance": ("data", "database", "Cloud SQL", "gcp"), "google_firestore_database": ("data", "database", "Firestore", "gcp"),
    "google_api_gateway_api": ("edge", "gateway", "API Gateway", "gcp"),
}
CDK_TYPES = {
    "Function": ("compute", "function", "Lambda"), "NodejsFunction": ("compute", "function", "Lambda"), "PythonFunction": ("compute", "function", "Lambda"),
    "DockerImageFunction": ("compute", "function", "Lambda"), "Table": ("data", "table", "DynamoDB"), "TableV2": ("data", "table", "DynamoDB"),
    "Bucket": ("data", "bucket", "S3"), "Queue": ("messaging", "queue", "SQS"), "Topic": ("messaging", "topic", "SNS"),
    "RestApi": ("edge", "gateway", "API Gateway REST"), "LambdaRestApi": ("edge", "gateway", "API Gateway REST"), "HttpApi": ("edge", "gateway", "API Gateway HTTP"),
    "UserPool": ("identity", "idp", "Cognito user pool"), "StateMachine": ("messaging", "workflow", "Step Functions"),
    "Distribution": ("edge", "cdn", "CloudFront"), "Rule": ("messaging", "schedule", "EventBridge rule"), "GraphqlApi": ("edge", "gateway", "AppSync"),
    "DatabaseInstance": ("data", "database", "RDS"), "DatabaseCluster": ("data", "database", "Aurora"),
    "ApplicationLoadBalancedFargateService": ("compute", "service", "Fargate service"), "FargateService": ("compute", "service", "Fargate service"),
}
COMPOSE_IMAGES = {
    "postgres": ("data", "database", "PostgreSQL"), "postgis": ("data", "database", "PostgreSQL"), "mysql": ("data", "database", "MySQL"),
    "mariadb": ("data", "database", "MariaDB"), "mongo": ("data", "database", "MongoDB"), "redis": ("data", "cache", "Redis"),
    "valkey": ("data", "cache", "Valkey"), "memcached": ("data", "cache", "Memcached"), "rabbitmq": ("messaging", "queue", "RabbitMQ"),
    "kafka": ("messaging", "topic", "Kafka"), "redpanda": ("messaging", "topic", "Redpanda"), "zookeeper": ("messaging", "service", "ZooKeeper"),
    "elasticsearch": ("data", "index", "Elasticsearch"), "opensearch": ("data", "index", "OpenSearch"), "minio": ("data", "bucket", "MinIO"),
    "localstack": ("ops", "service", "LocalStack"), "dynamodb-local": ("data", "table", "DynamoDB Local"), "nginx": ("edge", "gateway", "nginx"),
    "traefik": ("edge", "gateway", "Traefik"), "keycloak": ("identity", "idp", "Keycloak"), "mailhog": ("ops", "service", "MailHog"),
    "azurite": ("data", "bucket", "Azurite"), "cosmosdb": ("data", "database", "Cosmos emulator"), "grafana": ("ops", "monitor", "Grafana"),
    "prometheus": ("ops", "monitor", "Prometheus"), "jaeger": ("ops", "monitor", "Jaeger"),
}

ENV_CODE_RE = re.compile(
    r"process\.env\.([A-Z][A-Z0-9_]{2,})|process\.env\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\]|import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"
    r"|os\.environ(?:\.get)?\(?\[?['\"]([A-Z][A-Z0-9_]{2,})['\"]|os\.getenv\(['\"]([A-Z][A-Z0-9_]{2,})['\"]"
    r"|Environment\.GetEnvironmentVariable\(\"([A-Z][A-Z0-9_]{2,})\"\)|System\.getenv\(\"([A-Z][A-Z0-9_]{2,})\"\)"
)
SECRET_RE = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|PRIVATE|API_KEY|APIKEY|CREDENTIAL|_KEY$", re.I)


def slug(s):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", str(s))
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def read(path, limit=MAX_READ):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


# --------------------------------------------------------------------------- atlas builder
class Atlas:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.nodes = {}
        self.edges = {}
        self.apis = []
        self.flows = []
        self.gaps = []
        self.stack = []
        self.config = {}
        self.setup = []
        self.prereq = []
        self.pipeline = []
        self.entities = []
        self.relations = []
        self.owners = []
        self.decisions = []
        self.hotspots = []
        self.entry_points = []
        self.modules = []
        self.auth_hints = set()
        self.auth_roles = []
        self.verified_at = set()
        self.service_ids = []
        self.found = Counter()

    def rel(self, p):
        return os.path.relpath(p, self.root).replace(os.sep, "/")

    def add_stack(self, s):
        if s and s not in self.stack:
            self.stack.append(s)

    def node(self, nid, label, layer, kind, provider="self", tech="", source=None, confidence="declared", group=None, notes=""):
        nid = slug(nid)
        n = self.nodes.get(nid)
        if n is None:
            n = {"id": nid, "label": label, "kind": kind, "layer": layer, "provider": provider, "tech": tech,
                 "source": [], "confidence": confidence}
            if group:
                n["group"] = group
            if notes:
                n["notes"] = notes
            self.nodes[nid] = n
        else:
            if confidence == "declared":
                n["confidence"] = "declared"
            if tech and not n.get("tech"):
                n["tech"] = tech
            if notes and notes not in n.get("notes", ""):
                n["notes"] = (n.get("notes", "") + " " + notes).strip()
        for s in ([source] if isinstance(source, str) else (source or [])):
            if s and s not in n["source"]:
                n["source"].append(s)
        return nid

    def edge(self, a, b, kind, label="", confidence="declared", source=None):
        a, b = slug(a), slug(b)
        if a == b:
            return
        key = (a, b, kind)
        e = self.edges.get(key)
        if e is None:
            e = {"from": a, "to": b, "kind": kind, "label": label, "confidence": confidence, "source": []}
            self.edges[key] = e
        else:
            if label and label not in e["label"].split(" · "):
                e["label"] = (e["label"] + " · " + label).strip(" ·") if e["label"] else label
                if len(e["label"]) > 120:
                    e["label"] = e["label"][:117] + "…"
            if confidence == "declared":
                e["confidence"] = "declared"
        if source and source not in e["source"]:
            e["source"].append(source)

    def cfg(self, key, where, purpose=""):
        c = self.config.setdefault(key, {"key": key, "where": [], "secret": bool(SECRET_RE.search(key)), "purpose": purpose})
        if where not in c["where"] and len(c["where"]) < 6:
            c["where"].append(where)


# --------------------------------------------------------------------------- walking
def walk(root):
    files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".") or d in (".github", ".gitlab", ".circleci", ".azure")]
        for fn in fns:
            files.append(os.path.join(dp, fn))
            if len(files) >= MAX_FILES:
                return files
    return files


# --------------------------------------------------------------------------- detectors
def owner_for(atlas, owners_by_dir, path):
    d = os.path.dirname(path)
    while True:
        if d in owners_by_dir:
            return owners_by_dir[d]
        if d == atlas.root or len(d) < len(atlas.root):
            return None
        d = os.path.dirname(d)


def detect_packages(atlas, files, owners_by_dir, sdk_users):
    pkgs = [f for f in files if os.path.basename(f) == "package.json"]
    pyreq = [f for f in files if os.path.basename(f) in ("requirements.txt", "pyproject.toml", "Pipfile")]
    for f in pkgs:
        try:
            data = json.loads(read(f))
        except Exception:
            continue
        deps = {}
        for k in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(data.get(k) or {})
        d = os.path.dirname(f)
        rel = atlas.rel(f)
        name = data.get("name") or os.path.basename(d) or "app"
        short = name.split("/")[-1]
        fe = next((v for k, v in JS_FRONTEND.items() if k in deps), None)
        be = next((v for k, v in JS_BACKEND.items() if k in deps), None)
        owner = None
        if fe:
            owner = atlas.node(f"{short}-web" if not short.endswith(("web", "app", "frontend", "ui")) else short,
                               f"{short} ({fe})", "client", "app", "self", fe, rel, "declared")
            atlas.add_stack(fe)
            if fe in ("Next.js", "Nuxt", "SvelteKit", "Remix") and any(
                    re.search(r"[/\\](app|pages|src[/\\]app|src[/\\]pages)[/\\]api[/\\]|[/\\]server[/\\]api[/\\]", x) for x in files if x.startswith(d + os.sep)):
                srv = atlas.node(f"{short}-server-routes", f"{short} server routes", "compute", "service", "self", f"{fe} API routes", rel, "declared",
                                 notes="Server-side routes inside the frontend project.")
                atlas.edge(owner, srv, "calls", "fetch /api/*", "inferred", rel)
        if be:
            owner = atlas.node(f"{short}-api" if not short.endswith(("api", "server", "service", "backend")) else short,
                               f"{short} ({be})", "compute", "service", "self", be, rel, "declared")
            atlas.add_stack(be)
        if owner:
            owners_by_dir[d] = owner
            atlas.modules.append({"path": atlas.rel(d) or ".", "purpose": f"{fe or be} package '{name}'", "depends_on": []})
        for dep in deps:
            if dep in AUTH:
                sdk_users[("auth", AUTH[dep])].append((d, rel, dep))
            elif dep in AUTH_HINTS:
                atlas.auth_hints.add(f"{dep} in {rel}")
            elif dep in SDK:
                sdk_users[("sdk", SDK[dep])].append((d, rel, dep))
            elif dep == "aws-sdk":
                sdk_users[("sdk", ("aws-sdk", "AWS services (aws-sdk v2)", "external", "api", "aws"))].append((d, rel, dep))
        scripts = data.get("scripts") or {}
        for s in ("dev", "start", "build", "test", "lint", "deploy", "migrate", "db:migrate", "seed"):
            if s in scripts:
                pm = "pnpm" if os.path.exists(os.path.join(d, "pnpm-lock.yaml")) else "yarn" if os.path.exists(os.path.join(d, "yarn.lock")) else "npm run" if s not in ("start", "test") else "npm"
                cmd = f"{pm} {s}" if pm != "npm" else f"npm {s}"
                where = atlas.rel(d) or "."
                atlas.setup.append({"step": f"{s} ({where})", "command": f"cd {where} && {cmd}" if where != "." else cmd, "notes": scripts[s][:120]})
        eng = (data.get("engines") or {}).get("node")
        if eng:
            atlas.prereq.append(f"Node {eng} ({rel})")
        main = data.get("main")
        if main:
            atlas.entry_points.append({"path": atlas.rel(os.path.join(d, main)), "purpose": f"main of {name}"})
    for f in pyreq:
        txt = read(f).lower()
        d = os.path.dirname(f)
        rel = atlas.rel(f)
        names = set(re.findall(r"^\s*\"?([a-z0-9_.\-\[\]]+)", txt, re.M))
        names = {re.split(r"[\[<>=~!;]", n)[0] for n in names}
        be = next((v for k, v in PY_BACKEND.items() if k in names), None)
        owner = owners_by_dir.get(d)
        if be and not owner:
            short = os.path.basename(d) if d != atlas.root else os.path.basename(atlas.root)
            nid = short if short.endswith(("api", "server", "service", "backend")) else f"{short}-api"
            owner = atlas.node(nid, f"{short} ({be})", "compute", "service", "self", be, rel, "declared")
            owners_by_dir[d] = owner
            atlas.add_stack(be)
            atlas.modules.append({"path": atlas.rel(d) or ".", "purpose": f"{be} app", "depends_on": []})
        for n in names:
            if n in AUTH:
                sdk_users[("auth", AUTH[n])].append((d, rel, n))
            elif n in AUTH_HINTS:
                atlas.auth_hints.add(f"{n} in {rel}")
            elif n in SDK or n in PY_SDK_DUPES:
                sdk_users[("sdk", SDK.get(n) or PY_SDK_DUPES[n])].append((d, rel, n))
    for f in files:
        b = os.path.basename(f)
        if b in (".nvmrc", ".node-version", ".python-version", ".tool-versions", ".ruby-version"):
            v = read(f, 200).strip().splitlines()
            if v:
                atlas.prereq.append(f"{b}: {v[0]}")
        elif b == "go.mod":
            m = re.search(r"^go\s+([\d.]+)", read(f), re.M)
            atlas.add_stack("Go")
            if m:
                atlas.prereq.append(f"Go {m.group(1)}")
        elif b.endswith(".csproj"):
            atlas.add_stack(".NET")
        elif b in ("pom.xml", "build.gradle", "build.gradle.kts"):
            atlas.add_stack("JVM")


def resolve_sdk_users(atlas, sdk_users, owners_by_dir):
    """Turn dependency evidence into nodes + edges from the owning app/function."""
    for (kind, sig), users in sdk_users.items():
        if kind == "auth":
            iid, label, prov = sig
            atlas.node(iid, label, "identity", "idp", prov, label, [u[1] for u in users][:4], "declared")
            atlas.add_stack(label)
        else:
            iid, label, layer, nkind, prov = sig
            note = ("Generic: an SDK dependency was found. Replace with the specific resources it touches."
                    if layer in ("data", "messaging") else "SDK dependency found; confirm which components call it.")
            atlas.node(iid, label, layer, nkind, prov, label, [u[1] for u in users][:4], "inferred", notes=note)
        for d, rel, dep in users:
            owner = owners_by_dir.get(d) or owner_for(atlas, owners_by_dir, os.path.join(d, "x"))
            owners = [owner] if owner else functions_under(atlas, d, dep)
            for owner in owners:
                link_sdk(atlas, kind, sig, owner, dep, rel)


def functions_under(atlas, d, dep):
    """Compute nodes whose code lives under d; prefer those whose files import dep."""
    prefix = (atlas.rel(d) + "/") if d != atlas.root else ""
    cands = [n for n in atlas.nodes.values() if n["layer"] == "compute"
             and any(s.startswith(prefix) and os.path.splitext(s)[1] in CODE_EXT for s in n["source"])]
    hits = [n["id"] for n in cands if any(dep in read(os.path.join(atlas.root, s), 100_000)
                                          for s in n["source"] if os.path.splitext(s)[1] in CODE_EXT)]
    return hits or [n["id"] for n in cands]


def link_sdk(atlas, kind, sig, owner, dep, rel):
    if kind == "auth":
        if atlas.nodes[owner]["layer"] == "client":
            atlas.edge(owner, sig[0], "authenticates", f"sign-in via {dep}", "declared", rel)
        else:
            atlas.edge(owner, sig[0], "authorizes", f"verifies tokens ({dep})", "inferred", rel)
            atlas.verified_at.add(owner)
    else:
        ek = "reads-writes" if sig[2] == "data" else "publishes" if sig[2] == "messaging" else "calls"
        atlas.edge(owner, sig[0], ek, dep, "inferred", rel)


def logical_refs(val, known):
    """Collect CloudFormation logical IDs referenced inside a value."""
    out = set()

    def rec(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "Ref" and isinstance(x, str):
                    out.add(x)
                elif k == "Fn::GetAtt":
                    if isinstance(x, list) and x:
                        out.add(str(x[0]))
                    elif isinstance(x, str):
                        out.add(x.split(".")[0])
                elif k == "Fn::ImportValue":
                    continue
                else:
                    rec(x)
        elif isinstance(v, list):
            for x in v:
                rec(x)
        elif isinstance(v, str):
            for m in re.findall(r"\$\{([A-Za-z0-9]+)(?:\.[A-Za-z]+)?\}", v):
                out.add(m)
            for m in re.findall(r"resources\.Resources\.([A-Za-z0-9]+)", v):
                out.add(m)
    rec(val)
    return {r for r in out if r in known}


def classify_actions(actions):
    acts = [a.lower() for a in (actions if isinstance(actions, list) else [actions]) if isinstance(a, str)]
    if not acts:
        return "reads-writes", ""
    reads = any(re.search(r"get|query|scan|read|list|describe|receive|batchget", a) for a in acts)
    writes = any(re.search(r"put|update|delete|write|send|publish|batchwrite|start|invoke", a) for a in acts)
    kind = "reads-writes" if reads and writes or any(a.endswith("*") for a in acts) else "reads" if reads else "writes" if writes else "reads-writes"
    short = ", ".join(sorted({a.split(":")[-1] for a in acts}))[:80]
    return kind, short


def cfn_resource_nodes(atlas, resources, rel, group, prefix=""):
    """Create nodes for CloudFormation resources; return logical-id -> node id map."""
    lid_map = {}
    for lid, r in (resources or {}).items():
        if not isinstance(r, dict):
            continue
        t = r.get("Type", "")
        if t in CFN_TYPES:
            layer, kind, tech = CFN_TYPES[t]
            props = r.get("Properties") or {}
            nice = props.get("TableName") or props.get("QueueName") or props.get("TopicName") or props.get("BucketName") or props.get("UserPoolName")
            label = lid if not isinstance(nice, str) or "${" in nice else nice
            lid_map[lid] = atlas.node(prefix + lid, label, layer, kind, "aws", tech, rel, "declared", group)
            if t in ("AWS::DynamoDB::Table",):
                ks = props.get("KeySchema") or []
                keys = ", ".join(f"{k.get('AttributeName')}({k.get('KeyType')})" for k in ks if isinstance(k, dict))
                gsis = [g.get("IndexName") for g in props.get("GlobalSecondaryIndexes") or [] if isinstance(g, dict)]
                atlas.entities.append({"name": label, "store": lid_map[lid], "keys": keys + (f"; GSIs: {', '.join(map(str, gsis))}" if gsis else ""),
                                       "fields": [a.get("AttributeName") for a in props.get("AttributeDefinitions") or [] if isinstance(a, dict)],
                                       "owner": "", "access_patterns": [], "source": rel})
            if "Cognito::UserPool" in t:
                atlas.add_stack("AWS Cognito")
    return lid_map


def iam_edges(atlas, fn_ids, statements, lid_map, rel):
    for st in statements or []:
        if not isinstance(st, dict) or st.get("Effect", "Allow") != "Allow":
            continue
        kind, short = classify_actions(st.get("Action") or [])
        targets = logical_refs(st.get("Resource"), lid_map)
        for t in targets:
            for fid in fn_ids:
                atlas.edge(fid, lid_map[t], kind, short, "declared", rel)


def env_edges(atlas, fn_id, env, lid_map, rel):
    for k, v in (env or {}).items() if isinstance(env, dict) else []:
        for t in logical_refs(v, lid_map):
            tgt = lid_map[t]
            layer = atlas.nodes[tgt]["layer"]
            if layer in ("data", "messaging", "ops"):
                atlas.edge(fn_id, tgt, "reads-writes" if layer == "data" else "publishes" if layer == "messaging" else "reads",
                           f"env {k}", "inferred", rel)


def detect_serverless(atlas, files, owners_by_dir):
    for f in files:
        if not re.match(r"serverless(\.[\w-]+)?\.ya?ml$", os.path.basename(f)):
            continue
        docs = load_yaml_all(read(f))
        if not docs or not isinstance(docs[0], dict):
            if not HAVE_YAML:
                atlas.gaps.append(f"Install PyYAML to parse {atlas.rel(f)}")
            continue
        sv = docs[0]
        rel = atlas.rel(f)
        d = os.path.dirname(f)
        atlas.found["serverless"] += 1
        service = sv.get("service")
        service = service.get("name") if isinstance(service, dict) else service
        group = slug(service or os.path.basename(d))
        atlas.add_stack("Serverless Framework")
        provider = sv.get("provider") or {}
        runtime = provider.get("runtime", "")
        resources = ((sv.get("resources") or {}).get("Resources")) if isinstance(sv.get("resources"), dict) else {}
        lid_map = cfn_resource_nodes(atlas, resources, rel, group, prefix=f"{group}-")
        fns = sv.get("functions") or {}
        fn_ids = []
        api_id = None
        authorizer_nodes = [nid for nid in lid_map.values() if atlas.nodes[nid]["layer"] == "identity"]
        for fname, fn in fns.items():
            if not isinstance(fn, dict):
                continue
            handler = fn.get("handler", "")
            hpath = handler.rsplit(".", 1)[0] if handler else ""
            src = [rel]
            for ext in (".ts", ".js", ".mjs", ".py", ".go"):
                cand = os.path.join(d, hpath + ext)
                if hpath and os.path.exists(cand):
                    src.append(atlas.rel(cand))
                    atlas.entry_points.append({"path": atlas.rel(cand), "purpose": f"Lambda handler '{fname}'"})
                    owners_by_dir.setdefault(os.path.dirname(cand), f"{group}-{slug(fname)}")
                    break
            fid = atlas.node(f"{group}-{fname}", fname, "compute", "function", "aws", f"Lambda · {fn.get('runtime', runtime)}".strip(" ·"),
                             src, "declared", group, fn.get("description", ""))
            fn_ids.append(fid)
            env_edges(atlas, fid, {**(provider.get("environment") or {}), **(fn.get("environment") or {})}, lid_map, rel)
            iam_edges(atlas, [fid], fn.get("iamRoleStatements"), lid_map, rel)
            for ev in fn.get("events") or []:
                if not isinstance(ev, dict) or not ev:
                    continue
                etype, cfg = next(iter(ev.items()))
                if etype in ("http", "httpApi"):
                    api_id = api_id or atlas.node(f"{group}-api-gateway", f"API Gateway ({service})", "edge", "gateway", "aws",
                                                  "API Gateway " + ("HTTP" if etype == "httpApi" else "REST"), rel, "declared", group)
                    if isinstance(cfg, str):
                        parts = cfg.split()
                        method, path = (parts + ["ANY", "/"])[:2] if len(parts) >= 2 else ("ANY", parts[0] if parts else "/")
                        auth = None
                    else:
                        cfg = cfg or {}
                        method, path = str(cfg.get("method", "ANY")).upper(), cfg.get("path", "/")
                        auth = cfg.get("authorizer")
                    if not str(path).startswith("/"):
                        path = "/" + str(path)
                    atlas.edge(api_id, fid, "routes", f"{method} {path}", "declared", rel)
                    auth_txt = "none declared"
                    if auth:
                        if isinstance(auth, dict):
                            at = auth.get("type") or auth.get("name") or ""
                            auth_txt = str(at)
                            arn = auth.get("arn")
                            refs = logical_refs(arn, lid_map) if arn else set()
                            for r in refs:
                                atlas.edge(api_id, lid_map[r], "authorizes", "JWT authorizer", "declared", rel)
                            if "COGNITO" in str(at).upper() or refs or "cognito" in json.dumps(auth).lower():
                                cog = next(iter([lid_map[r] for r in refs]), None) or (authorizer_nodes[0] if authorizer_nodes else atlas.node("cognito", "AWS Cognito", "identity", "idp", "aws", "Cognito", rel, "inferred"))
                                atlas.edge(api_id, cog, "authorizes", "Cognito authorizer", "declared", rel)
                                auth_txt = "Cognito JWT" + (f" (scopes: {', '.join(auth.get('scopes'))})" if auth.get("scopes") else "")
                        else:
                            auth_txt = str(auth)
                            if auth == "aws_iam":
                                auth_txt = "AWS IAM (SigV4)"
                        atlas.verified_at.add(api_id)
                    atlas.apis.append({"method": method, "path": path, "handler": fid, "auth": auth_txt, "description": fn.get("description", ""), "source": rel})
                elif etype == "sqs":
                    arn = cfg.get("arn") if isinstance(cfg, dict) else cfg
                    refs = logical_refs(arn, lid_map)
                    qid = lid_map[next(iter(refs))] if refs else atlas.node(f"{group}-{fname}-queue", "SQS queue", "messaging", "queue", "aws", "SQS", rel, "inferred", group)
                    atlas.edge(qid, fid, "triggers", "SQS batch", "declared", rel)
                elif etype == "sns":
                    topic = cfg if isinstance(cfg, str) else (cfg or {}).get("topicName") or (cfg or {}).get("arn")
                    refs = logical_refs(topic, lid_map)
                    tid = lid_map[next(iter(refs))] if refs else atlas.node(f"{group}-{slug(str(topic))[:30]}", f"SNS {str(topic)[:30]}", "messaging", "topic", "aws", "SNS", rel, "declared", group)
                    atlas.edge(tid, fid, "triggers", "SNS message", "declared", rel)
                elif etype == "s3":
                    b = cfg if isinstance(cfg, str) else (cfg or {}).get("bucket")
                    bid = atlas.node(f"{group}-{slug(str(b))[:30]}", f"S3 {b}", "data", "bucket", "aws", "S3", rel, "declared", group)
                    atlas.edge(bid, fid, "triggers", (cfg or {}).get("event", "s3 event") if isinstance(cfg, dict) else "s3 event", "declared", rel)
                elif etype == "schedule":
                    rate = cfg if isinstance(cfg, str) else (cfg or {}).get("rate")
                    sid = atlas.node(f"{group}-{fname}-schedule", f"Schedule {str(rate)[:40]}", "messaging", "schedule", "aws", "EventBridge schedule", rel, "declared", group)
                    atlas.edge(sid, fid, "triggers", str(rate)[:60], "declared", rel)
                elif etype == "stream":
                    arn = cfg.get("arn") if isinstance(cfg, dict) else cfg
                    refs = logical_refs(arn, lid_map)
                    for r in refs:
                        atlas.edge(lid_map[r], fid, "triggers", "stream", "declared", rel)
                elif etype in ("eventBridge", "cloudwatchEvent"):
                    bid = atlas.node(f"{group}-eventbridge", "EventBridge", "messaging", "bus", "aws", "EventBridge", rel, "declared", group)
                    pat = json.dumps((cfg or {}).get("pattern", {}))[:60] if isinstance(cfg, dict) else ""
                    atlas.edge(bid, fid, "triggers", pat or "event", "declared", rel)
                elif etype == "websocket":
                    wid = atlas.node(f"{group}-websocket-api", "WebSocket API", "edge", "gateway", "aws", "API Gateway WebSocket", rel, "declared", group)
                    route = cfg.get("route") if isinstance(cfg, dict) else cfg
                    atlas.edge(wid, fid, "routes", str(route), "declared", rel)
                elif etype == "cognitoUserPool":
                    cid = authorizer_nodes[0] if authorizer_nodes else atlas.node("cognito", "AWS Cognito", "identity", "idp", "aws", "Cognito", rel, "declared")
                    atlas.edge(cid, fid, "triggers", (cfg or {}).get("trigger", "trigger") if isinstance(cfg, dict) else "trigger", "declared", rel)
        stmts = (provider.get("iamRoleStatements") or ((provider.get("iam") or {}).get("role") or {}).get("statements")
                 if isinstance((provider.get("iam") or {}).get("role"), dict) else provider.get("iamRoleStatements"))
        iam_edges(atlas, fn_ids, stmts, lid_map, rel)
        for fid in fn_ids:
            atlas.service_ids.append({"who": fid, "can": "see edges (IAM)", "source": rel})
        if runtime:
            atlas.prereq.append(f"Lambda runtime {runtime} ({rel})")


def detect_cfn(atlas, files, owners_by_dir):
    for f in files:
        b = os.path.basename(f)
        if not re.search(r"\.(ya?ml|json|template)$", b) or re.match(r"serverless", b) or "node_modules" in f:
            continue
        txt = read(f, 600_000)
        if "AWS::" not in txt or "Resources" not in txt:
            continue
        docs = json.loads(txt) if b.endswith(".json") and txt.strip().startswith("{") else None
        if docs is None:
            docs = (load_yaml_all(txt) or [None])[0]
        if not isinstance(docs, dict) or not isinstance(docs.get("Resources"), dict):
            continue
        rel = atlas.rel(f)
        atlas.found["cloudformation"] += 1
        sam = "Transform" in docs and "Serverless" in str(docs.get("Transform"))
        atlas.add_stack("AWS SAM" if sam else "CloudFormation")
        group = slug(os.path.splitext(b)[0] if os.path.basename(os.path.dirname(f)) in ("", ".") else os.path.basename(os.path.dirname(f)) or "stack")
        res = docs["Resources"]
        lid_map = cfn_resource_nodes(atlas, res, rel, group)
        glob_env = (((docs.get("Globals") or {}).get("Function") or {}).get("Environment") or {}).get("Variables") or {}
        for lid, r in res.items():
            if not isinstance(r, dict) or r.get("Type") not in ("AWS::Serverless::Function", "AWS::Lambda::Function"):
                continue
            fid = lid_map[lid]
            props = r.get("Properties") or {}
            env = {**glob_env, **((props.get("Environment") or {}).get("Variables") or {})}
            env_edges(atlas, fid, env, lid_map, rel)
            cu = props.get("CodeUri")
            if isinstance(cu, str):
                atlas.nodes[fid]["source"].append(cu)
            for pol in props.get("Policies") or []:
                if isinstance(pol, dict):
                    for pname, pv in pol.items():
                        refs = logical_refs(pv, lid_map)
                        k = "reads" if "Read" in pname else "writes" if re.search(r"Send|Publish|Write|Put", pname) else "reads-writes"
                        for t in refs:
                            atlas.edge(fid, lid_map[t], k, pname.replace("Policy", ""), "declared", rel)
                        if pname == "Statement":
                            iam_edges(atlas, [fid], pv, lid_map, rel)
            for ename, ev in (props.get("Events") or {}).items():
                if not isinstance(ev, dict):
                    continue
                et, ep = ev.get("Type"), ev.get("Properties") or {}
                if et in ("Api", "HttpApi"):
                    refs = logical_refs(ep.get("RestApiId") or ep.get("ApiId"), lid_map)
                    gid = lid_map[next(iter(refs))] if refs else atlas.node(f"{group}-implicit-api", "API Gateway (implicit)", "edge", "gateway", "aws", f"API Gateway {'HTTP' if et == 'HttpApi' else 'REST'}", rel, "declared", group)
                    method, path = str(ep.get("Method", "ANY")).upper(), ep.get("Path", "/")
                    atlas.edge(gid, fid, "routes", f"{method} {path}", "declared", rel)
                    a = (ep.get("Auth") or {}).get("Authorizer")
                    atlas.apis.append({"method": method, "path": path, "handler": fid, "auth": str(a or "see API default"), "description": ename, "source": rel})
                elif et in ("SQS", "SNS", "DynamoDB", "Kinesis", "S3", "EventBridgeRule", "CloudWatchEvent"):
                    refs = logical_refs(ep, lid_map)
                    for t in refs:
                        atlas.edge(lid_map[t], fid, "triggers", et, "declared", rel)
                    if not refs and et in ("EventBridgeRule", "CloudWatchEvent"):
                        bid = atlas.node(f"{group}-eventbridge", "EventBridge", "messaging", "bus", "aws", "EventBridge", rel, "declared", group)
                        atlas.edge(bid, fid, "triggers", ename, "declared", rel)
                elif et in ("Schedule", "ScheduleV2"):
                    sid = atlas.node(f"{group}-{lid}-schedule", f"Schedule {ep.get('Schedule') or ep.get('ScheduleExpression')}", "messaging", "schedule", "aws", "EventBridge schedule", rel, "declared", group)
                    atlas.edge(sid, fid, "triggers", str(ep.get("Schedule") or ep.get("ScheduleExpression")), "declared", rel)
                elif et == "Cognito":
                    for t in logical_refs(ep, lid_map):
                        atlas.edge(lid_map[t], fid, "triggers", str(ep.get("Trigger")), "declared", rel)
        for lid, r in res.items():
            if not isinstance(r, dict):
                continue
            t = r.get("Type", "")
            props = r.get("Properties") or {}
            if t in ("AWS::Serverless::Api", "AWS::Serverless::HttpApi") and lid in lid_map:
                for t2 in logical_refs(props.get("Auth"), lid_map):
                    atlas.edge(lid_map[lid], lid_map[t2], "authorizes", "JWT authorizer", "declared", rel)
                    atlas.verified_at.add(lid_map[lid])
            elif t == "AWS::ApiGateway::Authorizer":
                for api in logical_refs(props.get("RestApiId"), lid_map):
                    for pool in logical_refs(props.get("ProviderARNs"), lid_map):
                        atlas.edge(lid_map[api], lid_map[pool], "authorizes", "Cognito authorizer", "declared", rel)
                        atlas.verified_at.add(lid_map[api])
            elif t == "AWS::Lambda::EventSourceMapping":
                fns = logical_refs(props.get("FunctionName"), lid_map)
                srcs = logical_refs(props.get("EventSourceArn"), lid_map)
                for a in srcs:
                    for z in fns:
                        atlas.edge(lid_map[a], lid_map[z], "triggers", "event source", "declared", rel)
            elif t == "AWS::IAM::Policy" or t == "AWS::IAM::Role":
                pass  # role→function mapping is too indirect; agent enriches.
            elif t == "AWS::CloudFront::Distribution" and lid in lid_map:
                for z in logical_refs(props, lid_map):
                    if z != lid:
                        atlas.edge(lid_map[lid], lid_map[z], "routes", "origin", "declared", rel)


def tf_blocks(txt):
    for m in re.finditer(r'^\s*(resource|module|data)\s+"([\w-]+)"\s*(?:"([\w-]+)")?\s*\{', txt, re.M):
        start = m.end()
        depth, i = 1, start
        while i < len(txt) and depth:
            c = txt[i]
            depth += (c == "{") - (c == "}")
            i += 1
        yield m.group(1), m.group(2), m.group(3), txt[start:i - 1]


def detect_terraform(atlas, files):
    tf = [f for f in files if f.endswith(".tf")]
    if not tf:
        return
    blocks = []
    for f in tf:
        for kind, t, name, body in tf_blocks(read(f)):
            blocks.append((kind, t, name, body, atlas.rel(f)))
    if not blocks:
        return
    atlas.found["terraform"] += len(tf)
    atlas.add_stack("Terraform")
    ids = {}
    for kind, t, name, body, rel in blocks:
        if kind == "resource" and t in TF_TYPES:
            layer, nkind, tech, prov = TF_TYPES[t]
            nm = re.search(r'^\s*(?:name|function_name|bucket)\s*=\s*"([^"$]+)"', body, re.M)
            ids[f"{t}.{name}"] = atlas.node(f"{name}-{t.split('_', 1)[1]}" if name in ("this", "main", "default") else name,
                                            nm.group(1) if nm else name, layer, nkind, prov, tech, rel, "declared")
            if t == "aws_dynamodb_table":
                hk = re.search(r'hash_key\s*=\s*"([^"]+)"', body)
                rk = re.search(r'range_key\s*=\s*"([^"]+)"', body)
                atlas.entities.append({"name": nm.group(1) if nm else name, "store": ids[f"{t}.{name}"],
                                       "keys": ", ".join(x for x in [f"{hk.group(1)}(HASH)" if hk else "", f"{rk.group(1)}(RANGE)" if rk else ""] if x),
                                       "fields": [], "owner": "", "access_patterns": [], "source": rel})
        elif kind == "module":
            src = re.search(r'source\s*=\s*"([^"]+)"', body)
            atlas.gaps.append(f"Terraform module '{t}' ({src.group(1) if src else '?'}) in {rel} — inspect for resources not mapped here.")
    ref_re = re.compile(r"\b((?:aws|azurerm|google|azuread)_[a-z0-9_]+)\.([\w-]+)")
    for kind, t, name, body, rel in blocks:
        if kind != "resource":
            continue
        refs = [ids[f"{a}.{b}"] for a, b in ref_re.findall(body) if f"{a}.{b}" in ids]
        me = ids.get(f"{t}.{name}")
        if me:
            for r in set(refs):
                if r != me:
                    layer = atlas.nodes[r]["layer"]
                    atlas.edge(me, r, "reads-writes" if layer == "data" else "depends-on", "references", "inferred", rel)
        else:
            uniq = list(dict.fromkeys(refs))
            fns = [r for r in uniq if atlas.nodes[r]["layer"] == "compute"]
            others = [r for r in uniq if r not in fns]
            label = t.replace("aws_", "").replace("_", " ")
            for fn in fns:
                for o in others:
                    lay = atlas.nodes[o]["layer"]
                    if lay in ("edge",):
                        atlas.edge(o, fn, "routes", label, "declared", rel)
                    elif lay in ("messaging",) or "event_source" in t or "notification" in t:
                        atlas.edge(o, fn, "triggers", label, "declared", rel)
                    elif "policy" in t or "iam" in t:
                        atlas.edge(fn, o, "reads-writes", label, "inferred", rel)
                    elif lay == "identity":
                        atlas.edge(o, fn, "authorizes", label, "inferred", rel)
            if "authorizer" in t:
                gws = [r for r in uniq if atlas.nodes[r]["layer"] == "edge"]
                idps = [r for r in uniq if atlas.nodes[r]["layer"] == "identity"]
                for g in gws:
                    for i in idps:
                        atlas.edge(g, i, "authorizes", "JWT authorizer", "declared", rel)
                        atlas.verified_at.add(g)


def detect_cdk(atlas, files):
    roots = {os.path.dirname(f) for f in files if os.path.basename(f) == "cdk.json"}
    if not roots:
        return
    atlas.add_stack("AWS CDK")
    new_re = re.compile(r"(?:(?:const|let|var|this\.)\s*(\w+)\s*=\s*|(\w+)\s*=\s*)?new\s+(?:\w+\.)?(\w+)\(\s*(?:this|self|scope)\s*,\s*['\"]([\w-]+)['\"]")
    grant_re = re.compile(r"(?:this\.)?(\w+)\.grant(\w*)\(\s*(?:this\.)?(\w+)")
    integ_re = re.compile(r"new\s+(?:\w+\.)?(?:Lambda\w*Integration|HttpLambdaIntegration)\(\s*(?:['\"][^'\"]*['\"]\s*,\s*)?(?:this\.)?(\w+)")
    src_re = re.compile(r"new\s+(?:\w+\.)?(SqsEventSource|SnsEventSource|DynamoEventSource|S3EventSource|KinesisEventSource)\(\s*(?:this\.)?(\w+)")
    for f in files:
        if not any(f.startswith(r + os.sep) for r in roots) or not f.endswith((".ts", ".py", ".js")) or f.endswith(".d.ts") or "test" in f.lower():
            continue
        txt = read(f)
        if "aws-cdk" not in txt and "aws_cdk" not in txt:
            continue
        rel = atlas.rel(f)
        atlas.found["cdk"] += 1
        var2id = {}
        apis = []
        for m in new_re.finditer(txt):
            var = m.group(1) or m.group(2)
            cls, cid = m.group(3), m.group(4)
            if cls in CDK_TYPES:
                layer, kind, tech = CDK_TYPES[cls]
                nid = atlas.node(cid, cid, layer, kind, "aws", tech, rel, "declared")
                if var:
                    var2id[var] = nid
                if layer == "edge":
                    apis.append(nid)
        for res, how, grantee in grant_re.findall(txt):
            if res in var2id and grantee in var2id:
                k = "reads" if "Read" in how and "Write" not in how else "writes" if re.search(r"Write|Send|Publish|Put", how) and "Read" not in how else "reads-writes"
                atlas.edge(var2id[grantee], var2id[res], k, "grant" + how, "declared", rel)
        for fn in integ_re.findall(txt):
            if fn in var2id:
                for a in apis or [atlas.node("api-gateway", "API Gateway", "edge", "gateway", "aws", "API Gateway", rel, "inferred")]:
                    atlas.edge(a, var2id[fn], "routes", "integration", "declared", rel)
        for line in txt.splitlines():
            m = re.search(r"(?:this\.)?(\w+)\.addEventSource\(\s*" + src_re.pattern, line)
            if m and m.group(1) in var2id and m.group(3) in var2id:
                atlas.edge(var2id[m.group(3)], var2id[m.group(1)], "triggers", m.group(2).replace("EventSource", ""), "declared", rel)


def detect_compose(atlas, files):
    for f in files:
        b = os.path.basename(f)
        if not re.match(r"(docker-)?compose(\.[\w-]+)?\.ya?ml$", b):
            continue
        docs = load_yaml_all(read(f))
        if not docs or not isinstance(docs[0], dict):
            continue
        svcs = docs[0].get("services") or {}
        rel = atlas.rel(f)
        atlas.found["compose"] += 1
        atlas.add_stack("Docker Compose")
        names = set(svcs)
        ids = {}
        for name, s in svcs.items():
            s = s or {}
            image = str(s.get("image", ""))
            sig = next((v for k, v in COMPOSE_IMAGES.items() if k in image.lower() or k == name.lower()), None)
            if sig:
                layer, kind, tech = sig
            else:
                layer, kind, tech = ("compute", "service", "container" + (f" ({image})" if image else " (built locally)"))
            ids[name] = atlas.node(name, name, layer, kind, "self", tech, rel, "declared", notes="Local/dev via docker-compose.")
        for name, s in svcs.items():
            s = s or {}
            dep = s.get("depends_on") or []
            for x in (dep if isinstance(dep, list) else list(dep)):
                if x in ids:
                    atlas.edge(ids[name], ids[x], "depends-on", "depends_on", "declared", rel)
            env = s.get("environment") or {}
            items = env.items() if isinstance(env, dict) else [tuple((e + "=").split("=", 1)) for e in env if isinstance(e, str)]
            for k, v in items:
                atlas.cfg(str(k), rel)
                for other in names - {name}:
                    if re.search(rf"[/@:]{re.escape(other)}(:|/|$)", str(v)):
                        atlas.edge(ids[name], ids[other], "calls", f"env {k}", "inferred", rel)
            ports = s.get("ports") or []
            if ports and atlas.nodes[ids[name]]["layer"] == "compute":
                atlas.nodes[ids[name]]["notes"] = (atlas.nodes[ids[name]].get("notes", "") + f" Ports: {', '.join(map(str, ports))}.").strip()
        atlas.setup.append({"step": "Start local dependencies", "command": f"docker compose -f {rel} up -d", "notes": ", ".join(list(names)[:8])})


def detect_k8s(atlas, files):
    deps, svcs, ings = {}, {}, []
    for f in files:
        if not f.endswith((".yaml", ".yml")) or "/templates/" in f.replace(os.sep, "/"):
            continue
        txt = read(f)
        if "apiVersion:" not in txt or "kind:" not in txt:
            continue
        for d in load_yaml_all(txt):
            if not isinstance(d, dict):
                continue
            k = d.get("kind")
            md = d.get("metadata") or {}
            rel = atlas.rel(f)
            if k in ("Deployment", "StatefulSet", "DaemonSet", "CronJob"):
                spec = d.get("spec") or {}
                labels = ((spec.get("template") or {}).get("metadata") or {}).get("labels") or {}
                imgs = [c.get("image") for c in (((spec.get("template") or {}).get("spec") or {}).get("containers") or []) if isinstance(c, dict)]
                deps[md.get("name")] = (atlas.node(md.get("name", "workload"), md.get("name", "workload"), "compute" if k != "CronJob" else "messaging",
                                                   "service" if k != "CronJob" else "schedule", "self", f"K8s {k} · {', '.join(map(str, imgs))[:60]}", rel, "declared"), labels)
            elif k == "Service":
                svcs[md.get("name")] = ((d.get("spec") or {}).get("selector") or {}, rel)
            elif k == "Ingress":
                ings.append((md.get("name", "ingress"), d.get("spec") or {}, rel))
    if not deps:
        return
    atlas.found["kubernetes"] += 1
    atlas.add_stack("Kubernetes")
    svc_to_dep = {}
    for sname, (sel, rel) in svcs.items():
        for dname, (nid, labels) in deps.items():
            if sel and all(labels.get(a) == b for a, b in sel.items()):
                svc_to_dep[sname] = nid
    for name, spec, rel in ings:
        iid = atlas.node(f"ingress-{name}", f"Ingress {name}", "edge", "gateway", "self", "K8s Ingress", rel, "declared")
        for rule in spec.get("rules") or []:
            host = rule.get("host", "*")
            for p in ((rule.get("http") or {}).get("paths") or []):
                be = ((p.get("backend") or {}).get("service") or {}).get("name") or (p.get("backend") or {}).get("serviceName")
                if be in svc_to_dep:
                    atlas.edge(iid, svc_to_dep[be], "routes", f"{host}{p.get('path', '/')}", "declared", rel)


def detect_openapi(atlas, files):
    for f in files:
        if not f.endswith((".yaml", ".yml", ".json")):
            continue
        b = os.path.basename(f).lower()
        if not any(k in b for k in ("openapi", "swagger", "api")):
            continue
        txt = read(f)
        if not re.search(r"^\s*[\"']?(openapi|swagger)[\"']?\s*:", txt, re.M):
            continue
        try:
            doc = json.loads(txt) if f.endswith(".json") else (load_yaml_all(txt) or [None])[0]
        except Exception:
            doc = None
        if not isinstance(doc, dict):
            continue
        rel = atlas.rel(f)
        atlas.found["openapi"] += 1
        existing = {(a["method"], a["path"]) for a in atlas.apis}
        for path, ops in (doc.get("paths") or {}).items():
            for method, op in (ops or {}).items():
                if method.lower() not in ("get", "post", "put", "patch", "delete"):
                    continue
                key = (method.upper(), path)
                if key in existing:
                    continue
                op = op or {}
                sec = op.get("security", doc.get("security"))
                atlas.apis.append({"method": method.upper(), "path": path, "handler": op.get("operationId", ""),
                                   "auth": ", ".join(k for s in sec or [] for k in s) if sec else "none declared",
                                   "description": (op.get("summary") or op.get("description") or "")[:140], "source": rel})


def detect_prisma(atlas, files):
    for f in files:
        if not f.endswith(".prisma"):
            continue
        txt = read(f)
        rel = atlas.rel(f)
        prov = re.search(r'datasource\s+\w+\s*\{[^}]*provider\s*=\s*"(\w+)"', txt)
        store = atlas.node("sql-db", f"{(prov.group(1) if prov else 'SQL').capitalize()} (Prisma)", "data", "database", "self",
                           prov.group(1) if prov else "SQL", rel, "declared")
        if "sql-db" in atlas.nodes:
            atlas.nodes["sql-db"]["notes"] = ""
        models = dict(re.findall(r"model\s+(\w+)\s*\{([^}]*)\}", txt))
        for mname, body in models.items():
            fields, keys = [], []
            for line in body.splitlines():
                parts = line.strip().split()
                if len(parts) < 2 or parts[0].startswith(("//", "@@")):
                    continue
                fn, ft = parts[0], parts[1].rstrip("?[]")
                if "@id" in line:
                    keys.append(fn)
                if ft in models:
                    atlas.relations.append({"from": mname, "to": ft, "kind": "1-n" if parts[1].endswith("[]") else "n-1"})
                else:
                    fields.append(fn)
            atlas.entities.append({"name": mname, "store": store, "keys": ", ".join(keys), "fields": fields[:20], "owner": "", "access_patterns": [], "source": rel})


def detect_config(atlas, files):
    for f in files:
        b = os.path.basename(f)
        if re.match(r"\.env\.(example|sample|template|dist|defaults)$|\.env\.[\w.-]*example$|^env\.example$|example\.env$", b):
            for line in read(f).splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m:
                    atlas.cfg(m.group(1), atlas.rel(f))
        elif b == "local.settings.json" or b == "appsettings.json":
            try:
                data = json.loads(read(f))
                vals = data.get("Values") or {} if b == "local.settings.json" else {k: 1 for k in data}
                for k in vals:
                    atlas.cfg(k, atlas.rel(f) + " (names only)")
            except Exception:
                pass
    for f in files:
        if os.path.splitext(f)[1] not in CODE_EXT:
            continue
        txt = read(f, 200_000)
        for m in ENV_CODE_RE.finditer(txt):
            key = next(g for g in m.groups() if g)
            atlas.cfg(key, atlas.rel(f))


def detect_ci(atlas, files):
    for f in files:
        rel = atlas.rel(f)
        n = rel.lower()
        if "/.github/workflows/" in "/" + n and n.endswith((".yml", ".yaml")):
            d = (load_yaml_all(read(f)) or [{}])[0] or {}
            on = d.get("on", d.get(True, ""))
            trig = ", ".join(on) if isinstance(on, (list, dict)) else str(on)
            for jname, job in (d.get("jobs") or {}).items():
                steps = [s.get("name") or (s.get("uses") or s.get("run", ""))[:40] for s in (job or {}).get("steps") or [] if isinstance(s, dict)]
                atlas.pipeline.append({"stage": f"{d.get('name', os.path.basename(f))} › {jname}", "tool": "GitHub Actions",
                                       "does": f"on {trig}: " + "; ".join(str(s) for s in steps[:6] if s), "source": rel})
        elif n.endswith(".gitlab-ci.yml"):
            d = (load_yaml_all(read(f)) or [{}])[0] or {}
            for k, v in d.items():
                if isinstance(v, dict) and "script" in v:
                    atlas.pipeline.append({"stage": f"{v.get('stage', '')} › {k}", "tool": "GitLab CI", "does": "; ".join(map(str, v["script"]))[:160] if isinstance(v["script"], list) else str(v["script"])[:160], "source": rel})
        elif os.path.basename(n) in ("buildspec.yml", "buildspec.yaml"):
            d = (load_yaml_all(read(f)) or [{}])[0] or {}
            for ph, v in (d.get("phases") or {}).items():
                atlas.pipeline.append({"stage": ph, "tool": "CodeBuild", "does": "; ".join(map(str, (v or {}).get("commands") or []))[:160], "source": rel})
        elif os.path.basename(n) == "amplify.yml":
            atlas.pipeline.append({"stage": "build & deploy", "tool": "Amplify Hosting", "does": "see amplify.yml phases", "source": rel})
            atlas.add_stack("AWS Amplify")
        elif os.path.basename(n) == "jenkinsfile":
            for st in re.findall(r"stage\s*\(\s*['\"]([^'\"]+)", read(f)):
                atlas.pipeline.append({"stage": st, "tool": "Jenkins", "does": "", "source": rel})
        elif os.path.basename(n) in ("azure-pipelines.yml", "azure-pipelines.yaml", "bitbucket-pipelines.yml", "cloudbuild.yaml", ".circleci/config.yml") or n.endswith(".circleci/config.yml"):
            atlas.pipeline.append({"stage": "pipeline", "tool": os.path.basename(n).split(".")[0], "does": "inspect file", "source": rel})


def detect_context(atlas, files):
    for f in files:
        b = os.path.basename(f)
        rel = atlas.rel(f)
        if b == "CODEOWNERS":
            for line in read(f).splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split()
                    if len(parts) >= 2:
                        atlas.owners.append({"area": parts[0], "owner": " ".join(parts[1:]), "source": rel})
        elif re.search(r"(^|/)(adr|adrs|decisions|architecture/decisions)/", rel.lower()) and b.endswith(".md"):
            txt = read(f, 20_000)
            title = re.search(r"^#\s+(.+)$", txt, re.M)
            date = re.search(r"(\d{4}-\d{2}(?:-\d{2})?)", txt)
            status = re.search(r"(?i)status:?\s*\**\s*(\w+)", txt)
            atlas.decisions.append({"title": title.group(1).strip() if title else b, "date": date.group(1) if date else "",
                                    "summary": f"Status: {status.group(1)}" if status else "", "source": rel})
        elif b.lower() in ("readme.md", "readme") and os.path.dirname(f) == atlas.root:
            txt = read(f, 80_000)
            sec = re.search(r"(?ims)^#+\s*(getting started|setup|installation|install|local development|running locally|quick ?start|development)\b.*?$(.*?)(?=^#+\s|\Z)", txt)
            if sec:
                cmds = re.findall(r"```(?:bash|sh|shell|console|zsh)?\n(.*?)```", sec.group(2), re.S)
                steps = []
                for block in cmds[:4]:
                    for line in block.strip().splitlines()[:6]:
                        line = line.lstrip("$ ").strip()
                        if line and not line.startswith("#"):
                            steps.append({"step": "From README", "command": line, "notes": sec.group(1)})
                atlas.setup[:0] = steps


def detect_hotspots(atlas, files):
    churn = Counter()
    if os.path.isdir(os.path.join(atlas.root, ".git")):
        try:
            out = subprocess.run(["git", "-C", atlas.root, "log", "--since=6.months", "--name-only", "--pretty=format:"],
                                 capture_output=True, text=True, timeout=60).stdout
            churn = Counter(l for l in out.splitlines() if l.strip() and os.path.splitext(l)[1] in CODE_EXT)
        except Exception:
            pass
    todos = {}
    for f in files:
        if os.path.splitext(f)[1] in CODE_EXT:
            c = len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", read(f, 200_000)))
            if c:
                todos[atlas.rel(f)] = c
    score = Counter()
    for p, c in churn.items():
        score[p] += c * 2
    for p, c in todos.items():
        score[p] += c
    for p, _ in score.most_common(12):
        bits = []
        if churn.get(p):
            bits.append(f"{churn[p]} commits in 6 months")
        if todos.get(p):
            bits.append(f"{todos[p]} TODO/FIXME")
        atlas.hotspots.append({"path": p, "reason": ", ".join(bits)})


def detect_code_layout(atlas, files):
    top = Counter()
    for f in files:
        r = atlas.rel(f)
        if "/" in r and os.path.splitext(f)[1] in CODE_EXT:
            top[r.split("/")[0]] += 1
    known = {m["path"].split("/")[0] for m in atlas.modules}
    for d, c in top.most_common(15):
        if d not in known and not any(m["path"] == d for m in atlas.modules):
            atlas.modules.append({"path": d, "purpose": f"{c} code files — purpose to confirm", "depends_on": []})
    for f in files:
        r = atlas.rel(f)
        if re.search(r"(^|/)(src/)?app/(layout|page)\.(t|j)sx?$|(^|/)(src/)?pages/(_app|index)\.(t|j)sx?$|(^|/)(src/)?main\.(t|j)sx?$|(^|/)(main|app|manage|wsgi|asgi)\.py$|(^|/)cmd/[\w-]+/main\.go$|(^|/)Program\.cs$|(^|/)middleware\.(t|j)s$", r):
            if len(atlas.entry_points) < 30:
                atlas.entry_points.append({"path": r, "purpose": "middleware (often auth)" if "middleware" in r else "entry point"})


def git_remote(root):
    cfg = os.path.join(root, ".git", "config")
    m = re.search(r'\[remote "origin"\][^\[]*url\s*=\s*(\S+)', read(cfg))
    if not m:
        return ""
    url = m.group(1)
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    url = re.sub(r"https://[^@/]+@", "https://", url)
    return re.sub(r"\.git$", "", url)


# --------------------------------------------------------------------------- post-processing
def finalize(atlas):
    # client -> gateway / identity inference
    clients = [n for n in atlas.nodes.values() if n["layer"] == "client"]
    gateways = [n for n in atlas.nodes.values() if n["layer"] == "edge" and n["kind"] in ("gateway", "cdn")]
    idps = [n for n in atlas.nodes.values() if n["layer"] == "identity"]
    services = [n for n in atlas.nodes.values() if n["layer"] == "compute" and n["kind"] == "service"]
    for c in clients:
        has_out = any(e["from"] == c["id"] and atlas.nodes[e["to"]]["layer"] in ("edge", "compute") for e in atlas.edges.values())
        if not has_out:
            for g in [g for g in gateways if g["kind"] == "gateway"] or services[:3]:
                atlas.edge(c["id"], g["id"], "calls", "HTTPS (inferred)", "inferred")
        if idps and not any(e["from"] == c["id"] and e["kind"] == "authenticates" for e in atlas.edges.values()):
            atlas.edge(c["id"], idps[0]["id"], "authenticates", "sign-in (inferred)", "inferred")
    # merge duplicate generic cognito nodes into declared user pool
    pools = [n for n in idps if n["id"] != "cognito" and "Cognito" in n.get("tech", "")]
    if "cognito" in atlas.nodes and pools:
        target = pools[0]["id"]
        target_node = atlas.nodes[target]
        for s in atlas.nodes["cognito"]["source"]:
            if s not in target_node["source"]:
                target_node["source"].append(s)
        for k in list(atlas.edges):
            e = atlas.edges.pop(k)
            if e["from"] == "cognito":
                e["from"] = target
            if e["to"] == "cognito":
                e["to"] = target
            if e["from"] != e["to"]:
                atlas.edges[(e["from"], e["to"], e["kind"])] = e
        del atlas.nodes["cognito"]
    # generic SDK nodes shadowed by specific resources
    for gid, tech in (("dynamodb", "DynamoDB"), ("s3", "S3"), ("sqs", "SQS"), ("sns", "SNS")):
        if gid in atlas.nodes and any(n["id"] != gid and n.get("tech") == tech for n in atlas.nodes.values()):
            covered = {e["from"] for e in atlas.edges.values() if atlas.nodes[e["to"]].get("tech") == tech and e["to"] != gid}
            users = sorted({e["from"] for e in atlas.edges.values() if e["to"] == gid} - covered)
            for k in [k for k in atlas.edges if gid in (k[0], k[1])]:
                del atlas.edges[k]
            del atlas.nodes[gid]
            if users:
                atlas.gaps.append(f"{', '.join(users)} use{'s' if len(users) == 1 else ''} the {tech} SDK — confirm which specific {tech} resources each touches.")
    # an inferred edge duplicating a declared one between the same pair adds noise
    declared_pairs = {(e["from"], e["to"]): e for e in atlas.edges.values() if e["confidence"] == "declared"}
    for k in [k for k, e in atlas.edges.items() if e["confidence"] == "inferred" and (e["from"], e["to"]) in declared_pairs]:
        e = atlas.edges.pop(k)
        d = declared_pairs[(e["from"], e["to"])]
        if e["label"] and e["label"] not in d["label"]:
            d["label"] = (d["label"] + " · " + e["label"]).strip(" ·")
    # owner guess for entities
    for ent in atlas.entities:
        if not ent.get("owner"):
            writers = sorted({e["from"] for e in atlas.edges.values() if e["to"] == ent["store"] and e["kind"] in ("writes", "reads-writes")})
            ent["owner"] = ", ".join(writers[:3])
    # gaps
    if not idps:
        atlas.gaps.append("No identity provider detected — how do users authenticate?")
    if not any(atlas.found[k] for k in ("serverless", "cloudformation", "terraform", "cdk", "kubernetes")):
        atlas.gaps.append("No infrastructure-as-code found — where is production infrastructure defined?")
    if clients and not gateways and not services:
        atlas.gaps.append("Frontend found but no backend/API detected — which API does it call?")
    for n in atlas.nodes.values():
        if n["confidence"] == "inferred" and "Generic" in n.get("notes", ""):
            atlas.gaps.append(f"'{n['label']}' is a generic SDK-derived node — replace with specific resources.")
    orphans = [n["id"] for n in atlas.nodes.values() if not any(n["id"] in (e["from"], e["to"]) for e in atlas.edges.values())]
    if orphans:
        atlas.gaps.append(f"Unconnected nodes (find their callers): {', '.join(orphans[:12])}")
    atlas.gaps.append("Environment URLs (dev/stage/prod) — not derivable from code.")


def build(root):
    atlas = Atlas(root)
    files = walk(atlas.root)
    owners_by_dir, sdk_users = {}, defaultdict(list)
    detect_packages(atlas, files, owners_by_dir, sdk_users)
    detect_serverless(atlas, files, owners_by_dir)
    detect_cfn(atlas, files, owners_by_dir)
    detect_terraform(atlas, files)
    detect_cdk(atlas, files)
    detect_compose(atlas, files)
    detect_k8s(atlas, files)
    resolve_sdk_users(atlas, sdk_users, owners_by_dir)
    detect_openapi(atlas, files)
    detect_prisma(atlas, files)
    detect_config(atlas, files)
    detect_ci(atlas, files)
    detect_context(atlas, files)
    detect_hotspots(atlas, files)
    detect_code_layout(atlas, files)
    finalize(atlas)

    name = os.path.basename(atlas.root)
    rp = os.path.join(atlas.root, "package.json")
    if os.path.exists(rp):
        try:
            name = json.loads(read(rp)).get("name") or name
        except Exception:
            pass
    seen = set()
    setup = [s for s in atlas.setup if not (s["command"] in seen or seen.add(s["command"]))]
    out = {
        "meta": {"name": name, "summary": "", "repo": git_remote(atlas.root), "root": atlas.root,
                 "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "stack": atlas.stack, "scanner_version": SCANNER_VERSION, "files_scanned": len(files)},
        "nodes": list(atlas.nodes.values()),
        "edges": list(atlas.edges.values()),
        "flows": [],
        "apis": atlas.apis,
        "auth": {"summary": "", "providers": [n["id"] for n in atlas.nodes.values() if n["layer"] == "identity"],
                 "token": "", "verified_at": sorted(atlas.verified_at), "roles": atlas.auth_roles,
                 "service_identities": [], "hints": sorted(atlas.auth_hints)},
        "data": {"entities": atlas.entities, "relations": atlas.relations},
        "code": {"layout": "", "entry_points": atlas.entry_points[:40], "modules": atlas.modules},
        "run": {"prerequisites": sorted(set(atlas.prereq)), "setup": setup[:30], "environments": [],
                "config": sorted(({**c, "where": ", ".join(c["where"])} for c in atlas.config.values()), key=lambda c: c["key"])[:150],
                "pipeline": atlas.pipeline},
        "operate": {"logs": [], "metrics": [], "alarms": [], "runbooks": []},
        "context": {"glossary": [], "owners": atlas.owners, "decisions": atlas.decisions, "hotspots": atlas.hotspots},
        "tour": [], "first_tasks": [], "gaps": list(dict.fromkeys(atlas.gaps)),
    }
    return out, atlas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("-o", "--out", help="default: <repo>/docs/onboarding/atlas.json")
    ap.add_argument("--no-root", action="store_true", help="omit absolute root path (for sharing)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing enriched atlas")
    a = ap.parse_args()
    if not os.path.isdir(a.repo):
        sys.exit(f"not a directory: {a.repo}")
    if not a.out:
        a.out = os.path.join(os.path.abspath(a.repo), "docs", "onboarding", "atlas.json")
    if os.path.exists(a.out) and not a.force:
        try:
            with open(a.out, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
        if (old.get("meta") or {}).get("summary") or old.get("flows") or old.get("tour"):
            sys.exit(f"{a.out} already has enrichment (summary/flows/tour). "
                     f"Scan to a temp path with -o to diff, or pass --force to overwrite.")
    out, atlas = build(a.repo)
    if a.no_root:
        out["meta"].pop("root", None)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    layers = Counter(n["layer"] for n in out["nodes"])
    print(f"atlas -> {a.out}", file=sys.stderr)
    print(f"  files scanned: {out['meta']['files_scanned']}  stack: {', '.join(out['meta']['stack']) or '—'}", file=sys.stderr)
    print(f"  nodes: {len(out['nodes'])} ({', '.join(f'{k}={v}' for k, v in layers.items())})  edges: {len(out['edges'])}", file=sys.stderr)
    print(f"  apis: {len(out['apis'])}  entities: {len(out['data']['entities'])}  config keys: {len(out['run']['config'])}  pipeline: {len(out['run']['pipeline'])}", file=sys.stderr)
    print(f"  detectors hit: {dict(atlas.found) or 'none (no IaC)'}  yaml: {'yes' if HAVE_YAML else 'NO — pip install pyyaml'}", file=sys.stderr)
    print(f"  gaps: {len(out['gaps'])}", file=sys.stderr)
    ids = [f"{n['id']}({n['layer']})" for n in out["nodes"]]
    print(f"  node ids: {', '.join(ids[:80])}{' …' if len(ids) > 80 else ''}", file=sys.stderr)
    for e in out["edges"][:60]:
        print(f"  edge: {e['from']} -[{e['kind']}]-> {e['to']}", file=sys.stderr)
    if len(out["edges"]) > 60:
        print(f"  … {len(out['edges']) - 60} more edges in the JSON", file=sys.stderr)


if __name__ == "__main__":
    main()
