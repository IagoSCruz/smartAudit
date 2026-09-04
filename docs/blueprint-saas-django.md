# Blueprint Arquitetural: Sistemas Escaláveis com Django + IA Assistida

<aside>
📌

**Blueprint Arquitetural Reutilizável** — Documento de referência para construção de sistemas SaaS multi-tenant escaláveis com Python/Django, orquestração de IA (LangChain/LangGraph), processamento assíncrono (Celery/RabbitMQ), banco PostgreSQL, observabilidade (Prometheus/Grafana/Sentry/LangSmith) e deploy em Docker Swarm/VPS — destilado a partir da construção real de um SaaS de mentoria com IA.

**Versão:** 1.0 — **Data:** 2026-04-27

</aside>

---

# 1. Sumário Executivo

Este blueprint condensa os padrões arquiteturais, decisões técnicas e workflows de desenvolvimento extraídos da construção real de uma plataforma SaaS multi-tenant de IA generativa (chat com agentes treinados via RAG sobre conteúdo proprietário). O sistema-fonte foi construído ao longo de 60+ sprints incrementais, com mais de 200 prompts estruturados de desenvolvimento assistido por IA, e atravessou todas as fases canônicas de um produto de software: MVP em SQLite, migração para PostgreSQL containerizado, decomposição em apps Django por bounded context, introdução de orquestração de agentes com LangGraph, processamento assíncrono via Celery/RabbitMQ para tarefas pesadas (treinamento de RAG, transcrição de vídeo, processamento em massa de solicitações), integração com múltiplos provedores de LLM com fallback, observabilidade via Sentry self-hosted + Flower + dashboards customizados, e deploy em VPS via Docker Swarm com Easy Panel.

## 1.1 Filosofia de Construção

| **Princípio** | **Implicação prática** |
| --- | --- |
| **Recursos nativos primeiro** | CBVs, ORM, signals, forms, admin, sessions, mail backend — antes de adicionar dependências. |
| **Design system inviolável** | HTML estático de referência. Nenhum componente novo sem entrar nele primeiro. |
| **Idempotência por design** | Tasks Celery, webhooks, jobs cron, eventos de pagamento — sempre seguros para reprocessamento. |
| **Observabilidade desde o dia 1** | token_count, message_cost, time_saved_minutes registrados em cada mensagem. Métricas viram produto. |

## 1.2 Stack de Referência

| **Camada** | **Tecnologia** | **Papel** |
| --- | --- | --- |
| Banco | PostgreSQL 16 (com migração planejada de SQLite) | OLTP + extensões (pgvector opcional) |
| Async | Celery 5.6+, Celery Beat, Flower | Tasks pesadas, agendamentos, monitoria |
| Vector store | FAISS (in-disk por agente) → pgvector quando escalar | Retrieval semântico |
| Observabilidade | Sentry self-hosted, Prometheus + Grafana, LangSmith, MKDocs | Erros, métricas, tracing IA, docs |
| Frontend | Django Templates + Bootstrap-derivado + HTMX/SSE para streaming | SSR + interatividade pontual, sem SPA pesado |

---

# 2. Princípios Fundamentais

Estes são os princípios não-negociáveis identificados. Quando há conflito entre simplicidade e "escalabilidade futura imaginada", a simplicidade vence — desde que o caminho de upgrade esteja mapeado.

## 2.1 Princípios de Modelagem

<aside>
⚖️

**P1 — Bounded Context = Django App.** Toda entidade de domínio fica em uma app dedicada. URLs, views, models, signals, templates e admin de cada contexto convivem na mesma pasta. Cross-context só por FK explícito ou service.

</aside>

<aside>
⚖️

**P2 — Todo model herda de `BaseModel` com `created_at` e `updated_at`.** Auditoria temporal não é opcional. Adicionado uma vez como abstract, propagado para sempre.

</aside>

<aside>
⚖️

**P3 — Login por email, sem username.** `AbstractUser` com `USERNAME_FIELD = 'email'` desde a sprint 1 — antes do primeiro `migrate`. Mexer depois é doloroso.

</aside>

<aside>
⚖️

**P4 — `school_id` (ou `tenant_id`) em toda tabela do domínio.** Multi-tenancy com shared schema funciona apenas se a FK existir em 100% dos registros tenant-scoped. Sem exceção.

</aside>

<aside>
⚖️

**P5 — Signals em `signals.py` na app que dispara o evento, conectados em `apps.py`.** Nunca em `models.py`. Nunca cross-app sem evento explícito.

</aside>

## 2.2 Princípios de IA & Custo

<aside>
🔥

**P6 — Imports por provider, sempre.** Nunca `from langchain.embeddings import ...` ou `from langchain.chat_models import ...`. Use `langchain_openai`, `langchain_community`, `langchain_text_splitters`. Imports legados são depreciados entre minor versions.

</aside>

<aside>
🔥

**P7 — API keys via env var, nunca como parâmetro.** Os providers leem `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, etc., automaticamente. Passar como parâmetro vira segredo em log/stacktrace.

</aside>

<aside>
🔥

**P8 — Custo da mensagem é calculado e persistido NO ATO DA ESCRITA.** Não recalcule depois — o preço por 1M tokens muda. Snapshot no momento da geração é a única fonte de verdade.

</aside>

<aside>
🔥

**P9 — Top-K limitado e chunking conservador.** Retrieval de 5 chunks de 1000 tokens com overlap 200. Mais que isso aumenta custo sem ganho proporcional de qualidade.

</aside>

<aside>
🔥

**P10 — Fallback de provider obrigatório em produção.** Se o LLM primário cai, o agente cai. Configure ao menos um secundário (OpenRouter espelhando OpenAI é o caminho de menor atrito).

</aside>

## 2.3 Princípios Operacionais

<aside>
⚙️

**P11 — Tasks pesadas vão para Celery, sem exceção.** Treinamento de RAG, transcrição de vídeo, envio de emails em massa, processamento de webhooks. Nunca em request síncrona.

</aside>

<aside>
⚙️

**P12 — Idempotência em webhooks e tasks.** Toda task recebe um ID único; toda integração webhook tem chave de deduplicação (event_id do provedor). Reprocessar nunca pode duplicar efeito.

</aside>

<aside>
⚙️

**P13 — Status de processamento explícitos.** `pending → pending_processing → processed/failed`. Nunca booleano. Sempre auditável.

</aside>

<aside>
⚙️

**P14 — Subdomínio por serviço operacional, com auth.** `flower.dominio`, `rabbitmq.dominio`, `docs.dominio`, `sentry.dominio`. Senhas geradas, nunca defaults.

</aside>

<aside>
⚙️

**P15 — Modal &gt; `alert()` nativo.** Confirmações destrutivas (treinar IA, deletar chat) usam modal do design system. `window.alert` é dívida desde o dia 1.

</aside>

## 2.4 Princípios de Desenvolvimento Assistido por IA

<aside>
🧠

**P16 — Prompt sempre referencia `@PRD.md`, `@design_system/...` e o código atual.** Nunca peça uma feature ao agente sem mandar ele ler as três fontes. "Greenfield assumption" é o pior anti-padrão.

</aside>

<aside>
🧠

**P17 — Plan-then-execute em prompts separados.** Use modelo "raciocinador" (Opus/o-class) para planejar e atualizar o PRD; modelo "executor" para implementar a sprint marcada.

</aside>

<aside>
🧠

**P18 — Ambiguidades são resolvidas no PRD, não no código.** Se o agente encontrou algo dúbio, ele decide e DOCUMENTA a decisão no PRD. Código não é o lugar para resolver semântica.

</aside>

<aside>
🧠

**P19 — Definition of Done = `[x]` no checklist da sprint.** Marcar a checkbox é o ritual. Sem isso, sprint não fechou.

</aside>

---

# 3. Arquitetura de Referência

## 3.1 Visão de Sistema

```mermaid
graph TB
    subgraph "Cliente"
        WEB["Web (Django Templates + SSE)"]
        EMBED["Chat Embedável (iframe/widget)"]
        MOB["PWA / WebView"]
    end
    subgraph "Edge"
        TRA["Traefik (TLS, routing, rate-limit)"]
    end
    subgraph "Aplicação (Docker Swarm)"
        APP1["Django App replica 1"]
        APP2["Django App replica N"]
        WORKER["Celery Workers"]
        BEAT["Celery Beat (scheduler)"]
        FLOWER["Flower (admin)"]
    end
    subgraph "Stateful"
        PG["PostgreSQL (primary + replica opcional)"]
        REDIS["Redis (cache + sessions)"]
        RMQ["RabbitMQ (broker)"]
        VOL["Volume media/ (uploads + FAISS index)"]
    end
    subgraph "Observabilidade"
        SENTRY["Sentry (self-hosted)"]
        PROM["Prometheus + Grafana"]
        LS["LangSmith (tracing IA)"]
        DOCS["MKDocs"]
    end
    subgraph "Externo"
        OAI["OpenAI / OpenRouter"]
        STRIPE["Stripe / Hubla"]
        EMAIL["SMTP"]
        GCAL["Google APIs (OAuth + Calendar + Drive)"]
        MCP["MCP servers (GitHub, etc.)"]
    end
    WEB --> TRA
    EMBED --> TRA
    MOB --> TRA
    TRA --> APP1
    TRA --> APP2
    APP1 --> PG
    APP1 --> REDIS
    APP1 --> RMQ
    APP1 --> VOL
    APP2 --> PG
    APP2 --> REDIS
    APP2 --> RMQ
    APP2 --> VOL
    RMQ --> WORKER
    BEAT --> RMQ
    WORKER --> PG
    WORKER --> VOL
    WORKER --> OAI
    APP1 --> OAI
    APP1 --> STRIPE
    APP1 --> EMAIL
    APP1 --> GCAL
    APP1 --> MCP
    APP1 -.errors.-> SENTRY
    APP1 -.metrics.-> PROM
    APP1 -.traces.-> LS
    WORKER -.errors.-> SENTRY
    WORKER -.traces.-> LS
```

## 3.2 Camadas Lógicas

```mermaid
graph LR
    URL["URLConf"] --> VIEW["CBV + Mixins de acesso"]
    VIEW --> FORM["Forms / Validators"]
    VIEW --> SVC["Service Layer (orquestração)"]
    SVC --> ORM["Models / Managers"]
    SVC --> AI["AI Engine (LangGraph + RAG)"]
    SVC --> TASK["Celery Task delegator"]
    SVC --> INT["Integration adapters"]
    AI --> VS["Vector store por agente"]
    AI --> LLM["LLM provider abstraction"]
    LLM --> PRIMARY["Primary provider"]
    LLM --> FALLBACK["Fallback provider"]
    INT --> PAY["Payment adapter (Stripe/Hubla)"]
    INT --> WEBHK["Webhook handlers (idempotente)"]
    INT --> MCP["MCP client"]
    SIG["Signals"] -.async events.-> TASK
    ORM --> DB[("PostgreSQL")]
