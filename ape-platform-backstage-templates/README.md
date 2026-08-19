# Backstage Templates - DNS Resources

Este diretório contém templates do Backstage Scaffolder para provisionamento de recursos DNS via APE Platform.

## ️ Importante

**Estes templates são para referência local durante desenvolvimento do POC.**

Para integração com a plataforma APE:
1. Os templates devem ser movidos para o repositório `dock-tech/ape-platform-backstage-templates`
2. Path final: `templates/resources/aws/zone.yaml` e `templates/resources/aws/record.yaml`
3. Shared partials já existem no repo APE - não é necessário duplicá-los

## Estrutura

```
backstage-templates/
├── shared/ # Partials reutilizáveis (DRY)
│ ├── entities/ # Steps relacionados ao catálogo
│ │ ├── clone.yaml # Clona ape-platform-entities
│ │ ├── commit.yaml # Commit das alterações
│ │ ├── push.yaml # Push para master
│ │ ├── fetch-system.yaml # Busca entidade System
│ │ ├── fetch-system-domain.yaml # Busca Domain do System
│ │ └── refresh-entities.yaml # Força refresh do catálogo
│ └── notify.yaml # Notifica usuário

└── templates/
 └── resources/
 └── aws/
 ├── zone.yaml # Cria zona DNS (Route53 Hosted Zone)
 ├── record.yaml # Cria registro DNS
 └── record-edit.yaml # Edita registro DNS existente
```

## Templates Disponíveis

### 1. Zone (Zona DNS)

**Template:** `templates/resources/aws/zone.yaml`
**Tipo:** `resource`
**Visibilidade:** Público (APE, SRE, TechLead)

**Campos do Formulário:**
- `name` - Nome do recurso
- `system` - Sistema (EntityPicker)
- `zoneName` - Nome da zona DNS (ex: `test.dev.dock.tech`)
- `comment` - Comentário opcional (max 256 chars)
- `tags` - Tags AWS adicionais (opcional)

**XRD Correspondente:** `zones.dock.tech` (v1)

**Comportamento:**
- Create-only (sem edição)
- Valida se arquivo já existe
- Cria entidade Resource no catálogo
- ArgoCD sincroniza → Crossplane cria zona no Route53

**Arquivo gerado:**
```yaml
# entities/{domain}/{subdomain}/{system}/resources/dev/zone-{name}-dev.yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
 name: my-zone
 namespace: cross-cloud-dns-poc
spec:
 type: dns-zone
 cloud: aws
 owner: team-name
 system: dns-poc
 zoneName: test.dev.dock.tech
 comment: "My DNS zone"
 tags:
 CostCenter: Engineering
```

---

### 2. Record (Registro DNS)

**Template:** `templates/resources/aws/record.yaml`
**Tipo:** `resource`
**Visibilidade:** Público (APE, SRE, TechLead, Developer)

**Campos do Formulário:**

**Básicos:**
- `name` - Nome do recurso
- `system` - Sistema (EntityPicker)
- `zone` - Zona DNS (EntityPicker - Resource type=dns-zone)
- `recordName` - Nome do registro (ex: `www`, `api`)
- `type` - Tipo do registro (A, AAAA, CNAME, TXT, ALIAS)

**Condicionais por tipo:**

**A / AAAA / CNAME / TXT:**
- `ttl` - TTL em segundos (default: 3600)
- `values` - Array de valores (IPs, hostnames, texto)

**ALIAS:**
- `serviceType` - Tipo de serviço AWS (CloudFront, ALB, NLB, S3Website, APIGateway, GlobalAccelerator, Custom)
- `dnsName` - Nome DNS do destino
- `customZoneId` - Zone ID (apenas se serviceType=Custom)

**Weighted Routing (Opcional):**
- `enableWeightedRouting` - Habilitar roteamento ponderado
- `setIdentifier` - Identificador único
- `weight` - Peso do tráfego (0-255)

**XRD Correspondente:** `records.dock.tech` (v1)

**Comportamento:**
- Permite edição (via `dns-record-edit`)
- Busca zona selecionada do catálogo
- Adiciona anotação `dock.tech/scaffolder-editable-template`
- Persiste parâmetros em `dock.tech/scaffolder-parameters`

