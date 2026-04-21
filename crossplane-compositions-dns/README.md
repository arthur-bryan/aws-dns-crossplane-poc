# Crossplane Compositions DNS

Este Helm chart fornece Compositions e Composite Resource Definitions (XRDs) para provisionamento de recursos AWS Route53, permitindo a gestão self-service de zonas DNS e registros DNS individuais.

## Visão Geral

O chart `crossplane-compositions-dns` implementa abstrações de alto nível para criar e gerenciar:

- **Zonas DNS (Hosted Zones)** - Zonas DNS hospedadas no Route53 com validação de existência
- **Registros DNS** - Registros individuais (A, AAAA, CNAME, TXT, ALIAS) com suporte a weighted routing

## Componentes

### Custom Resource Definitions (CRDs)

#### Zone (`zones.dock.tech`)

Define uma zona DNS hospedada no Route53.

**Campos principais:**

- `name` - Nome do recurso
- `domain`, `subdomain`, `system`, `environment` - Organização hierárquica
- `aws.account` - Account ID AWS (12 dígitos)
- `aws.accountName` - Nome da conta AWS (deve corresponder ao ClusterProviderConfig)
- `zoneName` - Nome da zona DNS (FQDN sem ponto final, ex: `test.dev.dock.tech`)
- `comment` - Comentário opcional para a zona (máx. 256 caracteres)
- `tags` - Tags AWS adicionais (tags de hierarquia são adicionadas automaticamente)

**Status retornado:**

- `zoneId` - ID da hosted zone no Route53
- `nameServers` - Array de servidores DNS para delegação
- `ready` - Indica se a zona está pronta
- `message` - Mensagem de status

**Validações:**

- `zoneName` não pode terminar com `.`
- `zoneName` não pode começar com `-`
- `zoneName` não pode conter `..`

#### Record (`records.dock.tech`)

Define um registro DNS individual em uma zona Route53.

**Campos principais:**

- `name` - Nome do recurso
- `domain`, `subdomain`, `system`, `environment` - Organização hierárquica
- `aws.account` - Account ID AWS (12 dígitos)
- `aws.accountName` - Nome da conta AWS
- `aws.region` - Região AWS (obrigatória para lookup de ALIAS zone IDs)
- `zoneId` - ID da zona Route53 (alternativa ao `zoneName`)
- `zoneName` - Nome da zona DNS (alternativa ao `zoneId`)
- `recordName` - Nome do registro (ex: `www`, `api`, `cdn`)
- `type` - Tipo de registro DNS: `A`, `AAAA`, `CNAME`, `TXT`, `ALIAS`
- `ttl` - TTL em segundos (padrão: 3600, mín: 60, máx: 86400) - não usado para ALIAS
- `values` - Array de valores do registro (obrigatório para A, AAAA, CNAME, TXT)

**Campos para ALIAS records:**

- `aliasTarget.serviceType` - Tipo de serviço AWS (auto-preenche hostedZoneId):
  - `CloudFront` - CloudFront distribution
  - `ALB` - Application Load Balancer
  - `NLB` - Network Load Balancer
  - `S3Website` - S3 website endpoint
  - `APIGateway` - API Gateway regional
  - `GlobalAccelerator` - AWS Global Accelerator
  - `Custom` - Requer `hostedZoneId` manual
- `aliasTarget.dnsName` - Nome DNS do destino
- `aliasTarget.hostedZoneId` - Zone ID do destino (obrigatório apenas para `Custom`)
- `aliasTarget.evaluateTargetHealth` - Avaliar saúde do destino (padrão: false)

**Campos para Weighted Routing:**

- `setIdentifier` - Identificador único para o registro weighted (1-128 caracteres)
- `weight` - Peso do tráfego (0-255) para distribuição proporcional

**Status retornado:**

- `fqdn` - Nome completo do registro DNS
- `recordId` - Identificador do registro
- `ready` - Indica se o registro está pronto
- `message` - Mensagem de status

**Validações:**

- Pelo menos um entre `zoneId` ou `zoneName` deve ser fornecido
- Se tipo for `ALIAS`, `aliasTarget` é obrigatório
- Se tipo não for `ALIAS`, `values` é obrigatório
- Se `serviceType` for `Custom`, `hostedZoneId` é obrigatório
- Se `setIdentifier` for fornecido, `weight` também deve ser fornecido
- Se `weight` for fornecido, `setIdentifier` também deve ser fornecido

### Compositions

As Compositions implementam a lógica de criação dos recursos AWS Route53 usando o Crossplane Function Pipeline com Go Templating.

#### Composition Zone