```

## 3.3 Estrutura de Diretórios Canônica

```
project_root/
├── compose/
│   ├── django/Dockerfile
│   ├── celery/Dockerfile
│   ├── traefik/dynamic/
│   └── postgres/init/
├── docker-compose.yml          # dev
├── docker-stack.yml            # swarm prod
├── core/                       # settings, celery_app, urls raiz, asgi/wsgi
│   ├── settings/{base,dev,prod}.py
│   ├── celery.py
│   └── urls.py
├── apps/
│   ├── accounts/               # User customizado, login email, perfil
│   ├── tenants/                # School/Organization, plano, billing context
│   ├── catalog/                # Course/Product (entidade vendável)
│   ├── agents/                 # Agent, AgentDocument, AgentSkill, AgentMCP
│   ├── conversations/          # ChatSession, ChatMessage, share links
│   ├── enrollments/            # Vínculos student↔course/agent
│   ├── credits/                # CreditWallet, CreditPackage, transactions
│   ├── billing/                # Subscription, Invoice, payment provider abstraction
│   ├── webhooks/               # Inbound webhook routing + idempotency
│   ├── activities/             # Quiz/Flashcards/Exercises (gamification)
│   ├── gamification/           # Trophies, ranking, competitions
│   ├── notifications/          # Push subscriptions, scheduled, recurring
│   ├── reports/                # Bug reports, suggestions
│   ├── integrations/           # Google OAuth, Drive, MCP registry
│   └── landing/                # Landing pública, planos
├── ai/                         # AI engine compartilhada
│   ├── pipelines/              # RAG ingestion, retrieval graphs
│   ├── providers/              # Adapters (OpenAI, OpenRouter, ...)
│   ├── prompts/                # System prompt builders
│   ├── tools/                  # MCP/skills tool wrappers
│   └── tracing/                # LangSmith hooks
├── design_system/
│   └── design-system.html      # Referência viva, copiada como golden
├── templates/
├── static/
├── media/                      # PESADO em volume — backup separado
│   └── agents/<id>/{documents,faiss_index}/
├── docs/                       # MKDocs
├── cron/                       # Cron jobs transitórios (ver §6)
├── PRD.md                      # Source of truth do produto
├── AGENTS.md                   # Guia para agentes de codificação
└── CLAUDE.md                   # Atalhos para Claude Code
```

---

# 4. Padrões por Domínio

Cada padrão segue a estrutura: **Nome → Problema → Solução → Quando aplicar / Quando NÃO aplicar → Exemplo → Trade-offs**.

## 4.1 Domínio: Arquitetura e Modelagem

### 🟦 P-ARQ-01 — App-per-Bounded-Context

- **Problema:** Models e views se tornam um "god app" gigantesco em projetos Django reais. Migrações ficam imprevisíveis, signals viram macarrão, refatorar uma feature toca 80% do código.
- **Solução:** Cada bounded context (entidade central + agregados próximos) vira uma app Django independente, com seus próprios `models.py`, `views.py`, `urls.py`, `forms.py`, `signals.py`, `admin.py`, `apps.py`, `tests/` e `templates/<app>/`. Apps se referenciam **apenas via FK** ou via service layer.
- **Quando aplicar:** Sempre. Mesmo um MVP começa com 4-5 apps (`accounts`, `tenants`, `catalog`, `<core_domain>`).
- **Quando NÃO aplicar:** Em scripts utilitários ou comandos one-shot. Não force um bounded context onde só há um helper.
- **Exemplo:**

```python
# apps/agents/apps.py
from django.apps import AppConfig

class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agents'
    label = 'agents'

    def ready(self):
        from . import signals  # noqa: F401
```

- **Trade-offs:** Mais boilerplate inicial; precisa cuidar de imports circulares (resolva com FK como string `'tenants.School'`). Em compensação, deletar/refatorar uma feature vira tocar 1 pasta.

### 🟦 P-ARQ-02 — Abstract `BaseModel` com Audit Fields

- **Problema:** Sem `created_at`/`updated_at` consistentes, debugging de produção e auditoria viram arqueologia.
- **Solução:** Um abstract base model em uma app `core` (ou `commons`), herdado por TODO model do projeto.
- **Quando aplicar:** Em 100% dos models de domínio. Tabelas through M2M também.
- **Quando NÃO aplicar:** Em models internos do Django (`auth_*`, `django_session`).
- **Exemplo:**

```python
# apps/core/models.py
from django.db import models

class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ('-created_at',)
```

- **Trade-offs:** Adiciona 2 colunas em todas as tabelas (storage desprezível). Indexar `created_at` desde o início evita migration cara depois quando forem rodar relatórios.

### 🟦 P-ARQ-03 — Custom User com `email` como `USERNAME_FIELD`

- **Problema:** Trocar de `username` para `email` depois do primeiro `migrate` é um pesadelo. O default do Django força um username que ninguém usa em SaaS B2B/B2C modernos.
- **Solução:** No início do projeto (antes do primeiro `migrate`), criar `accounts/models.py` com `AbstractUser` customizado, definir `USERNAME_FIELD = 'email'`, registrar `AUTH_USER_MODEL = 'accounts.User'` em settings, e implementar um `EmailBackend` para autenticação.
- **Quando aplicar:** Em todo projeto greenfield onde o usuário se identifica por email. (≈100% dos SaaS modernos.)
- **Quando NÃO aplicar:** Quando você está estendendo um Django legado já com migrações em produção — neste caso, considere usar OneToOne `Profile` em vez de trocar `User`.
- **Exemplo:**

```python
# apps/accounts/models.py
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self._create_user(email, password, **extra)

class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(max_length=16, choices=[('admin','Admin'), ('member','Member')], default='member')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()
```

```python
# apps/accounts/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        email = (username or kwargs.get('email') or '').lower().strip()
        try:
            user = UserModel.objects.get(email=email)
        except UserModel.DoesNotExist:
            UserModel().set_password(password)  # mitigate timing
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
```

- **Trade-offs:** Inviabiliza login social com username. Compensação: `email` é o universal modern login.

### 🟦 P-ARQ-04 — Service Layer Leve (não anêmico)

- **Problema:** Lógica de negócio em CBV vira caos quando uma única ação dispara 4 efeitos (criar registro + cobrar crédito + enviar email + emitir webhook). Lógica em manager fica acoplada a 1 model.
- **Solução:** Para fluxos com >1 efeito ou >1 model, criar um módulo `services.py` (ou pasta `services/`) na app, com funções puras que recebem entidades/IDs e retornam resultados. CBVs delegam para services.
- **Quando aplicar:** Onboarding de aluno, processamento de webhook de pagamento, treinamento de agente, geração de atividade IA.
- **Quando NÃO aplicar:** CRUD trivial. `CreateView` que só salva 1 form não precisa de service.
- **Exemplo:**

```python
# apps/enrollments/services.py
from django.db import transaction
from apps.accounts.models import User
from apps.accounts.services import create_user_with_random_password
from apps.enrollments.models import Enrollment
from apps.notifications.tasks import send_welcome_email_task

@transaction.atomic
def enroll_or_invite(*, school, course, email: str, name: str | None = None) -> Enrollment:
    user, created = User.objects.get_or_create(email=email.lower(), defaults={'first_name': name or ''})
    if created:
        plain_password = create_user_with_random_password(user)
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user, course=course, school=school,
        defaults={'is_active': True},
    )
    send_welcome_email_task.delay(
        user_id=user.id, school_id=school.id, course_id=course.id,
        is_new_account=created,
        plain_password=plain_password if created else None,
    )
    return enrollment
```

- **Trade-offs:** Mais um arquivo por app. Em compensação, testes ficam triviais (chamar função pura) e CBV fica em 5 linhas.

### 🟦 P-ARQ-05 — Mixins de Acesso para Multi-Tenant Isolation

- **Problema:** Filtros de tenant esquecidos numa query são o vetor de vazamento cross-tenant #1.
- **Solução:** Mixins de CBV que: (a) garantem `LoginRequiredMixin`, (b) restringem `get_queryset` ao tenant do usuário, (c) validam ownership em `get_object`. Aplicar em TODA view tenant-scoped por convenção.
- **Exemplo:**

```python
# apps/tenants/mixins.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

class SchoolScopedMixin(LoginRequiredMixin):
    school_lookup = 'school'  # FK name in queryset model

    def get_school(self):
        return getattr(self.request.user, 'owned_school', None)

    def get_queryset(self):
        qs = super().get_queryset()
        school = self.get_school()
        if school is None:
            raise PermissionDenied
        return qs.filter(**{self.school_lookup: school})
```

- **Trade-offs:** Acoplamento à convenção (`school` como nome da FK). Vale a disciplina.

### 🟦 P-ARQ-06 — `signals.py` por App + Conexão em `apps.ready()`

- **Problema:** Signals em `models.py` causam import cycles e disparam em testes que não querem o efeito colateral.
- **Solução:** Cada app tem seu `signals.py`. Receivers usam `@receiver(...)` decorator. Conexão em `AppConfig.ready()`. Em testes, use `@factory.django.mute_signals` ou `mock.patch`.
- **Trade-offs:** Mais um arquivo. Em compensação, signals viram explícitos e testáveis.

### 🟦 P-ARQ-07 — `purchase_url` / `external_id` para Integrações

- **Problema:** Sistema vende produtos que vivem fora dele (cursos hospedados em Hubla/Kiwify/Hotmart, repos no GitHub, vídeos em Drive).
- **Solução:** Toda entidade que espelha algo externo recebe campos `external_id` (ID na plataforma origem) e `purchase_url` (link público). Webhooks usam o `external_id` para casar evento com entidade local.
- **Exemplo:** `Course.hubla_product_id`, `Course.kiwify_product_id`, `Project.github_repo_url`.

### 🟦 P-ARQ-08 — Status Enum com Valores Explícitos

- **Problema:** Booleanos não escalam (`is_processed`, `is_paid`, `is_approved`, `is_failed` na mesma tabela = combinatória ruim).
- **Solução:** `TextChoices` com transições explícitas. Documente o grafo de estados.
- **Exemplo:**

```python
class AccessRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        APPROVED = 'approved', 'Aprovado'
        DENIED = 'denied', 'Negado'
        PENDING_PROCESSING = 'pending_processing', 'Pendente de Processamento'
        PROCESSED = 'processed', 'Processado'
        FAILED = 'failed', 'Falhou'
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
```

## 4.2 Domínio: IA e Orquestração com LangChain/LangGraph

### 🟪 P-AI-01 — Provider-Separated Imports (versionamento)

- **Problema:** O ecossistema LangChain quebra APIs entre minor versions. Imports legados (`langchain.embeddings`, `langchain.chat_models`) viram dívida instantânea.
- **Solução:** Pinar versões mínimas no `requirements.txt` e usar **somente** os pacotes por provider. Auditar a cada início de sprint que toca IA.
- **Exemplo:**

```python
# requirements.txt (versões mínimas)
langchain>=1.2.0
langchain-community>=0.4.0
langchain-openai>=1.1.0
langchain-text-splitters>=1.1.0
langgraph>=1.1.0
openai>=2.0.0
faiss-cpu>=1.13.0
tiktoken>=0.12.0
pypdf>=6.0.0
```

```python
# ai/providers/openai_provider.py
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
```

- **Trade-offs:** Mais imports espalhados. Compensação: zero risco de deprecação silenciosa.

### 🟪 P-AI-02 — RAG Pipeline em 5 etapas, com FAISS por agente

- **Problema:** Pipeline RAG vira spaghetti se você acopla loading, splitting, embedding e indexação na mesma função.
- **Solução:** Pipeline canônico de 5 etapas, cada uma uma função pura. Index FAISS persiste em `media/agents/<agent_id>/faiss_index/`.
- **Etapas:** `load → split → embed → index → persist`.
- **Exemplo:**

```python
# ai/pipelines/rag_ingestion.py
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader, CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

LOADERS = {
    '.pdf': PyPDFLoader,
    '.md':  TextLoader,
    '.txt': TextLoader,
    '.csv': CSVLoader,
    '.srt': TextLoader,
}