**Arquivo gerado:**
```yaml
# entities/{domain}/{subdomain}/{system}/resources/dev/record-{name}-dev.yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
 name: my-record
 namespace: cross-cloud-dns-poc
 annotations:
 dock.tech/scaffolder-editable-template: dns-record-edit
 dock.tech/scaffolder-parameters: '{"name":"my-record",...}'
spec:
 type: dns-record
 cloud: aws
 owner: team-name
 system: dns-poc
 zone: resource:cross-cloud-dns-poc/my-zone
 recordName: api
 recordType: A
 ttl: 3600
 values:
 - 10.0.1.100
```

---

### 3. Record Edit (Edição de Registro)

**Template:** `templates/resources/aws/record-edit.yaml`
**Tipo:** `resource`
**Visibilidade:** Oculto (tag `hidden`)

**Campos Imutáveis (disabled):**
- `name`
- `system`
- `zone`
- `recordName`
- `type`
- `serviceType` (para ALIAS)

**Campos Editáveis:**
- `ttl` - Pode ser ajustado
- `values` - IPs, hostnames podem ser alterados
- `dnsName` - Destino do ALIAS pode mudar
- `weight` - Peso pode ser ajustado
- `setIdentifier` - Pode ser adicionado/modificado

**Comportamento:**
- Usa `roadiehq:utils:merge` (não sobrescreve, apenas atualiza)
- Preserva campos imutáveis
- Atualiza snapshot de parâmetros
- Registra ação de `updated` no activity log

---

## Contrato: Template ↔ XRD

**IMPORTANTE:** Os campos do template devem corresponder exatamente ao schema da XRD.

### Zone Template → Zone XRD

| Campo Template | Campo XRD | Validação |
|----------------|-----------|-----------|
| `name` | `spec.name` | required |
| `system` → `domain/subdomain/system/environment` | `spec.domain/subdomain/system/environment` | required |
| `zoneName` | `spec.zoneName` | required, pattern: `^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$` |
| `comment` | `spec.comment` | optional, maxLength: 256 |
| `tags` | `spec.tags` | optional, object |

### Record Template → Record XRD

| Campo Template | Campo XRD | Validação |
|----------------|-----------|-----------|
| `zone` (Resource ref) | `spec.zoneName` ou `spec.zoneId` | required (one of) |
| `recordName` | `spec.recordName` | required, immutable |
| `type` | `spec.type` | required, enum: [A, AAAA, CNAME, TXT, ALIAS], immutable |
| `ttl` | `spec.ttl` | optional, default: 3600, min: 60, max: 86400 |
| `values` | `spec.values` | required if type != ALIAS, array minItems: 1 |
| `serviceType` | `spec.aliasTarget.serviceType` | required if type = ALIAS, enum, immutable |
| `dnsName` | `spec.aliasTarget.dnsName` | required if type = ALIAS |
| `customZoneId` | `spec.aliasTarget.hostedZoneId` | required if serviceType = Custom |
| `setIdentifier` | `spec.setIdentifier` | optional, required with weight |
| `weight` | `spec.weight` | optional, min: 0, max: 255, required with setIdentifier |

---

## Imutabilidade

**Zone:**
- `zoneName` - Imutável (não pode ser alterado após criação)

**Record:**
- `recordName` - Imutável
- `type` - Imutável
- `zoneName` / `zoneId` - Imutável
- `serviceType` (ALIAS) - Imutável

**Por que imutável?**
- Alterar `recordName` seria criar um registro diferente
- Alterar `type` (A → CNAME) altera a natureza do recurso
- Alterar `serviceType` (CloudFront → ALB) muda a lógica de zone ID

**Solução:** Deletar e recriar o registro com novos valores.

---

## Fluxo de Integração com APE Platform

### Criação de Zona

```
1. Usuário preenche formulário no Backstage
 ↓
2. Template clona ape-platform-entities
 ↓
3. Busca System e Domain do catálogo
 ↓
4. Resolve path hierárquico (ex: cross/cloud/dns-poc)
 ↓
5. Escreve arquivo Resource YAML
 ↓
6. Commit + Push para master
 ↓
7. Backstage ingere nova entidade
 ↓
8. ArgoCD detecta mudança (branch: master)
 ↓
9. Aplica Resource como CR no Kubernetes
 ↓
10. Crossplane lê CR e cria Route53 Zone na AWS
 ↓
11. Status atualizado com zoneId e nameServers
```