Cria uma zona DNS hospedada no Route53.

Características:

- Validação automática (verifica se zona já existe via `managementPolicies`)
- Suporte para tags customizadas + tags de hierarquia automáticas
- Comentário padrão: "Managed by APE Platform"
- Status retorna `zoneId` e `nameServers` para delegação

#### Composition Record

Cria registros DNS individuais com lógica avançada.

Características:

- **Lookup de zona**: Se `zoneName` for fornecido, faz lookup automático do `zoneId` usando modo `Observe`
- **Auto-resolução de ALIAS zone IDs**: Mapeia automaticamente o `hostedZoneId` baseado em `serviceType` e região:
  - CloudFront: Global (Z2FDTNDATAQYW2)
  - ALB/NLB/S3Website/APIGateway: Específico por região (70+ mapeamentos)
- **Weighted routing**: Suporte nativo para distribuição de tráfego com múltiplos registros
- **Tipos de registro**: A, AAAA, CNAME, TXT, ALIAS
- Validação e atualização suportadas via `managementPolicies`

## Uso

### Exemplo: Criar Zona DNS

```yaml
apiVersion: dock.tech/v1
kind: Zone
metadata:
  name: test-zone-dev
  namespace: cross-cloud-dns-poc
spec:
  name: test-zone-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account

  zoneName: test.dev.dock.tech
  comment: "Zona de teste para APE platform"

  tags:
    CostCenter: "Engineering"
    Owner: "APE Team"
```

### Exemplo: Registro A

```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: api-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: api-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: api
  type: A
  ttl: 3600
  values:
    - "10.0.1.100"
```

### Exemplo: Registro CNAME

```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: www-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: www-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: www
  type: CNAME
  ttl: 3600
  values:
    - "api.test.dev.dock.tech"
```

### Exemplo: Registro ALIAS (CloudFront)

```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: cdn-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: cdn-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: cdn
  type: ALIAS
  aliasTarget:
    serviceType: CloudFront
    dnsName: d111111abcdef8.cloudfront.net
    evaluateTargetHealth: false
```

### Exemplo: Registro ALIAS (ALB)

```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: app-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: app-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: app
  type: ALIAS
  aliasTarget:
    serviceType: ALB
    dnsName: my-alb-123456789.us-east-2.elb.amazonaws.com
    evaluateTargetHealth: true
```

### Exemplo: Weighted Routing (70% / 30%)

```yaml
# Registro primário - 70% do tráfego
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: api-primary-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: api-primary-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: api
  type: A
  ttl: 60
  values:
    - "10.0.1.100"

  setIdentifier: "primary-us-east-2"
  weight: 70

---
# Registro secundário - 30% do tráfego
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: api-secondary-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: api-secondary-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: api
  type: A
  ttl: 60
  values:
    - "10.0.2.200"

  setIdentifier: "secondary-us-west-2"
  weight: 30
```

### Exemplo: Registro TXT

```yaml
apiVersion: dock.tech/v1
kind: Record
metadata:
  name: verification-test-dev
  namespace: cross-cloud-dns-poc
spec:
  name: verification-test-dev
  domain: cross
  subdomain: cloud
  system: dns-poc
  environment: dev

  aws:
    account: 123456789012
    accountName: dev-account
    region: us-east-2

  zoneName: test.dev.dock.tech
  recordName: _verification
  type: TXT
  ttl: 3600
  values:
    - "v=spf1 include:_spf.google.com ~all"
    - "verification-token-12345"
```

## Configuração

### Values

```yaml
managementPolicies:
  - Observe
  - Create
  - Update
  - Delete
```

Os `managementPolicies` controlam como o Crossplane gerencia os recursos provisionados:

- **Observe**: Monitora recursos existentes (usado para validação de zonas)
- **Create**: Cria novos recursos
- **Update**: Atualiza recursos existentes (permite edição de registros)
- **Delete**: Remove recursos quando o CR é deletado

## Lookup Automático de Zone ID para ALIAS

A composition mapeia automaticamente o `hostedZoneId` baseado no `serviceType`:

### CloudFront (Global)
- Zone ID: `Z2FDTNDATAQYW2`

### Global Accelerator (Global)
- Zone ID: `Z2BJ6XQ5FK7U4H`

### Application Load Balancer (Regional)
- us-east-1: `Z35SXDOTRQ7X7K`
- us-east-2: `Z3AADJGX6KTTL2`
- us-west-1: `Z368ELLRRE2KJ0`
- us-west-2: `Z1H1FL5HABSF5`
- eu-west-1: `Z32O12XQLNTSW2`
- eu-central-1: `Z215JYRZR1TBD5`
- ap-southeast-1: `Z1LMS91P8CMLE5`
- sa-east-1: `Z2P70J7HTTTPLU`

