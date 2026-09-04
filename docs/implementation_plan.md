# SmartAudit — Sistema de Conciliação e Auditoria de Frete

> **Status: consolidado.** Este foi o levantamento inicial do produto e é
> preservado como registro da discussão. As decisões arquiteturais vigentes, o
> estado executado e o roadmap com Definition of Done estão na seção
> **10. Aplicação do Blueprint: SmartAudit** de
> [`blueprint-saas-django.md`](blueprint-saas-django.md). Em caso de conflito, a
> seção 10 e o código atual prevalecem. Checkboxes abaixo representam escopo
> pretendido, não trabalho já concluído.

Plataforma SaaS multi-tenant para vendedores/lojistas de e-commerce que automatiza a conferência de fretes cobrados por transportadoras, comparando valores cobrados (CT-e) com as tabelas de frete contratadas.

---

## Resumo das Decisões

| Decisão | Escolha |
|---|---|
| **Persona** | Vendedores/lojistas de e-commerce (SaaS multi-tenant) |
| **Multi-tenancy** | Schema compartilhado com `tenant_id` |
| **Banco de dados** | PostgreSQL |
| **Framework** | Django 6.1 + Django Ninja (API) |
| **Autenticação** | JWT com roles (Admin, Operador, Visualizador) |
| **Task Queue** | Celery + Redis |
| **Armazenamento XML** | Dados parseados no banco + XML original em S3/MinIO |
| **Processamento** | Síncrono (1-10 arquivos) / Assíncrono via Celery (lotes) |
| **Deploy** | Docker + Docker Compose (dev), Cloud container (prod) |

---

## 1. Domínios (Bounded Contexts) e Django Apps

### 1.1. `accounts` — Gestão de Tenants e Usuários
**Responsabilidade**: Cadastro de tenants (empresas/lojistas), usuários, autenticação JWT e controle de acesso.

**Entidades**:
- **Tenant**: Empresa/lojista que usa o sistema
  - `id`, `name`, `cnpj`, `is_active`, `created_at`
  - Configurações: tolerância de divergência (valor fixo + percentual)
- **User**: Usuário vinculado a um tenant
  - `id`, `tenant_id`, `email`, `role` (ADMIN | OPERATOR | VIEWER), `is_active`

**Regras de negócio**:
- Todo usuário pertence a exatamente 1 tenant
- Admin pode gerenciar usuários do seu tenant
- Operador pode fazer uploads, executar auditorias, contestar
- Viewer é somente leitura
- Todas as queries são filtradas por `tenant_id` (isolamento de dados)

---

### 1.2. `documents` — Documentos Fiscais (CT-e e NF-e)
**Responsabilidade**: Upload, parsing, armazenamento e validação de XMLs de CT-e e NF-e.

**Entidades**:
- **CTe** (Conhecimento de Transporte Eletrônico):
  - `id`, `tenant_id`, `access_key` (chave de acesso, 44 dígitos)
  - `number`, `series`, `issue_date`, `status` (NORMAL | CANCELED | COMPLEMENTAR)
  - Remetente: `sender_cnpj`, `sender_name`, `sender_city`, `sender_state`, `sender_zip`
  - Destinatário: `recipient_cnpj`, `recipient_name`, `recipient_city`, `recipient_state`, `recipient_zip`
  - Transportadora: `carrier_cnpj`, `carrier_name`
  - Valores: `total_freight`, `freight_weight`, `cubed_weight`, `charged_weight`
  - Componentes: `base_freight`, `ad_valorem`, `gris`, `toll`, `tas_tda`, `icms_value`, `icms_rate`, `other_charges`
  - `service_type` (convencional, expresso, etc.)
  - `xml_file_path` (referência ao XML original no S3/MinIO)
  - `raw_xml_data` (JSONField com dados brutos parseados para referência)