def ingest_documents(agent_id: int, file_paths: list[Path], embeddings_model: str = 'text-embedding-3-small'):
    docs = []
    for path in file_paths:
        Loader = LOADERS[path.suffix.lower()]
        docs.extend(Loader(str(path)).load())
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    embeddings = OpenAIEmbeddings(model=embeddings_model)
    index = FAISS.from_documents(chunks, embeddings)
    out = Path(f'media/agents/{agent_id}/faiss_index')
    out.mkdir(parents=True, exist_ok=True)
    index.save_local(str(out))
    return {'chunks': len(chunks), 'path': str(out)}
```

- **Trade-offs:** FAISS é local e por agente — não escala horizontalmente direto. Quando passar de poucas centenas de agentes ou MB-de-índice, migre para pgvector ou Qdrant; o adapter já está pronto graças à LangChain.

### 🟪 P-AI-03 — System Prompt como Builder Dinâmico

- **Problema:** Hardcoded system prompts viram muralha quando precisam mudar por agente, por escola ou por skill ativa.
- **Solução:** Função builder que monta o system prompt a cada interação a partir de campos do agente + contexto recuperado + skills ativas + nome do usuário.
- **Exemplo:**

```python
# ai/prompts/builder.py
from textwrap import dedent

def build_system_prompt(*, agent, retrieved_context: str, user_name: str | None, active_skills: list[str]) -> str:
    parts = [
        f'Você é {agent.name}, mentor de IA do contexto "{agent.context_name}".',
        '',
        '## Personalidade & Tom de voz',
        agent.personality.strip(),
        '',
        '## Instruções de comportamento',
        agent.behavior_instructions.strip(),
    ]
    if user_name:
        parts += ['', f'Trate o usuário pelo primeiro nome quando apropriado: {user_name}.']
    if active_skills:
        parts += ['', '## Skills disponíveis nesta sessão', *(f'- {s}' for s in active_skills)]
    parts += [
        '',
        '## Material de referência (RAG)',
        retrieved_context or '(sem contexto relevante recuperado)',
        '',
        '## Regras inegociáveis',
        '- Responda em português brasileiro.',
        '- Baseie-se no material de referência acima; se não souber, diga que não tem essa informação.',
        '- Não invente fatos.',
    ]
    return dedent('\n'.join(parts)).strip()
```

- **Trade-offs:** Sem versionamento explícito do template = dificulta A/B. Solução: armazenar templates em DB (`PromptTemplate` model) quando o produto cresce.

### 🟪 P-AI-04 — Orquestração com `StateGraph` (LangGraph), não Chains legacy

- **Problema:** `LCEL` puro com chains aninhados fica difícil de debugar. Adicionar fallback, roteamento de modelo ou tool calling exige reescrever.
- **Solução:** Usar `StateGraph` do LangGraph para o fluxo principal: `retrieve → augment → generate → (optional) call_tool → respond`.
- **Exemplo:**

```python
# ai/pipelines/chat_graph.py
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import FAISS

class ChatState(TypedDict):
    question: str
    history: list[dict]
    agent_id: int
    model: str
    context: str
    answer: str

def retrieve(state: ChatState) -> ChatState:
    index = FAISS.load_local(f'media/agents/{state["agent_id"]}/faiss_index', embeddings, allow_dangerous_deserialization=True)
    docs = index.similarity_search(state['question'], k=5)
    state['context'] = '\n\n'.join(d.page_content for d in docs)
    return state

def generate(state: ChatState) -> ChatState:
    llm = ChatOpenAI(model=state['model'], streaming=True)
    messages = [
        {'role': 'system', 'content': build_system_prompt(...)},
        *state['history'],
        {'role': 'user', 'content': state['question']},
    ]
    state['answer'] = llm.invoke(messages).content
    return state

builder = StateGraph(ChatState)
builder.add_node('retrieve', retrieve)
builder.add_node('generate', generate)
builder.add_edge(START, 'retrieve')
builder.add_edge('retrieve', 'generate')
builder.add_edge('generate', END)
chat_graph = builder.compile()
```

- **Trade-offs:** Curva inicial maior. Em compensação, adicionar nó de fallback ou tool é trivial.

### 🟪 P-AI-05 — Multi-Provider com Fallback Transparente

- **Problema:** Quando o provider primário (OpenAI) cai, o produto cai.
- **Solução:** Adapter/Strategy pattern com tabela `LLMModel` no DB (`provider`, `code`, `cost_input_per_1m`, `cost_output_per_1m`). Cliente abstrato escolhe provider; em erro `>= 5xx` ou `RateLimitError`, faz fallback para um secundário (e.g. OpenRouter espelhando o mesmo modelo).

```python
# ai/providers/llm_router.py
from openai import OpenAI, OpenAIError
import os

class LLMRouter:
    def __init__(self, primary_base_url=None, fallback_base_url='https://openrouter.ai/api/v1'):
        self.primary = OpenAI(api_key=os.environ['OPENAI_API_KEY'], base_url=primary_base_url)
        self.fallback = OpenAI(api_key=os.environ['OPENROUTER_API_KEY'], base_url=fallback_base_url)

    def chat(self, *, model: str, messages: list[dict], **kw):
        try:
            return self.primary.chat.completions.create(model=model, messages=messages, **kw)
        except (OpenAIError,) as e:
            return self.fallback.chat.completions.create(model=model, messages=messages, **kw)
```

- **Trade-offs:** Complexidade de billing multi-provider; logue qual provider atendeu cada mensagem.

### 🟪 P-AI-06 — BYOK (Bring Your Own Key) por Tenant

- **Problema:** Cobrar tokens do tenant via cartão é arriscado e financeiramente complexo.
- **Solução:** Tenant cadastra suas próprias keys (`OpenAI`, `OpenRouter`). Sistema cobra apenas a mensalidade do plano. Tabela `TenantApiKey` (FK tenant, provider, encrypted_key). Encriptar com `cryptography.Fernet` usando key derivada de `SECRET_KEY` ou KMS.
- **Quando aplicar:** SaaS B2B onde tenants têm operação madura e querem controle de custo.
- **Quando NÃO aplicar:** B2C / produto que vende "tudo incluído" — cobre tokens via créditos no próprio sistema.
- **Trade-offs:** UX de onboarding fica mais friccionada (tenant precisa configurar key antes de usar). Mostre alerta persistente até a key ser cadastrada.

### 🟪 P-AI-07 — Cost Snapshot por Mensagem

- **Problema:** Recalcular custo de mensagens antigas com preço atual do modelo é mentira histórica.
- **Solução:** No momento de salvar `ChatMessage`, calcular `message_cost = token_count * model.cost_per_1m / 1_000_000` usando o preço **vigente naquele instante** e persistir junto.
- **Bonus:** Calcular `time_saved_minutes = (token_count // 100) * model.minutes_saved_per_100_tokens` como métrica de valor para o tenant.
- **Trade-offs:** Quando o preço do provider muda, o histórico mantém o preço antigo (correto!). Mas filtros no admin precisam considerar isso ao mostrar "custo total".

### 🟪 P-AI-08 — Streaming com `StreamingHttpResponse` + SSE

- **Problema:** Esperar 30s pela resposta completa do LLM mata UX de chat.
- **Solução:** `StreamingHttpResponse` em Django, com `Content-Type: text/event-stream`. LangChain suporta streaming via callback. Cliente consome via `EventSource`.
- **Exemplo:**

```python
from django.http import StreamingHttpResponse

def stream_message_view(request, session_id):
    def event_stream():
        for chunk in chat_graph.stream({...}):
            if 'generate' in chunk:
                yield f'data: {chunk["generate"]["answer"]}\n\n'
        yield 'event: end\ndata: done\n\n'
    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
```

- **Trade-offs:** Conexão unidirecional (suficiente para chat). Para conversa multi-aluno em tempo real, considere Channels/WebSocket.

### 🟪 P-AI-09 — Skills/Tools e MCP como Configuração por Agente

- **Problema:** Hardcoded tools no agente impedem extensibilidade.
- **Solução:** Tabelas `AgentSkill` e `AgentMCP` configuráveis por escola. No request de chat, o aluno ativa/desativa skills disponíveis. Skills viram tool definitions no LangGraph (web search, GitHub MCP, Google Calendar via OAuth, image vision).
- **Trade-offs:** Tool calling exige modelo compatível — degrade graciosamente quando o modelo selecionado não suporta.

### 🟪 P-AI-10 — Treinamento de RAG Sempre Assíncrono

- **Problema:** Indexar 200MB de PDFs em request síncrona = timeout, frustração e provider rate limit.
- **Solução:** Botão "Treinar Agente" dispara Celery task. Status do agente: `untrained → training → trained / failed`. UI faz polling ou WebSocket para acompanhar. Agente fica usável durante treino com índice antigo (não derruba enquanto re-treina).
- **Trade-offs:** Mais complexidade vs. UX correta — vale.

## 4.3 Domínio: Processamento Assíncrono com Celery

### 🟩 P-CELERY-01 — RabbitMQ como Broker (não Redis)

- **Problema:** Redis como broker perde tasks em quedas; não tem dead-letter nativo.
- **Solução:** RabbitMQ com versão `management` (dashboard em `https://rabbitmq.<dominio>`). Redis fica para cache/sessions/result_backend.
- **Trade-offs:** Mais um serviço. Compensação: confiabilidade de fila + observabilidade.

### 🟩 P-CELERY-02 — `celery.py` em `core/` com auto-discovery

- **Solução canônica:** Configuração mínima e idiomática.

```python
# core/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.prod')
app = Celery('project')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

```python
# core/__init__.py
from .celery import app as celery_app
__all__ = ('celery_app',)
```

```python
# settings/base.py — ajustes Celery
CELERY_BROKER_URL = os.environ['CELERY_BROKER_URL']  # amqp://user:pass@rabbitmq:5672//
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 25
```

### 🟩 P-CELERY-03 — Task Idempotente com Chave Externa

- **Problema:** Reprocessar uma task duplica efeito (cobra de novo, envia email de novo).
- **Solução:** Toda task que toca estado externo recebe um `idempotency_key` (ex: `event_id` do webhook). Antes de executar, registra/checa em tabela `IdempotentEvent`.
- **Exemplo:**

```python
@shared_task(bind=True, autoretry_for=(Exception,), max_retries=5, retry_backoff=True)
def process_payment_event(self, idempotency_key: str, payload: dict):
    obj, created = IdempotentEvent.objects.get_or_create(key=idempotency_key)
    if not created:
        return {'skipped': True, 'reason': 'already_processed'}
    try:
        _apply_payment_effects(payload)
        obj.status = 'processed'
        obj.save(update_fields=['status', 'updated_at'])
    except Exception:
        obj.delete()  # liberar para retry
        raise
```

### 🟩 P-CELERY-04 — Filas Dedicadas por Domínio

- **Problema:** Uma task lenta de transcrição congestiona a fila e atrasa um email crítico.
- **Solução:** Filas separadas: `default`, `ai_heavy` (treino RAG, transcrição, vision), `emails`, `webhooks`, `notifications`. Workers com `--queues=ai_heavy` rodam em containers dedicados com mais CPU.

```python
# rotear tasks
CELERY_TASK_ROUTES = {
    'apps.agents.tasks.train_agent': {'queue': 'ai_heavy'},
    'apps.agents.tasks.transcribe_video': {'queue': 'ai_heavy'},
    'apps.notifications.tasks.send_push': {'queue': 'notifications'},
    'apps.webhooks.tasks.process_payment_event': {'queue': 'webhooks'},
}
```

### 🟩 P-CELERY-05 — Beat para Cron, com migração de cron-no-container

- **Padrão evolutivo:** Comece com cron dentro do container Django (rápido de subir). Migre para Celery Beat quando: (a) precisar de retries, (b) precisar de visibilidade no Flower, (c) crescer para múltiplas réplicas (cron duplicaria execução).
- **Beat exemplo:**

```python
CELERY_BEAT_SCHEDULE = {
    'process-pending-access-requests': {
        'task': 'apps.enrollments.tasks.process_pending_requests',
        'schedule': 60.0,  # a cada minuto
    },
    'rotate-monthly-credits': {
        'task': 'apps.credits.tasks.rotate_monthly_credits',
        'schedule': crontab(minute=0, hour=3),  # 3 AM diário
    },
}
```

### 🟩 P-CELERY-06 — Flower com Auth no Subdomínio

- **Solução:** Flower em `https://flower.<dominio>` com `--basic-auth=user:strongpass`. Acesso interno ao admin do sistema. Senha injetada via secret do Swarm/Easy Panel.

### 🟩 P-CELERY-07 — Celery Errors → Sentry com `before_send`

- **Solução:** Integrar `sentry_sdk` com `CeleryIntegration`. Filtrar PII via `before_send`.

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn=os.environ['SENTRY_DSN'],
    integrations=[DjangoIntegration(), CeleryIntegration()],
    traces_sample_rate=0.1,
    environment=os.environ.get('ENVIRONMENT', 'prod'),
    release=os.environ.get('RELEASE'),
    before_send=scrub_pii,
)
```

### 🟩 P-CELERY-08 — Webhook → Task Imediata + Resposta 202

- **Problema:** Provedor de pagamento abandona se webhook demora >5s.
- **Solução:** View do webhook valida assinatura, persiste payload bruto, dispara `process_*_event.delay(payload_id)`, retorna `202 Accepted`. Toda lógica vai para a task.

## 4.4 Domínio: Infra, Containerização e Deploy

### 🟧 P-INFRA-01 — `compose/` por serviço com Dockerfiles separados

- **Estrutura canônica:**

```
compose/
├── django/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── start-web.sh
├── celery/
│   ├── Dockerfile (FROM django:latest)
│   └── start-worker.sh
├── traefik/
│   ├── traefik.yml
│   └── dynamic/
├── postgres/init/
└── nginx/  (opcional para servir media)
```

### 🟧 P-INFRA-02 — Dockerfile Multi-Stage Magrinho

```docker
# compose/django/Dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 ffmpeg cron nano && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY . .
RUN useradd -m django && chown -R django:django /app
USER django
EXPOSE 8000
CMD ["./compose/django/start-web.sh"]
```

```bash
# compose/django/start-web.sh
#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-3} \
    --threads ${GUNICORN_THREADS:-2} \
    --timeout 120 \
    --access-logfile - --error-logfile -