### Network Load Balancer (Regional)
- us-east-1: `Z26RNL4JYFTOTI`
- us-east-2: `ZLMOA37VPKANP`
- us-west-2: `Z18D5FSROUN65G`
- eu-west-1: `Z2IFOLAFXWLO4F`

### S3 Website Endpoint (Regional)
- us-east-1: `Z3AQBSTGFYJSTF`
- us-east-2: `Z2O1EMRO9K5GLX`
- us-west-2: `Z3BJ6K6RIION7M`
- eu-west-1: `Z1BKCTXD74EZPE`

### API Gateway (Regional)
- us-east-1: `Z1UJRXOUMOOFQ8`
- us-east-2: `ZOJJZC49E0EPZ`
- us-west-2: `Z2OJLYMUO9EFXC`
- eu-west-1: `ZLY8HYME6SFDD`

Para outros serviços ou zonas customizadas, use `serviceType: Custom` e forneça `hostedZoneId` manualmente.

## Dependências

Este chart requer:

- Crossplane instalado no cluster
- Provider AWS Route53 (Upbound) configurado
- Função `crossplane-contrib-function-go-templating` instalada
- Função `crossplane-contrib-function-auto-ready` instalada
- ClusterProviderConfig configurado para a conta AWS

## Estrutura de Pastas

```
crossplane-compositions-dns/
├── Chart.yaml              # Metadados do chart
├── values.yaml            # Valores padrão
├── README.md              # Esta documentação
└── templates/
    ├── compositions/      # Compositions que implementam a lógica
    │   ├── zone.yaml
    │   └── record.yaml
    └── crds/              # Definição de recursos customizados
        ├── zone.yaml
        └── record.yaml
```

## Arquitetura

As Compositions utilizam o Function Pipeline do Crossplane:

1. **Go Templating**: Renderiza templates com dados do composite resource
2. **Auto Ready**: Detecta automaticamente quando os recursos estão prontos

### Fluxo de Criação - Zone

1. Cria a Route53 Hosted Zone
2. Aplica tags de hierarquia automaticamente
3. Retorna `zoneId` e `nameServers` no status

### Fluxo de Criação - Record

1. Se `zoneName` fornecido: Cria recurso Zone em modo `Observe` para lookup do `zoneId`
2. Se tipo for `ALIAS`: Resolve `hostedZoneId` baseado em `serviceType` e região
3. Cria o Route53 Record com configuração apropriada
4. Se `setIdentifier` e `weight` fornecidos: Configura weighted routing policy
5. Retorna `fqdn` e `recordId` no status

## Boas Práticas

### Delegação de Zona

Após criar uma zona, use os `nameServers` retornados no status para configurar a delegação na zona pai:

```yaml
# Obter nameservers:
kubectl get zone test-zone-dev -n cross-cloud-dns-poc -o jsonpath='{.status.nameServers}'
```

### TTL para Weighted Routing

Use TTLs baixos (60-300 segundos) para weighted routing para facilitar mudanças rápidas de distribuição:

```yaml
ttl: 60  # Recomendado para weighted routing
```

### ALIAS vs CNAME

Sempre use `ALIAS` records para recursos AWS (ALB, CloudFront, S3):

- ✅ Não incorre em cobranças por queries DNS
- ✅ Pode ser usado no apex da zona (ex: `example.com`)
- ✅ Suporta health checks

CNAME só é necessário para destinos não-AWS ou subdomínios.

### Organização de Registros

Use `setIdentifier` descritivos para weighted routing:

```yaml
setIdentifier: "primary-us-east-2"   # ✅ Descritivo
# Evite:
setIdentifier: "r1"                   # ❌ Não descritivo
```

### Validação de Zona

A composition usa `managementPolicies: [Observe, Create, Update, Delete]` que:

- ✅ Detecta zonas existentes antes de criar
- ✅ Permite atualizações de tags e comentários
- ✅ Previne duplicação acidental

## Limitações

- Route53 é um serviço global, mas `region` ainda é obrigatório no spec para lookup de ALIAS zone IDs (ALB, NLB, etc.)
- Weighted routing requer múltiplos recursos Record com mesmo `recordName` mas `setIdentifier` diferentes
- ALIAS records não suportam TTL customizado (gerenciado pelo serviço destino)

## Suporte

Para questões ou problemas, consulte a documentação da plataforma APE ou contate a equipe de Platform Engineering.