- **NFe** (Nota Fiscal Eletrônica):
  - `id`, `tenant_id`, `access_key`
  - `number`, `series`, `issue_date`
  - Emitente: `issuer_cnpj`, `issuer_name`
  - Destinatário: `recipient_cnpj`, `recipient_name`, `recipient_zip`
  - `total_value` (valor total dos produtos)
  - `total_weight`, `total_volume`
  - Itens: armazenados como JSONField ou tabela separada (peso/volume por item)
  - `xml_file_path`

- **CTeNFeLink** (vínculo CT-e ↔ NF-e):
  - `cte_id`, `nfe_id` (many-to-many, pois 1 CT-e pode referenciar N NF-es)

- **DocumentUpload** (registro de uploads):
  - `id`, `tenant_id`, `uploaded_by`, `upload_date`
  - `file_name`, `file_type` (CTE | NFE), `file_path`
  - `status` (PENDING | PROCESSING | PROCESSED | ERROR)
  - `error_message`, `processed_at`

**Regras de negócio**:
- CT-e e NF-e são identificados unicamente pela **chave de acesso** (44 dígitos)
- Upload duplicado da mesma chave de acesso deve ser rejeitado (idempotência)
- O vínculo CT-e ↔ NF-e é feito automaticamente pela chave de acesso da NF-e referenciada no XML do CT-e (campo `infNFe/chave`)
- XMLs originais são armazenados em S3/MinIO; dados parseados ficam no PostgreSQL
- Upload de 1-10 arquivos: processamento síncrono
- Upload de 11+ arquivos: processamento assíncrono via Celery, com status consultável

---

### 1.3. `freight` — Tabelas e Regras de Frete
**Responsabilidade**: Cadastro e gestão das tabelas de frete contratadas com transportadoras.

**Entidades**:
- **Carrier** (Transportadora):
  - `id`, `tenant_id`, `cnpj`, `name`, `is_active`

- **FreightTable** (Tabela de frete):
  - `id`, `tenant_id`, `carrier_id`, `name`, `service_type`
  - `valid_from`, `valid_until` (vigência)
  - `is_active`, `uploaded_file_path`

- **FreightRule** (Regra/faixa da tabela):
  - `id`, `freight_table_id`
  - Faixa de CEP: `origin_zip_start`, `origin_zip_end`, `dest_zip_start`, `dest_zip_end`
  - Faixa de peso: `weight_min`, `weight_max`
  - `base_price` (valor fixo da faixa)
  - `price_per_excess_kg` (valor por kg excedente)
  - `ad_valorem_rate` (% sobre valor da mercadoria)
  - `gris_rate` (% GRIS)
  - `toll_value` (pedágio/GNTC)
  - `tas_tda_value` (taxa de dificuldade)
  - `dispatch_fee` (taxa de despacho)
  - `delivery_days` (prazo de entrega em dias)

- **CubageFactor** (Fator de cubagem por transportadora):
  - `id`, `freight_table_id`
  - `cubage_factor` (ex: 300 para rodoviário — divide volume em cm³ por 300 para obter peso cubado)

- **ICMSRule** (Regras de ICMS):
  - `id`, `freight_table_id`
  - `origin_state`, `dest_state`, `icms_rate`
  - `icms_included` (se o ICMS já está embutido nos valores ou é adicionado)

**Regras de negócio**:
- Uma transportadora pode ter múltiplas tabelas (por tipo de serviço, por vigência)
- Apenas 1 tabela por transportadora + tipo de serviço pode estar ativa por vez
- O frete é calculado usando o **maior** entre peso real e peso cubado (peso cubado = volume / fator de cubagem)
- Upload via template padronizado (Excel/CSV) fornecido pelo SmartAudit
- CEPs são tratados como faixas numéricas para lookup eficiente

---

### 1.4. `audit` — Motor de Auditoria e Divergências
**Responsabilidade**: Recalcular frete, comparar com valores cobrados, identificar divergências e gerenciar contestações.

