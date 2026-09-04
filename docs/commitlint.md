# Guia de Padrão de Commits (Commitlint)

Este documento estabelece o padrão de mensagens de commit para o repositório **SmartAudit**, baseado na especificação [Conventional Commits](https://www.conventionalcommits.org/) e validado automaticamente via **Commitlint** e **Husky**.

---

## 1. Estrutura da Mensagem

Cada mensagem de commit deve seguir o formato:

```text
<tipo>(<escopo>): <descrição>

[corpo opcional]

[rodapé opcional]
```

### Regras gerais:
- O `<tipo>` deve ser em letras minúsculas.
- O `(<escopo>)` é opcional para mudanças globais, mas quando informado deve estar em minúsculas (`kebab-case`) e pertencer à lista de escopos válidos.
- A `<descrição>` deve ser concisa, no imperativo, iniciando em letra minúscula e **sem ponto final**.
- O cabeçalho completo (`<tipo>(<escopo>): <descrição>`) não deve exceder **100 caracteres**.

---

## 2. Tipos Permitidos

| Tipo | Descrição | Quando usar |
|---|---|---|
| `feat` | Nova funcionalidade | Introdução de novo endpoint, model, service, parser, regra de frete, etc. |
| `fix` | Correção de bug | Ajuste em cálculo incorreto, correção de validação, erro em migration, etc. |
| `docs` | Alterações de documentação | Atualização do blueprint, README, diagramas, docstrings. |
| `style` | Formatação e estilo | Mudanças de formatação de código que não afetam a lógica (espaçamento, linting visual). |
| `refactor` | Refatoração | Mudança interna de código sem alteração de comportamento externo. |
| `perf` | Melhoria de desempenho | Otimização de query SQL, cache, processamento de XML em lote. |
| `test` | Testes | Adição, correção ou refatoração de testes unitários ou de integração. |
| `build` | Sistema de build / empacotamento | Mudanças em `pyproject.toml`, Dockerfile, builds de pacotes. |
| `ci` | Integração Contínua | Configuração de GitHub Actions, scripts de CI, pipelines. |
| `chore` | Manutenções rotineiras | Atualização de arquivos de configuração, scripts internos de tooling. |
| `revert` | Reversão | Reversão de commits anteriores (`git revert`). |

---

## 3. Escopos Permitidos

Os escopos foram padronizados de acordo com os **Bounded Contexts** da arquitetura do SmartAudit (ver Seção 10 do `docs/blueprint-saas-django.md`) e camadas operacionais/transversais do projeto:

### Bounded Contexts (Django Apps)
- `core`: Modelos base (`BaseModel`, `TenantScopedModel`), querysets globais, middleware e saúde.
- `accounts`: Identidade, usuário (`User`), autenticação e login por e-mail.
- `tenants`: Empresa cliente, isolamento de inquilinos e vínculos (`Membership`).
- `documents`: Upload, validação e parsing de CT-e e NF-e (`DocumentUpload`, `CTe`, `NFe`).
- `freight`: Transportadoras, vigências, tabelas e regras de cálculo de frete (`Carrier`, `FreightTable`, etc.).
- `audits`: Orquestrador de conciliação determinística e resultados (`AuditRun`, `AuditResult`).
- `reports`: Consultas analíticas e exportações.

### Escopos Operacionais e Transversais
- `infra`: Compose, PostgreSQL, RabbitMQ, Redis, MinIO, Docker e ambiente operacional.
- `deps`: Atualização e adição de dependências (`uv`, `npm`).
- `docs`: Documentação técnica, arquitetura e blueprints.
- `ci`: Pipelines e automações de integração contínua.
- `config`: Configurações de ambiente, settings do Django (`settings/`), variáveis de ambiente.
- `release`: Versionamento e tags de liberação.

---

## 4. Exemplos

### Commits Válidos ✅
```bash
feat(tenants): add membership uniqueness validation
fix(accounts): resolve case-insensitive email collision
docs(audits): document discrepancy tolerance formula
test(core): add isolation tests for TenantScopedModel
chore(deps): bump django from 6.1.0 to 6.1.1
ci: add test workflow for pull requests
docs: update architecture blueprint section 10
refactor(documents): extract xml parser into dedicated service
```

### Commits Inválidos ❌
```bash
# Erro: tipo com letra maiúscula e escopo fora da lista
Feat(login): add login endpoint

# Erro: escopo desconhecido
fix(frontend): adjust button color

# Erro: descrição iniciada com maiúscula e terminada com ponto
feat(tenants): Add membership validation.

# Erro: formato fora do padrão conventional commits
ajuste no calculo de frete
```

---

## 5. Setup Local e Verificação

### Instalação dos Git Hooks
Ao clonar o repositório, certifique-se de executar o comando abaixo para ativar o hook do Husky:

```bash
npm install
```

O Husky configurará automaticamente o hook `commit-msg` chamando o Commitlint a cada `git commit`.

### Validando uma mensagem manualmente
Você pode testar uma mensagem antes de commitar:

```bash
echo "feat(freight): add cubage factor rule" | npx commitlint
```

### Validando os commits recentes
Para validar o último commit realizado:

```bash
npx commitlint --from=HEAD~1
```