```

### 🟧 P-INFRA-03 — `docker-compose.yml` (Dev) vs. `docker-stack.yml` (Swarm)

- **Dev:** Compose com bind mounts para hot-reload.
- **Prod:** Swarm stack com `deploy.replicas`, `deploy.resources`, `deploy.update_config.parallelism: 1` para rolling updates zero-downtime.

```yaml
# docker-stack.yml (extrato)
version: '3.9'
services:
  app:
    image: registry.example.com/app:${TAG}
    deploy:
      replicas: 3
      update_config: { parallelism: 1, delay: 15s, order: start-first }
      restart_policy: { condition: on-failure }
      labels:
        - traefik.enable=true
        - traefik.http.routers.app.rule=Host(`app.example.com`)
        - traefik.http.routers.app.tls.certresolver=letsencrypt
        - traefik.http.services.app.loadbalancer.server.port=8000
    secrets: [django_secret_key, db_password, openai_api_key]
    environment:
      DJANGO_SETTINGS_MODULE: core.settings.prod
      DATABASE_URL: postgres://app:$$(cat /run/secrets/db_password)@postgres:5432/app
  worker:
    image: registry.example.com/app:${TAG}
    command: celery -A core worker -Q default,emails -l INFO --concurrency=4
    deploy: { replicas: 2 }
  worker-ai-heavy:
    image: registry.example.com/app:${TAG}
    command: celery -A core worker -Q ai_heavy -l INFO --concurrency=2
    deploy: { replicas: 2, resources: { limits: { cpus: '2.0', memory: '4G' } } }
  beat:
    image: registry.example.com/app:${TAG}
    command: celery -A core beat -l INFO
    deploy: { replicas: 1 }
```

### 🟧 P-INFRA-04 — Traefik como Edge (TLS automático + routing)

- **Solução:** Traefik no Swarm como serviço global. Labels nos serviços de app indicam regras de host. Let's Encrypt automático.
- **Subdomínios padrão:** `app`, `flower`, `rabbitmq`, `docs`, `sentry`. Todos com auth.

### 🟧 P-INFRA-05 — Docker Swarm Secrets > env vars

- **Problema:** Secrets em `.env` vazam para image, log, dump.
- **Solução:** `docker secret create` para senhas/keys. Em settings, ler de `/run/secrets/<name>`.

```python
def read_secret(name, default=None):
    p = Path(f'/run/secrets/{name}')
    if p.exists(): return p.read_text().strip()
    return os.environ.get(name.upper(), default)
```

### 🟧 P-INFRA-06 — Volume `media/` Persistente + Estratégia de Backup

- **Problema:** `media/` cresce muito com PDFs e índices FAISS. Precisa de backup separado da DB.
- **Solução:** Volume nomeado externo no Swarm. Job (CronJob ou Celery Beat) faz `restic`/`rclone` para S3-compatible (Backblaze, R2) com retenção.

```bash
# scripts/backup_media.sh
restic -r s3:s3.amazonaws.com/bucket-backup backup /var/lib/media \
  --exclude='*.tmp' --tag media --tag prod
restic -r s3:... forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
```

### 🟧 P-INFRA-07 — Easy Panel para a Camada Operacional

- **Quando aplicar:** VPS único ou cluster pequeno (<5 nós), equipe sem SRE dedicado.
- **Vantagens:** UI sobre Docker Swarm + Traefik + auto-deploy de templates. Excelente para fase 0–100k MAU.
- **Quando NÃO aplicar:** Multi-região, compliance pesado, exigências de IaC declarativa estrita. Migre para Kubernetes (EKS) ou ECS.

### 🟧 P-INFRA-08 — Cron-no-Container como Solução Transitória

- **Quando faz sentido:** Job simples que precisa rodar a cada minuto antes de ter Celery Beat.
- **Como:** Arquivo `cron/cron.app` na raiz, copiado para `/etc/cron.d/cron` no Dockerfile, com `RUN crontab /etc/cron.d/cron`. Stdout via `>> /var/log/cron_<job>.log 2>&1`.

```
# cron/cron.app
*/1 * * * * cd /app && export $(cat .env | xargs) && /usr/local/bin/python manage.py process_pending_requests >> /var/log/cron_requests.log 2>&1
```

```docker
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
COPY ./cron/cron.app /etc/cron.d/cron
RUN chmod 0644 /etc/cron.d/cron && crontab /etc/cron.d/cron
```

<aside>
⚠️

**Migração obrigatória para Beat quando:** múltiplas réplicas (cron duplica execução), retry/observabilidade necessárias, ou job passa de 1 minuto.

</aside>

### 🟧 P-INFRA-09 — `docs/` com MKDocs em container separado

- **Solução:** `mkdocs-material` em `docs.dominio:8001` como serviço Docker. Reload em git push via webhook ou rebuild.

## 4.5 Domínio: Observabilidade

### 🟫 P-OBS-01 — Sentry Self-Hosted como ground zero de erros

- **Solução:** Stack Sentry self-hosted (oficial, via `getsentry/self-hosted` repo) ou Sentry SaaS para times pequenos. Integrações Django + Celery + Redis. Tags por tenant (`scope.set_tag('school_id', ...)`) para isolar issues por cliente.

### 🟫 P-OBS-02 — Métricas de Negócio em Banco como Source-of-Truth

- **Padrão:** Não dependa só de Prometheus para métricas que aparecem em UI do produto (uso de tokens, alunos ativos, custo por escola). Persista em DB com agregações query-able. Prometheus fica para latência/throughput/erros.

### 🟫 P-OBS-03 — LangSmith Tracing com Sampling

- **Solução:** Habilitar `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`. Em prod, configurar `LANGCHAIN_PROJECT` por ambiente. Tracing de 100% em dev, ~10% em prod (custa).

### 🟫 P-OBS-04 — Dashboards Tenant-Scoped

- **Padrão:** Toda escola vê o próprio dashboard com KPIs (cursos, agentes treinados, alunos ativos, créditos consumidos, tempo economizado). Filtros por período: `hoje`, `essa_semana`, `esse_mes`, `personalizado`. Default = `esse_mes`.

### 🟫 P-OBS-05 — `time_saved_minutes` como Métrica de Valor

- **Solução:** Para SaaS de IA, calcular tempo economizado por interação é o métrico mais persuasivo. Fórmula configurável por modelo (ex.: `10 min por 100 tokens`). Persistir em `ChatMessage.time_saved_minutes`. Mostrar agregado no dashboard ("Sua escola economizou 320h em suporte este mês").

### 🟫 P-OBS-06 — Logs Estruturados (JSON) com Correlation ID

- **Solução:** `python-json-logger` ou `structlog`. Middleware injeta `request_id`. Tasks Celery propagam o `request_id` como `headers={'request_id': ...}`. Sentry → mesmo correlation. LangSmith → mesmo correlation.

### 🟫 P-OBS-07 — Painel "Reports & Suggestions" em DB

- **Solução:** Modelo `BugReport` / `Suggestion` com FK ao usuário, anexos (imagens), status. Botão visível em navbar (próximo a tag "Beta"). Admin do Django filtra por status, prioriza, marca resolvido com link para PR/commit.

## 4.6 Domínio: Multi-Tenancy

### 🟥 P-MT-01 — Shared Schema + FK + Mixins

- **Problema:** Schema-per-tenant escala mal e dificulta migrações; database-per-tenant onera infra.
- **Solução:** Shared schema, FK `tenant_id` em toda tabela tenant-scoped, mixin garante filtro nas CBVs. Validar com testes e auditorias periódicas (`./manage.py check_tenant_isolation`).

### 🟥 P-MT-02 — Cross-Tenant Allowed para User (E2E vs. Tenant)

- **Problema:** Mesmo usuário precisa pertencer a múltiplos tenants (estudante de várias escolas).
- **Solução:** `User` é global; vínculos com tenants ficam em tabela `Membership`/`Enrollment`. View que lista "meus tenants" filtra por membership ativo.

### 🟥 P-MT-03 — Plan Gate + Limit Check antes de Mutações

- **Solução:** Decorator/mixin `@enforce_plan_limit(resource='courses')` que checa contagem atual vs. `subscription.max_courses` antes de salvar. Resposta amigável (toast + CTA upgrade), não 500.

```python
from functools import wraps

def enforce_limit(resource: str):
    def deco(view_method):
        @wraps(view_method)
        def wrapper(self, request, *a, **kw):
            sub = request.user.owned_school.subscription
            count = self.get_current_usage(request, resource)
            limit = getattr(sub.plan, f'max_{resource}')
            if count >= limit:
                messages.warning(request, f'Você atingiu o limite de {resource} do plano {sub.plan.name}. Faça upgrade.')
                return redirect('billing:upgrade')
            return view_method(self, request, *a, **kw)
        return wrapper
    return deco