**Entidades**:
- **AuditRun** (Execução de auditoria):
  - `id`, `tenant_id`, `created_by`, `created_at`
  - `status` (PENDING | RUNNING | COMPLETED | FAILED)
  - `cte_count`, `divergence_count`, `total_overbilled`, `total_underbilled`

- **AuditResult** (Resultado por CT-e):
  - `id`, `audit_run_id`, `cte_id`
  - **Valores recalculados**: `calculated_base_freight`, `calculated_ad_valorem`, `calculated_gris`, `calculated_toll`, `calculated_tas_tda`, `calculated_icms`, `calculated_total`
  - **Valores cobrados** (do CT-e): `charged_total`
  - **Divergência**: `divergence_value` (cobrado - calculado), `divergence_percentage`
  - `status` (CONFORMING | DIVERGENT | DUPLICATE | ERROR)
  - `divergence_type` (OVERBILLED | UNDERBILLED | NONE)
  - `matched_freight_table_id` (qual tabela de frete foi usada)
  - `matched_freight_rule_id` (qual regra/faixa)
  - `notes` (observações, detalhes do erro)
  - **Detalhes de validação** (JSONField):
    - Peso validado? (CT-e vs. NF-e)
    - CEP correto?
    - Taxas conferidas individualmente?

- **AuditDispute** (Contestação):
  - `id`, `audit_result_id`, `created_by`, `created_at`
  - `status` (OPEN | RESOLVED | UNRESOLVED)
  - `resolution_notes`, `resolved_at`, `resolved_by`

**Regras de negócio (Motor de Auditoria)**:

1. **Matching de tabela**: Para cada CT-e, encontrar a tabela de frete ativa da transportadora (`carrier_cnpj`) + tipo de serviço na data de emissão
2. **Matching de regra**: Dentro da tabela, encontrar a regra que cobre o CEP de origem/destino e a faixa de peso
3. **Cálculo de peso**: Comparar peso real (do CT-e) com peso cubado (volume / fator de cubagem). Usar o maior.
4. **Validação de peso**: Se houver NF-e vinculada, comparar peso do CT-e com peso da NF-e (sinalizar se divergir)
5. **Recálculo do frete**:
   - Frete base = `base_price` + (`peso excedente` × `price_per_excess_kg`)
   - Ad Valorem = `valor da mercadoria` × `ad_valorem_rate`
   - GRIS = `valor da mercadoria` × `gris_rate`
   - Pedágio = `toll_value`
   - TAS/TDA = `tas_tda_value`
   - Subtotal = soma de todos
   - ICMS = Subtotal / (1 - `icms_rate`) - Subtotal (se ICMS embutido)  
     OU Subtotal × `icms_rate` (se ICMS destacado)
   - **Total calculado** = Subtotal + ICMS
6. **Comparação**: `divergência = valor cobrado (CT-e) - total calculado`
7. **Tolerância**: Divergência é relevante se:
   - `|divergência|` > tolerância em valor fixo do tenant **E**
   - `|divergência / total calculado|` > tolerância percentual do tenant
   - (ou seja, aplica-se a tolerância híbrida: ignora a divergência se ela estiver dentro de **qualquer um** dos limites)
8. **Duplicidade**: Identificar CT-es com mesma chave de NF-e referenciada, mesmo valor, e datas próximas

**Workflow de contestação**:
```
PENDENTE → AUDITADO (Conforme/Divergente) → CONTESTADO → RESOLVIDO / NÃO RESOLVIDO
```

---

### 1.5. `reports` — Relatórios e Exportação
**Responsabilidade**: Geração de relatórios analíticos e exportação de dados.

**Funcionalidades (pós-MVP)**:
- Dashboard de divergências: total cobrado a mais / a menos por período
- Relatório por transportadora: ranking de divergências
- Exportação em CSV, Excel (openpyxl) e PDF (weasyprint ou reportlab)

---

