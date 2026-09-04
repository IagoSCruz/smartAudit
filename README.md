# SmartAudit

SaaS multi-tenant para conciliação e auditoria de fretes. O sistema compara
CT-es e NF-es com as tabelas contratadas das transportadoras para identificar
cobranças divergentes.

## Estado atual

A fundação Django e a fronteira multi-tenant da API estão prontas, com:

- settings separados para base, desenvolvimento local e produção;
- usuário customizado com login por e-mail;
- tenants e memberships com papéis `admin`, `operator` e `viewer`;
- modelos abstratos para auditoria temporal e escopo por tenant;
- endpoint de saúde em `/health/` e Django Admin em `/admin/`;
- API Django Ninja em `/api/`, JWT em `/api/auth/login` e `/api/auth/refresh`;
- tenant resolvido por sessão ou `X-Tenant-ID`, sempre validado por membership;
- ingestão idempotente e segura de CT-e/NF-e, com XML original e dados normalizados;
- listagem e detalhe de documentos sempre isolados pelo tenant autenticado;
- PostgreSQL, RabbitMQ, Redis e MinIO reproduzíveis via Compose.

As decisões arquiteturais e o roadmap canônico ficam na seção **10. Aplicação
do Blueprint: SmartAudit** de
[`docs/blueprint-saas-django.md`](docs/blueprint-saas-django.md).

## Desenvolvimento local

Requisitos: Python 3.13, [uv](https://docs.astral.sh/uv/), Docker Compose e
Node.js (para hooks de commit).

```bash
cp .env.example .env
docker compose --env-file .env -f compose/compose.yaml up -d
set -a
source .env
set +a
uv sync --locked
npm install  # ativa os hooks de commit (Husky + Commitlint)
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Validação rápida:

```bash
uv run python manage.py check
uv run python manage.py test
uv run python manage.py makemigrations --check --dry-run
npx commitlint --from=HEAD~1
```

O padrão de mensagens de commit segue o Conventional Commits com escopos mapeados para os bounded contexts do sistema. Consulte os detalhes em [`docs/commitlint.md`](docs/commitlint.md).

Com as variáveis da `.env`, o ambiente local usa PostgreSQL. Sem `POSTGRES_DB`,
os comandos locais usam SQLite apenas para bootstrap e testes rápidos. Produção
exige explicitamente chave secreta, hosts, credenciais PostgreSQL, broker Celery
e result backend; os settings falham cedo quando algum valor obrigatório falta.

## API de documentos

Depois do login, envie o access token e o tenant autorizado em todas as rotas
protegidas. O upload é multipart e não aceita `tenant_id` como fonte de escopo:

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer <access-token>" \
  -H "X-Tenant-ID: <tenant-id>" \
  -F "uploaded_file=@documento.xml"
```

A documentação OpenAPI interativa está disponível em `/api/docs`.