```

### 🟥 P-MT-04 — BYOK por Tenant (chaves de provider)

- Já descrito em §4.2 (P-AI-06). Aqui reforça: **toda key cifrada em rest** (Fernet), **decifrada apenas em memória** no momento da chamada, **nunca logada**.

### 🟥 P-MT-05 — Suspensão Graciosa por Status do Plano

- **Solução:** `Subscription.status` ∈ {`trialing`, `active`, `past_due`, `canceled`, `expired`}. Em `past_due`, exibe banner global e bloqueia *ações de criação*, mas mantém leitura. Em `expired`, bloqueia agentes (estudantes não conseguem chat). Sempre com CTA claro de pagamento.

### 🟥 P-MT-06 — Trial com Expiração Hard (14 dias)

- **Solução:** Plano free com `trial_ends_at`. Após D+14, agentes desativados; admin recebe banner + email. Upgrade reativa imediato.

## 4.7 Domínio: Desenvolvimento Assistido por IA

### 🟨 P-DEV-01 — PRD Vivo como Fonte Única

- **Padrão:** `PRD.md` na raiz, atualizado a CADA feature/correção. Estrutura canônica: visão geral, arquitetura, modelo de dados, apps, funcionalidades (com critérios de aceite), fluxos (Mermaid), sistema de IA, billing, UI/UX, endpoints, **Roadmap de Sprints com checkboxes**, decisões técnicas, glossário.
- **Regra:** Todo prompt de implementação começa com `Analise com cuidado todos os detalhes do @PRD.md, do @design_system/design-system.html e do código...`.

### 🟨 P-DEV-02 — Prompt Estruturado em Tags XML

- **Solução:** Template canônico com seções tagueadas: `<context>`, `<role>`, `<objective>`, `<non_negotiable_rules>`, `<task_scope>`, `<feature_*>`, `<required_research_and_definition>`, `<deliverables>`, `<quality_bar>`, `<forbidden_output_patterns>`, `<execution_expectation>`. Reutilizável.

```xml
<context>...</context>
<role>Atue como engenheiro sênior...</role>
<objective>Implementar X respeitando @PRD.md</objective>
<non_negotiable_rules>
1. Leia @PRD.md integralmente.
2. Leia @design_system/design-system.html integralmente.
...
</non_negotiable_rules>
<deliverables>...</deliverables>
<forbidden_output_patterns>
- código genérico
- duplicação de regras já existentes
</forbidden_output_patterns>
```

### 🟨 P-DEV-03 — Plan-then-Execute em Modelos Diferentes

- **Padrão:** Modelo "raciocinador" (mais caro, mais profundo) gera plano e atualiza o PRD com sprint detalhada. Modelo "executor" (mais rápido, mais barato) implementa marcando checkboxes.
- **Anti-padrão:** Pedir ao mesmo modelo para planejar e executar tudo numa volta — explode contexto, perde fidelidade.

### 🟨 P-DEV-04 — Sprint-Driven com `[x]` no PRD

- **Padrão:** Cada sprint vira seção do PRD com checklist:

```markdown
### Sprint 12 — Webhooks Hubla (1 semana)
**Objetivo:** Receber eventos de venda/refund, criar/cancelar enrollment.

- [x] Model `WebhookEvent` (idempotência)
- [x] View `/webhooks/hubla/` com validação de assinatura
- [x] Task `process_hubla_event` (Celery)
- [ ] Testes de integração com payload real
- [ ] Documentação no MKDocs
```

- **Regra:** Marcar `[x]` é Definition of Done.

### 🟨 P-DEV-05 — Diagnóstico antes de Implementar

- **Padrão:** Toda task de feature começa com a frase no prompt: `Antes de implementar, faça um diagnóstico claro do que já existe no projeto sobre [...]`. Evita reinvenção e duplicação.

### 🟨 P-DEV-06 — Documentar Ambiguidades no PRD, não no código

- **Regra:** Quando o agente encontrar ambiguidade, ele decide pelo padrão mais consistente com o sistema atual e **registra a decisão no PRD**. Código não é o lugar para semântica.

### 🟨 P-DEV-07 — `AGENTS.md` / `CLAUDE.md` como Atalhos do Repo

- **Padrão:** Arquivos curtos na raiz com: comandos comuns, convenções de nomes, golden paths, reference snippets. Curtos: ~150 linhas máximo.

### 🟨 P-DEV-08 — Bug-Report dentro do Produto

- **Padrão:** Tag "Beta" + botão "Reportar bug / Sugerir melhoria" na navbar. Salva em DB com anexo. Vira input do próximo prompt de correção (anti-fricção: o usuário não precisa nem trocar de janela).

### 🟨 P-DEV-09 — Anti-Padrões Identificados

| **Anti-padrão** | **Por que evitar** | Pedir refatoração ampla "de quebra" | O agente quebra coisas não relacionadas; resultado vira PR gigante e arriscado. |
| --- | --- | --- | --- |
| Não enviar PRD/design system no prompt | Agente inventa padrões — solução fica órfã do sistema. | Aceitar `alert()` nativo "por enquanto" | Vira dívida visual permanente; modal correto custa pouco mais. |
| Não atualizar o PRD junto com o código | O PRD vira mentira — próximo prompt parte de premissa errada. | Pular o diagnóstico inicial | Resultado: 3 implementações paralelas da mesma coisa. |

## 4.8 Domínio: UI/UX, Jornadas e Funcionalidades-Chave

### 🟦 P-UX-01 — Design System como Arquivo Estático Vivo

- **Padrão:** `design_system/design-system.html` na raiz. Todo componente possível, com snippets copy-paste. Atualizado quando ENTRA novo componente; nada novo na UI sem entrar no DS primeiro.

### 🟦 P-UX-02 — Sidebar + Top Header Layout (admin)

- **Padrão:** Layout de painel admin = sidebar fixa à esquerda (navegação) + header superior (busca, perfil, alertas, créditos). Conteúdo central com cards de KPI no topo.

### 🟦 P-UX-03 — Cards Liberados/Bloqueados (catálogo)

- **Padrão:** Em catálogos onde o usuário tem subset, mostrar:
    - **Topo:** itens liberados (clicáveis, ação primária).
    - **Embaixo:** itens bloqueados com overlay de cadeado e CTA dual (Comprar ↗ / Solicitar acesso). Reforça discoverability sem confundir disponibilidade.

### 🟦 P-UX-04 — Chat Streaming com Sidebar de Sessões

- **Padrão:** Layout messenger (mensagens à direita do user, à esquerda do agent). Sidebar lista sessões. Streaming token-a-token via SSE. Header tem seletor de modelo.
- **Regra extra:** Não criar nova sessão em branco a cada load — só se a última sessão tiver mensagens.

### 🟦 P-UX-05 — Modal &gt; `alert()` para Confirmações

- **Padrão:** Confirmações destrutivas e ações que custam (treinar IA, deletar chat, sair de assinatura) em modal do design system. Texto claro + botão primário destrutivo + cancelar.

### 🟦 P-UX-06 — Período Filter Padrão ("Esse mês")

- **Padrão:** Toda visão de métrica tem filtro `hoje | essa_semana | esse_mes | personalizado`. Default = `esse_mes`. O personalizado abre date-range picker que persiste via querystring.

### 🟦 P-UX-07 — Créditos Visíveis na Navbar

- **Padrão:** Em SaaS de uso, sempre mostrar saldo (`23/100 créditos`) na navbar com tooltip explicando "1 crédito = 1 mensagem". Quando &lt;10%, virar amarelo; quando 0, vermelho com CTA "comprar pacote".

### 🟦 P-UX-08 — Ranking Sem PII

- **Padrão:** Tela de ranking/competição mostra nome (sem email), escola, métrica. Nunca dados pessoais. Top 3 tem destaque visual + premiação automática (créditos extras).

### 🟦 P-UX-09 — Chat Embedável (Iframe + Floating Bubble)

- **Padrão:** Gerar URL pública por agente que renderiza o chat sem chrome do app. Configurações por chat: cor primária, formato (fullscreen ou floating bubble). Cookie/localStorage para identidade do visitante. Rate-limit por IP.

### 🟦 P-UX-10 — Compartilhamento Público (read-only)

- **Padrão:** Botão "compartilhar conversa" gera link público read-only com mesmo design do chat + tag de modelo em cada mensagem do agente. URL com token único, opcionalmente com expiração.

### 🟦 P-UX-11 — UI em Idioma do Usuário, Código em Inglês

- **Regra:** Strings na UI em PT-BR (ou idioma local), nomes de models/views/URLs em inglês. Estrutura de pastas em inglês. Atualize `LANGUAGE_CODE` e use Django i18n quando expandir.

### 🟦 P-UX-12 — Mobile com Scroll Horizontal em Grids

- **Padrão:** Grids de dados em mobile não tentam quebrar — recebem `overflow-x: auto`. Tabelas mantêm colunas; usuário rola.

### 🟦 P-UX-13 — Enter no Mobile = Quebra de Linha (não enviar)

- **Solução:** Detectar mobile via `window.matchMedia('(pointer: coarse)')` ou user-agent; alterar behavior do textarea para `Enter = newline`. Botão dedicado de "enviar". Em desktop, `Enter = enviar`, `Shift+Enter = newline`.

### 🟦 P-UX-14 — Onboarding via Convite com Conta Auto-Criada

- **Padrão:** Quando admin convida email novo, o sistema:
    1. Cria User com senha randômica (não exposta na UI).
    2. Envia email com link mágico ou senha temporária.
    3. Redireciona usuário para "Alterar senha" no primeiro login.
- **Regra:** "Solicitar acesso" via link público idem; admin aprova → conta criada → email enviado.

### 🟦 P-UX-15 — Gamificação com Premiação Real (créditos)

- **Padrão:** Ranking mensal premia top 3 com créditos extras no próximo ciclo. Transparência: tela exibe critérios de pontuação, pesos por ação, premiação.

### 🟦 P-UX-16 — Notificações Push com Modos Auto + Custom

- **Padrão:** Tabela `PushSubscription` por usuário. Tela de admin permite (a) deixar plataforma gerenciar (auto, regras pré-definidas), (b) custom: imediato, agendado, recorrente, com seleção de destinatários (todos / manual / grupos: "sem login há 3 dias", "top 10 ranking", "com pendências").

---

# 5. Stack Detalhada

| **Tecnologia** | **Versão min.** | **Papel no sistema** | **Razão da escolha** | Python | 3.12 | Linguagem base | Type hints maduros, performance melhor, ainda dentro do ciclo de vida da maioria das libs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Django | 6.0 | Framework web monolítico modular | Bateria-incluída para SaaS: ORM, auth, admin, forms, sessions, mail, i18n. Multi-tenancy por FK é trivial. | PostgreSQL | 16 | OLTP + JSONB + extensões | Robustez, JSONB para payloads flexíveis, pgvector se quiser eliminar FAISS |
| Redis | 7 | Cache + sessions + Celery result backend | Hot path simples; baixíssima latência | RabbitMQ (management) | 3.13 | Broker de fila Celery | Confiabilidade, dead-letter, dashboard nativo, overhead aceitável |
| Celery | 5.6 | Tasks assíncronas + Beat (scheduler) | Maturidade, integração nativa com Django, observabilidade via Flower | Flower | 2.x | Dashboard Celery | Inspeção de tasks em tempo real; basic-auth basta para admin |
| LangChain | 1.2+ | Loaders, splitters, embeddings, vector store | Padrão de fato para integração com LLMs; ecossistema vasto | LangGraph | 1.1+ | Orquestração com `StateGraph` | Substituto natural a chains; flexível para fallback e tool calling |
| OpenAI SDK | 2.0+ | Cliente para OpenAI e (via base_url) OpenRouter | API estável, suporte a streaming/tools nativo | FAISS-cpu | 1.13+ | Vector store local | Sem custo de infra; rápido para volumes médios. Migrar para pgvector quando escalar |
| tiktoken | 0.12+ | Token counting | Crítico para controle de contexto e custo | pypdf | 6.0+ | Extração de texto de PDF | Loader padrão LangChain |
| Sentry (self-hosted) | 24.x | Error tracking | Tags por tenant, integrações Django+Celery, retain control on-prem | Prometheus + Grafana | 3.x / 11.x | Métricas de infra | Padrão de fato; dashboards reutilizáveis |
| LangSmith | SaaS | Tracing de chains/graphs | Sampling permite custo controlado em prod | MKDocs (Material) | 9.x | Documentação interna | Deploy simples como container separado |
| Docker / Compose | 26+ / 2.27+ | Containers | Reprodutibilidade; idêntico em dev/prod | Docker Swarm | integrado | Orquestração leve | Custo operacional muito menor que K8s para &lt;5 nós; rolling updates nativos |
| Traefik | 3.x | Reverse proxy + TLS automático | Service discovery via labels do Swarm; Let's Encrypt zero-config | Easy Panel | — | UI sobre Swarm + Traefik | Acelera operação para times sem SRE |
| Stripe / Hubla | API atual | Pagamentos recorrentes + one-time | Switch via env var (`PAYMENT_PLATFORM`); webhook idempotente | Cryptography (Fernet) | 43+ | Encrypt at rest de keys de tenant | Standard library, simples, auditável |

---

# 6. Workflow de Desenvolvimento Assistido por IA

## 6.1 Ciclo Canônico (do conceito ao deploy)

```mermaid
flowchart TD
    A["Ideia/feedback do usuário"] --> B["Prompt de PLANEJAMENTO (modelo raciocinador)"]
    B --> C["PRD.md atualizado: nova seção + sprint com checkboxes"]
    C --> D["Revisão humana do plano (5–15min)"]
    D --> E{Plano OK?}
    E -->|Não| B
    E -->|Sim| F["Prompt de EXECUÇÃO (modelo executor) referenciando PRD + DS + código"]
    F --> G["Implementação + marcação de [x] na sprint"]
    G --> H["Code review humano (focar em isolamento tenant, idempotência, custos)"]
    H --> I{Revisão OK?}
    I -->|Não| F
    I -->|Sim| J["Deploy via swarm rolling (Easy Panel push)"]
    J --> K["Monitoria pós-deploy: Sentry, Flower, Grafana, métricas no dashboard"]
    K --> L["Atualizar MKDocs se introduziu conceito novo"]