## 2. Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.13 |
| Framework Web | Django 6.1 |
| API | Django Ninja |
| Banco de Dados | PostgreSQL 16+ |
| Task Queue | Celery + Redis |
| Object Storage | MinIO (dev) / S3 (prod) |
| Parsing XML | lxml / defusedxml |
| Parsing Excel | openpyxl |
| Auth | Django auth + djangorestframework-simplejwt (compatível com Ninja) |
| Containerização | Docker + Docker Compose |
| Build | uv |

---

## 3. Estrutura de Diretórios Proposta

```
src/smartaudit/
├── settings/
│   ├── base.py
│   ├── local.py
│   └── production.py
├── accounts/
│   ├── models.py          # Tenant, User
│   ├── api.py             # Endpoints de auth, tenant, users
│   ├── schemas.py         # Pydantic schemas (Django Ninja)
│   ├── services.py        # Lógica de negócio
│   ├── admin.py
│   └── tests/
├── documents/
│   ├── models.py          # CTe, NFe, CTeNFeLink, DocumentUpload
│   ├── api.py             # Upload endpoints
│   ├── schemas.py
│   ├── services.py        # Lógica de upload e validação
│   ├── parsers/
│   │   ├── cte_parser.py  # Parser de XML CT-e
│   │   └── nfe_parser.py  # Parser de XML NF-e
│   ├── tasks.py           # Celery tasks (processamento de lotes)
│   └── tests/
├── freight/
│   ├── models.py          # Carrier, FreightTable, FreightRule, CubageFactor, ICMSRule
│   ├── api.py             # CRUD de transportadoras e tabelas
│   ├── schemas.py
│   ├── services.py        # Cálculo de frete, matching de regra
│   ├── importers/
│   │   └── table_importer.py  # Parser de planilhas Excel/CSV
│   └── tests/
├── audit/
│   ├── models.py          # AuditRun, AuditResult, AuditDispute
│   ├── api.py             # Executar auditoria, consultar resultados, contestar
│   ├── schemas.py
│   ├── services.py        # Motor de auditoria (orquestração)
│   ├── engine/
│   │   ├── calculator.py  # Recálculo de frete
│   │   ├── comparator.py  # Comparação cobrado vs. calculado
│   │   ├── validator.py   # Validações (peso, CEP, duplicidade)
│   │   └── tolerance.py   # Regras de tolerância
│   ├── tasks.py           # Celery tasks (auditoria em lote)
│   └── tests/
├── reports/
│   ├── api.py             # Endpoints de relatórios
│   ├── schemas.py
│   ├── services.py        # Geração de relatórios
│   ├── exporters/
│   │   ├── csv_exporter.py
│   │   ├── excel_exporter.py
│   │   └── pdf_exporter.py
│   └── tests/
├── core/
│   ├── middleware.py       # Tenant middleware (inject tenant_id)
│   ├── models.py          # Base models (TenantAwareModel)
│   ├── permissions.py     # Permission classes
│   ├── pagination.py      # Paginação padrão
│   └── storage.py         # S3/MinIO storage backend
├── manage.py
├── urls.py
├── asgi.py
└── wsgi.py
```

---

## 4. Endpoints da API (MVP)

### Accounts
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/auth/login` | Login (retorna JWT) |
| POST | `/api/auth/refresh` | Refresh token |
| GET | `/api/tenants/me` | Dados do tenant logado |
| PATCH | `/api/tenants/me` | Atualizar configurações (tolerância) |
| GET | `/api/users/` | Listar usuários do tenant |
| POST | `/api/users/` | Criar usuário |

### Documents
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/documents/upload` | Upload de XMLs (CT-e e/ou NF-e) |
| GET | `/api/documents/uploads` | Listar uploads com status |
| GET | `/api/documents/ctes` | Listar CT-es do tenant |
| GET | `/api/documents/ctes/{id}` | Detalhe de um CT-e |
| GET | `/api/documents/nfes` | Listar NF-es do tenant |
| GET | `/api/documents/nfes/{id}` | Detalhe de uma NF-e |