### Edição de Registro

```
1. Usuário clica "Edit" na entidade Record no Backstage
 ↓
2. Backstage lê anotação dock.tech/scaffolder-editable-template
 ↓
3. Abre template dns-record-edit
 ↓
4. Pré-preenche com dock.tech/scaffolder-parameters
 ↓
5. Usuário altera values/ttl/weight
 ↓
6. Template usa roadiehq:utils:merge
 ↓
7. Atualiza apenas campos alterados (preserva imutáveis)
 ↓
8. Commit + Push
 ↓
9. ArgoCD sync
 ↓
10. Crossplane atualiza Route53 Record
```

---

## Próximos Passos

Para integrar com APE Platform:

1. **Mover templates para repo APE:**
 ```bash
 # Copiar para ape-platform-backstage-templates
 cp templates/resources/aws/zone.yaml \
 ../ape-platform-backstage-templates/templates/resources/aws/

 cp templates/resources/aws/record.yaml \
 ../ape-platform-backstage-templates/templates/resources/aws/

 cp templates/resources/aws/record-edit.yaml \
 ../ape-platform-backstage-templates/templates/resources/aws/
 ```

2. **Validar shared partials:**
 - `shared/entities/*` já existem no repo APE
 - Não duplicar, usar os existentes via `$yaml`

3. **Testar no Backstage dev:**
 - Criar zona de teste
 - Criar registro A
 - Editar registro (alterar IP)
 - Verificar se CR foi criado no cluster
 - Verificar se zona/registro apareceu no Route53

4. **Documentar no APE:**
 - Atualizar README do ape-platform-backstage-templates
 - Adicionar exemplos de uso
 - Documentar campos obrigatórios

5. **Merge para master:**
 - PR para branch master
 - Review do time APE
 - Merge e deploy

---

## Custom Actions Necessárias

Estas actions já estão instaladas no Backstage APE:

| Action | Plugin | Descrição |
|--------|--------|-----------|
| `github:extras:clone` | dock-tech interno | Clona repositório GitHub |
| `github:extras:commit` | dock-tech interno | Commit com dados do usuário |
| `github:extras:push` | dock-tech interno | Push para GitHub |
| `hierarchy:details:get` | dock-tech interno | Resolve path hierárquico |
| `roadiehq:utils:fs:write` | RoadieHQ | Escreve arquivo |
| `roadiehq:utils:merge` | RoadieHQ | Merge YAML (para edição) |
| `catalog:fetch` | Backstage core | Busca entidades do catálogo |
| `activity-log:publish` | Backstage | Registra ações |
| `notification:send` | Backstage core | Notificação in-app |

---

## Validações Implementadas

### Zone Template
- Verifica se arquivo já existe (previne duplicação)
- Valida pattern do zoneName (FQDN sem dot final)
- MaxLength em comment (256 chars)

### Record Template
- Valida tipo de registro (A, AAAA, CNAME, TXT, ALIAS)
- Campos condicionais corretos por tipo
- ALIAS: serviceType obrigatório
- Custom: customZoneId obrigatório
- Weighted: setIdentifier + weight juntos
- Pattern de IPv4 para A records

### Record Edit Template
- Campos imutáveis marcados como disabled
- Usa merge em vez de overwrite
- Preserva estrutura original
- Atualiza apenas campos editáveis

---

## Troubleshooting

**Problema:** Template não aparece no Backstage
**Solução:** Verificar se está no path correto e sem tag `hidden`

**Problema:** Erro "Zone not found"
**Solução:** Verificar se zona foi criada e sincronizada pelo ArgoCD

**Problema:** Campos não pré-preenchidos na edição
**Solução:** Verificar anotação `dock.tech/scaffolder-parameters` no Resource

**Problema:** Commit falha
**Solução:** Verificar permissões GitHub do usuário Backstage

**Problema:** Custom zone ID não aceito
**Solução:** Verificar pattern `^Z[A-Z0-9]+$`

---

## Referências

- [Backstage Templates](https://backstage.io/docs/features/software-templates/)
- [APE Platform Docs](../ape-backstage-docs/)
- [XRD Definitions](../crossplane-compositions-dns/templates/crds/)
- [Compositions](../crossplane-compositions-dns/templates/compositions/)