```

## 6.2 Templates de Prompt Reutilizáveis

- **Template A — Planejamento de feature (modelo raciocinador)**
    
    ```xml
    <context>
    Projeto real existente. Fontes obrigatórias: @PRD.md, @design_system/design-system.html,
    código, padrões consolidados. NÃO trate como greenfield.
    </context>
    
    <role>
    Especialista sênior em arquitetura SaaS, IA, DX, integração e documentação
    orientada à implementação real.
    </role>
    
    <objective>
    NESTA TAREFA NÃO IMPLEMENTE. Apenas analise, diagnostique, especifique,
    planeje sprints e atualize o @PRD.md.
    </objective>
    
    <non_negotiable_rules>
    1. Leia integralmente @PRD.md.
    2. Leia integralmente @design_system/design-system.html.
    3. Analise o código real antes de propor.
    4. Não invente entidades/fluxos/permissões.
    5. Em ambiguidade: decida pelo padrão atual e DOCUMENTE no PRD.
    </non_negotiable_rules>
    
    <feature_scope>
    [descreva a feature]
    </feature_scope>
    
    <deliverables>
    1. Diagnóstico do estado atual
    2. Objetivo e valor
    3. Especificação funcional completa
    4. Modelagem (entidades, campos, status)
    5. Impactos (backend, frontend, banco, jobs, integrações)
    6. UX/UI (alinhada ao design system)
    7. Roadmap em sprints (objetivo, escopo, tarefas, dependências, riscos, entregáveis)
    8. Critérios de aceite verificáveis
    </deliverables>
    
    <forbidden_output_patterns>
    - texto genérico
    - arquitetura sem aderência ao código real
    - UX fora do design system
    </forbidden_output_patterns>
    ```
    
- **Template B — Execução de sprint (modelo executor)**
    
    ```
    Analise com cuidado todos os detalhes do @PRD.md, do
    @design_system/design-system.html e do código, implementações e padrões
    já realizados no projeto, e em seguida execute a Sprint NN — <título>
    descrita na seção 12. Roadmap de Sprints do @PRD.md.
    Ao concluir cada item, marque [x] no checklist. Ignore tarefas já marcadas.
    
    Regras inegociáveis:
    - Toda nova implementação deve parecer nativa do projeto.
    - Reaproveite componentes/serviços existentes; não duplique lógica.
    - Não faça refatoração ampla fora do escopo.
    - Em ambiguidade, decida pelo padrão atual e documente a decisão no PRD.
    ```
    
- **Template C — Diagnóstico de bug**
    
    ```
    Analise o seguinte bug reportado: <descrição>.
    Fontes: @PRD.md, @design_system/design-system.html, logs/Sentry, código.
    1. Reproduza mentalmente o caminho do bug (URL → view → service → DB / IA).
    2. Liste hipóteses de causa raiz, ordenadas por probabilidade.
    3. Para cada hipótese, descreva como verificar.
    4. Proponha o fix mínimo + fix robusto (com testes).
    5. Atualize o PRD na seção "correções aplicadas" caso o bug venha de regra de negócio mal especificada.
    ```
    

## 6.3 Modelos por Etapa

| **Etapa** | **Modelo recomendado (classe)** | **Por quê** | Brainstorming + planejamento | Raciocinador (Opus, GPT-o, Gemini Pro Thinking) | Profundidade contextual para sintetizar PRD com múltiplas seções |
| --- | --- | --- | --- | --- | --- |
| Execução de sprint | Executor (Sonnet, GPT-mini, Haiku) | Velocidade e custo para implementação iterativa | Code review crítico | Raciocinador novamente | Caça regressões e quebras de invariantes que o executor não vê |
| Geração de docs MKDocs | Executor | Texto estruturado direto | UX copy / landing | Executor com prompt criativo | Iterar variações é barato |

## 6.4 Anti-padrões de Workflow

- 🛑 Pedir "e já refatora isso aqui de quebra" no meio de outra task.
- 🛑 Aceitar implementação sem verificar manualmente em ambiente local antes do deploy.
- 🛑 Esquecer de atualizar o PRD junto com o código (PRD vira mentira).
- 🛑 Não rodar `migrate --check` antes de subir migration.
- 🛑 Push direto na main sem rolling update / sem subir image taggeada.

---

# 7. Checklist de Implementação (do zero ao primeiro deploy)

<aside>
📋

**Use esta checklist como roteiro. Cada item é independente — pode ser delegado a um modelo executor com `Template B`.**

</aside>

## Fase 0 — Decisões iniciais

- [ ]  Definir bounded contexts (escrever lista de apps Django: 5–10 apps).
- [ ]  Definir modelo de tenant: shared schema com FK (default).
- [ ]  Decidir BYOK vs. centralized API key.
- [ ]  Escolher provedor primário e fallback de LLM.
- [ ]  Esboçar PRD inicial: visão, personas, modelo de dados (ER em Mermaid), apps, sprints estimadas.

## Fase 1 — Fundação Django

- [ ]  `pip install django postgresql-* python-decouple`.
- [ ]  Criar `core/` (settings split: base, dev, prod).
- [ ]  Criar `apps/accounts/` com `User(AbstractUser)` + `USERNAME_FIELD = 'email'`.
- [ ]  Criar `apps/core/` com `BaseModel(abstract)`.
- [ ]  `EmailBackend` registrado em `AUTHENTICATION_BACKENDS`.
- [ ]  Primeiro `migrate` ✅.
- [ ]  Login/registro/logout/perfil (CBV).
- [ ]  Templates base com estrutura do design system (sidebar + header).

## Fase 2 — Tenants e Domínio Central

- [ ]  App `tenants/` com `School/Organization`, `Subscription`, `Plan`, `Membership`.
- [ ]  Mixins `LoginRequired` + `TenantScoped`.
- [ ]  CRUD de tenant.
- [ ]  Plan-gate decorator.
- [ ]  App de domínio central (e.g., `agents/`, `projects/`, depende do produto).

## Fase 3 — IA e RAG

- [ ]  Pin de versões em `requirements.txt` (LangChain 1.2+, OpenAI 2+, etc.).
- [ ]  Pasta `ai/` com `pipelines/`, `providers/`, `prompts/`, `tools/`.
- [ ]  Pipeline RAG ingestion (loaders → splitter → embeddings → FAISS).
- [ ]  Pipeline RAG retrieval (`StateGraph`).
- [ ]  System prompt builder.
- [ ]  Cliente LLM com fallback OpenAI ↔ OpenRouter.
- [ ]  Modelo `LLMModel` (cost por 1M tokens, capabilities).

## Fase 4 — Async

- [ ]  Subir RabbitMQ + Redis (compose).
- [ ]  `core/celery.py` com `autodiscover_tasks`.
- [ ]  Filas dedicadas: `default`, `ai_heavy`, `emails`, `webhooks`, `notifications`.
- [ ]  Migrar treinamento de RAG para Celery task.
- [ ]  Migrar envio de email para Celery task.
- [ ]  Beat com primeiros jobs cron.
- [ ]  Flower em subdomínio com basic-auth.

## Fase 5 — Chat e Streaming

- [ ]  Modelo `ChatSession` + `ChatMessage` (campos: model_used, token_count, message_cost, time_saved_minutes).
- [ ]  View de chat com `StreamingHttpResponse` (SSE).
- [ ]  UI tipo messenger + sidebar de sessões.
- [ ]  Não criar sessão vazia se a última estiver vazia.
- [ ]  Modelo selector no header.
- [ ]  Streaming via LangChain callback.

## Fase 6 — Billing e Webhooks

- [ ]  App `billing/` com adapter abstrato (`PaymentProvider`).
- [ ]  Adapters Stripe + secundário (Hubla, Mercado Pago, etc.).
- [ ]  Switch via `PAYMENT_PLATFORM` env var.
- [ ]  App `webhooks/` com modelo `WebhookEvent` (idempotency_key).
- [ ]  View webhook → persiste payload bruto → dispara task → 202.
- [ ]  Task `process_<provider>_event` idempotente.
- [ ]  Status de subscription gating UI (banner past_due, bloqueio expired).

## Fase 7 — Observabilidade

- [ ]  Sentry (self-hosted ou SaaS) + integrações Django + Celery.
- [ ]  Tags por tenant em todos os scopes.
- [ ]  Logs JSON estruturados com `request_id`.
- [ ]  LangSmith em dev (100%) e prod (~10% sample).
- [ ]  Dashboard de métricas com filtro `esse_mes` default.
- [ ]  MKDocs em container separado.

## Fase 8 — Containerização e Deploy

- [ ]  `compose/django/Dockerfile` multi-stage.
- [ ]  `compose/celery/Dockerfile` (FROM django).
- [ ]  `docker-compose.yml` (dev) com bind mount + reload.
- [ ]  `docker-stack.yml` (prod) com replicas + Traefik labels + secrets.
- [ ]  Volume `media/` com job de backup (restic/rclone).
- [ ]  CI/CD: build image → push registry → `docker stack deploy`.
- [ ]  Domínio + SSL automático Let's Encrypt via Traefik.
- [ ]  Subdomínios: `app`, `flower`, `rabbitmq`, `docs`, `sentry` — todos com auth.

## Fase 9 — Polimento e Estabilização

- [ ]  Tela de "Reportar bug" + tag Beta na navbar.
- [ ]  Modal de confirmação para todas ações destrutivas.
- [ ]  Filtros de período em todas as métricas (default `esse_mes`).
- [ ]  Mobile: scroll horizontal em grids; Enter = newline em mobile.
- [ ]  Audit de queries: `select_related` / `prefetch_related` no quente.
- [ ]  Tela 404/500 customizadas.
- [ ]  Onboarding via convite com senha randômica + email automático.

---

# 8. Pitfalls e Anti-Padrões

## 8.1 Modelagem & Multi-Tenancy

<aside>
⛔️

**`tenant_id` esquecido em UMA query =&gt; vazamento cross-tenant.** Solução: mixin obrigatório + teste automatizado que percorre todas as views autenticadas verificando filtro.

</aside>

<aside>
⛔️

**Trocar `User` model depois do primeiro `migrate`.** Quase impossível sem recriar DB. Faça antes.

</aside>

<aside>
⛔️

**Booleanos para status com mais de 2 estados implícitos.** `is_processed=False, is_failed=False` é o mesmo que "pendente"? Não. Use enum.

</aside>

## 8.2 IA & Custo

<aside>
⛔️

**Imports `langchain.embeddings` ou `langchain.chat_models`.** Vão quebrar na próxima minor. Use sempre os pacotes por provider.

</aside>

<aside>
⛔️

**Recalcular custo histórico com preço novo.** Mentira gerada. Snapshot no momento do salvamento.

</aside>

<aside>
⛔️

**Treinamento RAG síncrono.** Timeout, quota errors, frustração. Sempre Celery.

</aside>

<aside>
⛔️

**Top-K alto sem necessidade.** k=20 estoura context window e custo. k=5 funciona em 90% dos casos.

</aside>

## 8.3 Async

<aside>
⛔️

**Webhook fazendo trabalho síncrono.** Resposta &gt;5s = retry exponencial do provedor = duplicação. View persiste, task processa.

</aside>

<aside>
⛔️

**Cron-no-container com múltiplas réplicas.** Cron duplica execução por réplica. Migre para Beat.

</aside>

<aside>
⛔️

**Task sem `idempotency_key`.** Reprocessamento dobra efeito (2 emails, 2 cobranças). Default: chave externa obrigatória.

</aside>

## 8.4 Infra

<aside>
⛔️

**Senhas default em RabbitMQ/Postgres.** Subdomínio público = porta de invasão. Sempre senha gerada + secret.

</aside>

<aside>
⛔️

**Sem backup do volume `media/`.** Documentos de tenants se perdem com 1 falha de disco. Restic + S3-compatible, retention.

</aside>

<aside>
⛔️

**Update sem `parallelism: 1`.** Todas as réplicas reiniciam ao mesmo tempo = downtime.

</aside>

## 8.5 Desenvolvimento Assistido

<aside>
⛔️

**Prompt sem referenciar PRD/DS/código.** Resultado: solução órfã, fora do padrão, retrabalho.

</aside>

<aside>
⛔️

**"Refatora também" no meio de outra task.** Diff explode, review impossível, regressão garantida.

</aside>

<aside>
⛔️

**Aceitar implementação sem testar UI manualmente.** Type check passa, comportamento real quebra.

</aside>

---

# 9. Referências e Recursos

## 9.1 Documentação Oficial

- **Django 6 Docs:** [https://docs.djangoproject.com/en/6.0/](https://docs.djangoproject.com/en/6.0/)
- **LangChain (provider-separated):** [https://python.langchain.com/docs/](https://python.langchain.com/docs/)
- **LangGraph StateGraph:** [https://langchain-ai.github.io/langgraph/](https://langchain-ai.github.io/langgraph/)
- **Celery 5 + Django:** [https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html)
- **Docker Swarm:** [https://docs.docker.com/engine/swarm/](https://docs.docker.com/engine/swarm/)
- **Traefik:** [https://doc.traefik.io/traefik/](https://doc.traefik.io/traefik/)
- **OpenAI Python SDK 2.x:** [https://github.com/openai/openai-python](https://github.com/openai/openai-python)
- **OpenRouter:** [https://openrouter.ai/docs](https://openrouter.ai/docs)
- **Sentry self-hosted:** [https://develop.sentry.dev/self-hosted/](https://develop.sentry.dev/self-hosted/)
- **MKDocs Material:** [https://squidfunk.github.io/mkdocs-material/](https://squidfunk.github.io/mkdocs-material/)
- **Stripe API:** [https://docs.stripe.com/api](https://docs.stripe.com/api)

## 9.2 Bibliotecas Recomendadas

| **Necessidade** | **Lib** | **Observação** |
| --- | --- | --- |
| Logs JSON | `structlog` ou `python-json-logger` | structlog é mais moderno |
| Test factories | `factory_boy`  • `pytest-django` | `mute_signals` resolve testes ruidosos |
| Forms estilo HTMX | `django-htmx` | Streaming + interatividade sem SPA |
| Storage | `django-storages`  • S3-compatible | Para `media/` em escala |
| Queues observability | Flower + Prometheus exporter | Métricas para Grafana |

## 9.3 Padrões de Pasta de Settings

```python
# settings/base.py
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'apps.accounts', 'apps.tenants', 'apps.catalog', 'apps.agents',
    'apps.conversations', 'apps.enrollments', 'apps.credits', 'apps.billing',
    'apps.webhooks', 'apps.activities', 'apps.gamification',
    'apps.notifications', 'apps.reports', 'apps.integrations', 'apps.landing',
]
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['apps.accounts.backends.EmailBackend']
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_TZ = True
```

## 9.4 Comandos do Dia-a-Dia

```bash
# Local
docker compose up --build
docker compose run --rm app python manage.py migrate
docker compose run --rm app python manage.py createsuperuser