### Freight
| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/carriers/` | Listar transportadoras |
| POST | `/api/carriers/` | Cadastrar transportadora |
| GET | `/api/freight-tables/` | Listar tabelas de frete |
| POST | `/api/freight-tables/` | Criar tabela (upload planilha) |
| GET | `/api/freight-tables/{id}` | Detalhe da tabela (com regras) |
| DELETE | `/api/freight-tables/{id}` | Desativar tabela |

### Audit
| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/api/audits/` | Executar nova auditoria |
| GET | `/api/audits/` | Listar auditorias |
| GET | `/api/audits/{id}` | Detalhe da auditoria (com resultados) |
| GET | `/api/audits/{id}/results` | Resultados paginados |
| POST | `/api/audits/results/{id}/dispute` | Abrir contestação |
| PATCH | `/api/audits/disputes/{id}` | Atualizar/resolver contestação |

---

## 5. Regras de Negócio Consolidadas

### Tolerância de Divergência
- Configurável por tenant: valor fixo (R\$) + percentual (%)
- A divergência é **ignorada** se estiver dentro de **qualquer um** dos dois limites
- Exemplo: tolerância de R\$ 5,00 E 2%. Se o frete recalculado é R\$ 100,00 e o cobrado é R\$ 104,00, a divergência de R\$ 4,00 (4%) está dentro do limite de R\$ 5,00, então é considerada **conforme**

### Peso Cobrado
- O sistema compara peso real × peso cubado e usa o **maior** (peso taxado)
- Peso cubado = (comprimento × largura × altura em cm) ÷ fator de cubagem
- Fator de cubagem padrão rodoviário: 300

### Duplicidade
- Um CT-e é considerado duplicado se existir outro CT-e no mesmo tenant com:
  - Mesma(s) chave(s) de NF-e referenciada(s)
  - Mesmo valor total
  - Mesma transportadora
  - Data de emissão próxima (configurável, padrão: 30 dias)

### ICMS
- Pode ser **embutido** (já incluso no frete base) ou **destacado** (adicionado ao final)
- Depende da configuração na tabela de frete + UF de origem/destino
- Alíquotas variam por UF (7%, 12%, 18%, etc.)

---

## 6. Escopo do MVP

### Incluso no MVP
- [ ] Cadastro de tenant e usuários com JWT
- [ ] Upload de XML de CT-e com parsing
- [ ] Upload de XML de NF-e com parsing  
- [ ] Vínculo automático CT-e ↔ NF-e por chave de acesso
- [ ] Cadastro de transportadoras
- [ ] Upload de tabela de frete (template padronizado Excel/CSV)
- [ ] Motor de auditoria: recálculo, comparação, tolerância, duplicidade
- [ ] API REST com Django Ninja
- [ ] Docker Compose para ambiente local

### Fora do MVP (Fase 2+)
- [ ] Dashboard de divergências
- [ ] Relatórios por transportadora
- [ ] Exportação CSV/Excel/PDF
- [ ] Workflow de contestação
- [ ] Integração com SEFAZ (Distribuição DFe)
- [ ] Integração com marketplaces
- [ ] Alertas automáticos (e-mail, webhook)

---

## Verification Plan

### Automated Tests
- Testes unitários para cada parser de XML (CT-e e NF-e) com XMLs reais/mock
- Testes unitários para o motor de auditoria (recálculo, comparação, tolerância)
- Testes de integração para upload + parsing + auditoria end-to-end
- Testes de API para cada endpoint

```bash
python -m pytest src/ --cov=smartaudit
```

### Manual Verification
- Upload de XMLs reais de CT-e e NF-e e verificar parsing correto
- Criar tabela de frete e executar auditoria, conferir manualmente os valores recalculados
- Testar isolamento entre tenants (tenant A não vê dados do tenant B)