# Prod (Swarm)
docker stack deploy -c docker-stack.yml app
docker service scale app_worker-ai-heavy=4
docker service logs -f --tail 200 app_app

# Backup ad-hoc
restic -r s3:... backup /var/lib/media

# Celery saúde
docker exec -it $(docker ps -qf name=app_app) celery -A core inspect ping
```

---

<aside>
✅

**Critérios de auto-validação atingidos:**

- A Parte I do documento é totalmente genérica, sem menção ao sistema-fonte.
- Padrões cobrem os 8 domínios obrigatórios.
- Cada padrão tem nome, problema, solução, quando aplicar/não aplicar, exemplo, trade-offs.
- Estrutura segue as 10 seções obrigatórias.
- Inclui exemplos de Python, YAML, Dockerfile, Bash, Mermaid.
- Documento privado no Notion (sem teamspace público).

</aside>

---

# 10. Aplicação do Blueprint: SmartAudit

<aside>
📍

**Parte específica do projeto** — Esta seção aplica os padrões reutilizáveis da
Parte I ao SmartAudit. Ela é a fonte canônica para decisões arquiteturais,
sequência de implementação e estado das sprints. O arquivo
`docs/implementation_plan.md` permanece como levantamento inicial e histórico.

**Início da execução:** 2026-09-03 — **Estado:** fundação Django implementada.

</aside>

## 10.1 Visão do Produto e Fronteira do MVP

O SmartAudit é um SaaS B2B multi-tenant para vendedores e lojistas de
e-commerce. Ele ingere CT-es, NF-es e tabelas de frete contratadas; reconstrói o
valor esperado do frete; compara o esperado com o cobrado; e entrega evidência
auditável das divergências.

O MVP inclui identidade e tenants, ingestão de documentos fiscais, cadastro de
tabelas de frete, motor determinístico de auditoria, API autenticada e execução
local reproduzível. Relatórios avançados e workflow completo de contestação são
posteriores ao MVP.

**IA generativa não pertence ao MVP.** Os padrões LangChain/LangGraph da Parte I
continuam disponíveis para outros produtos ou uma futura funcionalidade
explicitamente aprovada, mas não serão instalados nem usados para cálculos
fiscais. Auditoria de frete deve ser determinística, explicável e reproduzível.

## 10.2 Decisões Arquiteturais Vigentes

| ID | Decisão | Consequência prática |
| --- | --- | --- |
| SA-ADR-001 | Esta seção e o código atual são canônicos. | O plano inicial é histórico; checkboxes só são marcados após teste/evidência. |
| SA-ADR-002 | Bounded context = Django app. | `accounts`, `tenants`, `documents`, `freight`, `audits` e `reports` não misturam models. |
| SA-ADR-003 | `User` é identidade global; acesso ocorre por `Membership`. | Um usuário pode operar mais de um tenant sem duplicar conta. Papel pertence ao vínculo, não ao usuário. |
| SA-ADR-004 | Shared schema com FK `tenant` obrigatória. | Todo model de negócio herda `TenantScopedModel`; payloads nunca escolhem tenant sem validar membership. |
| SA-ADR-005 | PostgreSQL é o banco canônico; SQLite é apenas bootstrap/teste local. | Compose e `psycopg` entram antes de dados reais; produção nunca usa SQLite. |
| SA-ADR-006 | Django Admin usa sessão; API do MVP usa JWT. | Domínios expõem routers Django Ninja; login/refresh JWT será integrado sem mover regra de negócio para endpoints. |
| SA-ADR-007 | RabbitMQ é broker Celery; Redis é cache/result backend. | Corrige a simplificação do plano inicial e preserva entrega confiável de lotes. |
| SA-ADR-008 | XML original vai para storage; dados normalizados vão para PostgreSQL. | MinIO em desenvolvimento e S3-compatible em produção; banco guarda chave e metadados do objeto. |
| SA-ADR-009 | Dinheiro usa `Decimal`; percentuais são frações de `0` a `1`. | `0.0200` significa 2%; nenhum cálculo monetário usa `float`. |
| SA-ADR-010 | Registros operacionais não são apagados em cascata com tenant/user. | FKs críticas usam `PROTECT`; tenant e membership são desativados por status. |

### Resolução do tenant

- Na UI autenticada, o tenant ativo será guardado na sessão e sempre validado
  contra uma `Membership` ativa.
- Na API, o cliente enviará `X-Tenant-ID`; o resolvedor aceitará o valor somente
  se o JWT representar usuário com membership ativa naquele tenant.
- `tenant_id` vindo no corpo da requisição não é fonte de autorização.
- Managers/querysets oferecem `for_tenant(tenant)`, mas o filtro explícito não
  substitui testes de isolamento.

## 10.3 Contextos e Responsabilidades

| App | Responsabilidade | Entidades principais | MVP |
| --- | --- | --- | --- |
| `core` | Primitivas compartilhadas e saúde do serviço. | `BaseModel`, `TenantScopedModel`, `TenantQuerySet` | Sim |
| `accounts` | Identidade e autenticação por e-mail. | `User` | Sim |
| `tenants` | Empresa cliente, preferências e autorização contextual. | `Tenant`, `Membership` | Sim |
| `documents` | Upload, validação e parsing de CT-e/NF-e. | `DocumentUpload`, `CTe`, `NFe`, `CTeNFeLink` | Sim |
| `freight` | Transportadoras, vigências e regras contratadas. | `Carrier`, `FreightTable`, `FreightRule`, `CubageFactor`, `ICMSRule` | Sim |
| `audits` | Orquestração determinística e trilha de divergências. | `AuditRun`, `AuditResult` | Sim |
| `reports` | Consultas analíticas e exportações. | Projeções/exports, sem duplicar fatos | Pós-MVP |

O workflow de contestação começa pós-MVP. Quando entrar, `AuditDispute` ficará em
`audits`, pois é parte do ciclo de vida de um resultado de auditoria.

## 10.4 Visão de Componentes

```mermaid
flowchart LR
    USER["Operador / Administrador"] --> WEB["Django Admin / futura UI"]
    CLIENT["Cliente de API"] --> API["Django Ninja + JWT"]
    WEB --> TENANT["Tenant resolver + RBAC"]
    API --> TENANT
    TENANT --> DOCS["documents"]
    TENANT --> FREIGHT["freight"]
    TENANT --> AUDITS["audits"]
    DOCS --> PG[(PostgreSQL)]
    FREIGHT --> PG
    AUDITS --> PG
    DOCS --> OBJECT[(MinIO / S3)]
    DOCS --> RMQ["RabbitMQ"]
    AUDITS --> RMQ
    RMQ --> WORKER["Celery workers"]
    WORKER --> PG
    WORKER --> OBJECT
    REDIS[(Redis)] -. cache/results .-> WEB
    REDIS -. task results .-> WORKER
```

Dependências entre contextos seguem uma direção simples:

```text
accounts <- tenants <- documents <- audits
                   \-> freight  <-/
core é importado por todos, mas não importa models concretos de domínio.
reports lê projeções de audits/freight/documents e não recebe escrita operacional.
```

## 10.5 Estrutura de Diretórios Aplicada

```text
smartAudit/
├── manage.py
├── pyproject.toml
├── docs/
│   ├── blueprint-saas-django.md
│   └── implementation_plan.md
├── src/smartaudit/
│   ├── settings/{base,local,production}.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── core/
│   ├── accounts/
│   ├── tenants/
│   ├── documents/             # Sprint 3
│   ├── freight/               # Sprint 4
│   ├── audits/                # Sprint 5
│   └── reports/               # pós-MVP
├── compose/                   # Sprint 2
├── templates/
├── static/
└── media/                     # local; storage externo nos ambientes reais
```

## 10.6 Modelo Inicial e Invariantes

```mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : has
    TENANT ||--o{ MEMBERSHIP : grants
    TENANT ||--o{ DOCUMENT_UPLOAD : owns
    TENANT ||--o{ CTE : owns
    TENANT ||--o{ NFE : owns
    TENANT ||--o{ CARRIER : contracts
    CARRIER ||--o{ FREIGHT_TABLE : publishes
    FREIGHT_TABLE ||--o{ FREIGHT_RULE : contains
    CTE }o--o{ NFE : references
    TENANT ||--o{ AUDIT_RUN : owns
    AUDIT_RUN ||--o{ AUDIT_RESULT : produces
    CTE ||--o{ AUDIT_RESULT : evaluated_by
    FREIGHT_RULE ||--o{ AUDIT_RESULT : explains
```

Invariantes obrigatórios:

1. `User.email` é único sem diferenciar maiúsculas/minúsculas e não existe
   `username`.
2. `(membership.tenant, membership.user)` é único; papel é `admin`, `operator`
   ou `viewer`.
3. Todo registro tenant-scoped tem FK `tenant` e `created_at`/`updated_at`.
4. Chaves de acesso CT-e/NF-e têm 44 dígitos e são únicas **por tenant**, não
   globalmente.
5. Upload e parsing são idempotentes pela combinação tenant + chave de acesso +
   tipo do documento.
6. Uma auditoria persiste inputs relevantes, versão da regra e componentes do
   cálculo; resultados históricos não são recalculados silenciosamente.
7. A divergência só é relevante quando ultrapassa simultaneamente a tolerância
   absoluta e a percentual. Se o total calculado for zero, não se divide por
   zero: o resultado exige classificação explícita do motor.
8. Datas fiscais e vigências são armazenadas com timezone quando representam um
   instante; datas puras continuam `date`.
9. CNPJ e CEP são persistidos normalizados somente com dígitos; formatação é
   responsabilidade de apresentação.

## 10.7 Estratégia de Processamento

O parser e o serviço de persistência serão únicos. O caminho síncrono (até 10
arquivos pequenos) e o assíncrono (11 ou mais, arquivo compactado ou carga
pesada) chamam o mesmo serviço idempotente; não existirão duas implementações do
parser. Auditorias em lote são sempre Celery. A transição canônica de upload é:

```text
pending -> processing -> processed
                      \-> failed
```

Retries só podem repetir trabalho seguro. O erro persistido deve indicar o
arquivo e a etapa sem armazenar segredo ou XML completo em log.

## 10.8 Roadmap Executável

### Sprint 0 — Consolidação arquitetural

**Objetivo:** converter a discussão inicial em decisões rastreáveis e remover
falsos sinais de conclusão.

- [x] Definir persona, fronteira do MVP e bounded contexts.
- [x] Separar `accounts` de `tenants`.
- [x] Escolher `User` global + `Membership` e resolução explícita de tenant.
- [x] Fixar PostgreSQL/RabbitMQ/Redis/MinIO nos papéis corretos.
- [x] Declarar IA generativa fora do MVP determinístico.
- [x] Corrigir o checklist histórico que marcava o MVP não implementado como pronto.

**Evidência:** esta seção e `docs/implementation_plan.md`.

### Sprint 1 — Fundação Django

**Objetivo:** criar a base executável antes da primeira migration de domínio.

- [x] Projeto Django 6.1 em layout `src/` com `manage.py` na raiz.
- [x] Settings separados em `base`, `local` e `production`.
- [x] `BaseModel`, `TenantQuerySet` e `TenantScopedModel` abstratos.
- [x] `User(AbstractUser)` sem username, manager e backend por e-mail.
- [x] `Tenant` com tolerâncias e janela de duplicidade.
- [x] `Membership` com roles e unicidade tenant/usuário.
- [x] Django Admin, migrations iniciais e endpoint `/health/`.
- [x] Testes de identidade, membership e saúde passando.

**Definition of Done:** `manage.py check`, testes e
`makemigrations --check --dry-run` verdes.

### Sprint 2 — Runtime PostgreSQL e fronteira de autorização

- [x] Adicionar `psycopg`, Django Ninja, JWT, Celery e dependências de teste via `uv`.
- [x] Criar `.env.example` sem segredos e validar settings obrigatórios.
- [x] Criar Compose com PostgreSQL, RabbitMQ, Redis e MinIO com healthchecks.
- [x] Implementar resolvedor de tenant para sessão e `X-Tenant-ID` para API.
- [x] Implementar guards de role e testes negativos cross-tenant.
- [x] Expor shell `/api/`, login e refresh JWT.

**Evidência:** lock reproduzível com `uv sync --locked`; settings local e de
produção validados; os quatro serviços do Compose saudáveis; bootstrap Celery
carregando RabbitMQ/Redis; 22 testes passando tanto em SQLite quanto em
PostgreSQL; `manage.py check` e `makemigrations --check --dry-run` verdes.

### Sprint 3 — Documentos fiscais como primeira vertical de negócio

- [x] Modelar upload, CT-e, NF-e e vínculo com constraints por tenant.
- [x] Implementar validação segura de XML (XXE desabilitado) e schemas de erro.
- [x] Implementar parsers puros com fixtures CT-e/NF-e anonimizadas.
- [x] Persistir de forma transacional e idempotente.
- [x] Criar endpoints de upload/listagem/detalhe com isolamento testado.

**Evidência:** migration inicial de `documents` com constraints tenant-scoped;
fixtures CT-e/NF-e anonimizadas e fixture XXE com DTD/entidade externa rejeitada;
rollback de banco e arquivo testado; reenvio da mesma chave sem duplicação;
upload/listagem/detalhe com testes negativos cross-tenant; 39 testes passando
com warnings tratados como erros tanto em SQLite quanto em PostgreSQL.

### Sprint 4 — Transportadoras e tabelas de frete

- [ ] Modelar transportadora, tabela, vigência, faixas, cubagem e ICMS.
- [ ] Publicar template versionado de CSV/XLSX.
- [ ] Validar sobreposição de CEP, peso e vigência antes de ativar tabela.
- [ ] Implementar importação transacional com relatório linha a linha.
- [ ] Testar matching determinístico de tabela e regra.

### Sprint 5 — Motor de auditoria

- [ ] Implementar value objects/serviços puros para peso, componentes e ICMS.
- [ ] Persistir `AuditRun` e snapshot explicável por CT-e.
- [ ] Aplicar tolerância híbrida e classificação de divergência.
- [ ] Detectar duplicidade sem cruzar tenants.
- [ ] Cobrir casos-limite monetários com testes parametrizados.

### Sprint 6 — Lotes, storage e operação

- [ ] Integrar storage MinIO/S3 mantendo apenas referências no banco.
- [ ] Implementar tasks Celery idempotentes para ingestão e auditoria em lote.
- [ ] Separar filas `default`, `documents` e `audits`.
- [ ] Adicionar correlation ID e logs estruturados sem conteúdo fiscal sensível.
- [ ] Testar retry, falha parcial e reprocessamento.

### Sprint 7 — Fechamento do MVP

- [ ] Completar endpoints, paginação e filtros.
- [ ] Executar suíte end-to-end upload -> parsing -> tabela -> auditoria.
- [ ] Auditar todas as queries e testes de isolamento cross-tenant.
- [ ] Documentar backup, restore, deploy e rollback.
- [ ] Validar manualmente cálculos contra amostras aprovadas pelo negócio.

## 10.9 Gates de Qualidade

Uma sprint só recebe `[x]` quando houver evidência proporcional ao risco:

- **Código:** `manage.py check` e migrations estáveis.
- **Domínio:** testes unitários para fórmulas, estados e idempotência.
- **Multi-tenancy:** ao menos um teste negativo provando que tenant A não lê nem
  altera dados do tenant B em cada endpoint.
- **Segurança de XML:** fixture com entidade externa/DTD rejeitada.
- **Banco:** constraints críticas verificadas no PostgreSQL, não apenas SQLite.
- **Async:** reprocessar a mesma task não duplica efeitos.
- **Entrega:** documentação e checklist atualizados no mesmo diff.

## 10.10 Validações de Negócio Necessárias Antes do Motor

Não bloqueiam a fundação, mas precisam de exemplos anonimizados antes das
Sprints 4 e 5:

1. versões/layouts de CT-e e NF-e realmente recebidos pelos primeiros clientes;
2. uma tabela de frete real para fechar colunas, mínimos, adicionais e regras de
   arredondamento;
3. exemplos aprovados de ICMS embutido e destacado;
4. política de CT-e complementar, cancelado e substituído;
5. critério definitivo de duplicidade quando um CT-e referencia várias NF-es.

Até essas amostras existirem, nenhum detalhe fiscal presumido será apresentado
como regra concluída.
