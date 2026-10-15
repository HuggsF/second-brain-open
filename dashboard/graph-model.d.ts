/**
 * Contratos documentais. Este arquivo não é carregado pelo dashboard nem valida JSON.
 * CatalogV1 descreve a entrada; SnapshotV1, o bundle gerado carregado no browser.
 * KnowledgeGraphV2 é uma proposta sem migração.
 * IDs, datas ISO-8601, hashes e números finitos exigem validação em runtime.
 */
export type EntityId = string;
export type EdgeId = string;
export type ViewId = string;
export type SourceId = string;
export type TenantId = string;
export type PolicyRef = string;
export type ActionRef = string;
export type CommandRef = string;
export type ISODateTime = string;
export type SHA256 = string;
export type JsonValue = null | boolean | number | string | readonly JsonValue[] | {
  readonly [key: string]: JsonValue;
};

/** Catálogo canônico atual: IDs/endpoints continuam escalares e relações paralelas são válidas. */
export interface CatalogV1 {
  readonly version: 1;
  readonly views: readonly { readonly id: ViewId; readonly label: string }[];
  readonly nodes: readonly CatalogNodeV1[];
  readonly edges: readonly CatalogEdgeV1[];
}
/** `local` é aceito por schema.js, mesmo sem ocorrências no catálogo consultado. */
export type EvidenceV1 = 'documentado' | 'implementado' | 'local' | 'parcial' | 'proposto' | 'relatado';
export interface DeploymentV1 {
  readonly label: string;
  readonly sha?: string;
  readonly source?: string;
  readonly verified_at?: string;
}
export interface CatalogNodeV1 {
  readonly id: EntityId;
  readonly label: string;
  /** Texto curado livre na v1, sem inferir equivalência com EntityKind da v2. */
  readonly type: string;
  readonly domain: string;
  readonly evidence: EvidenceV1;
  readonly document: string;
  readonly views: Readonly<Record<ViewId, readonly [number, number]>>;
  readonly issues?: readonly string[];
  readonly aliases?: readonly string[];
  readonly valid_at?: string;
  readonly deployment?: DeploymentV1;
}
export interface CatalogEdgeV1 {
  readonly id: EdgeId;
  readonly source: EntityId;
  readonly target: EntityId;
  readonly relation: string;
  readonly view: ViewId;
  readonly evidence: EvidenceV1;
  readonly source_file: string;
  readonly valid_at?: string;
  readonly deployment?: DeploymentV1;
}

/** Saída atual de build_graph.py, exposta em window.KIOSK_GRAPH por graph-data.js. */
export interface SnapshotV1 extends CatalogV1 {
  readonly documents: Readonly<Record<string, SnapshotDocumentV1>>;
  readonly teams: readonly SnapshotTeamV1[];
  readonly protocols: Readonly<Record<string, SnapshotProtocolV1>>;
  readonly templates: readonly SnapshotTemplateV1[];
  readonly built_from: string;
  readonly snapshot_id: SHA256;
  readonly built_at: ISODateTime;
}
/** Não há coleção `sources` na v1: as fontes estão no mapa `documents`. */
export interface SnapshotDocumentV1 {
  readonly text: string;
  readonly title: string;
  readonly category: string;
  readonly sha256: SHA256;
  readonly lines: number;
  readonly modified_at: ISODateTime;
}
/** Metadados copiados de teams/teams.yaml quando o loader YAML está disponível. */
export interface SnapshotTeamV1 {
  readonly id: string;
  readonly name: string;
  readonly category: string;
  readonly scope?: string;
  readonly systems?: readonly string[];
  readonly rules?: readonly string[];
  readonly playbooks?: readonly string[];
  readonly channels?: readonly {
    readonly type: string;
    readonly target: string;
    readonly protocol: string;
    readonly description?: string;
  }[];
}
export interface SnapshotProtocolV1 {
  readonly description: string;
  readonly artifact: string;
  readonly template: string;
}
export interface SnapshotTemplateV1 {
  readonly id: string;
  readonly title: string;
  readonly path: string;
  readonly lines: number;
}

/** PROPOSTA V2: rótulos de segurança são dados não confiáveis, nunca concessões de acesso. */
export type Classification = 'public' | 'internal' | 'confidential' | 'restricted';
export interface DataScope {
  readonly tenantId: TenantId;
  readonly classification: Classification;
  /** Referências descritivas. O servidor resolve e aplica as políticas efetivas. */
  readonly policyRefs?: readonly PolicyRef[];
}
export interface Provenance {
  readonly sourceId: SourceId;
  readonly documentSha256: SHA256;
  readonly method: 'curated' | 'extracted' | 'observed';
  readonly section?: string;
  /** Linhas 1-based, início <= fim; ambas obrigatórias ou ambas ausentes. */
  readonly lines?: { readonly start: number; readonly end: number };
  readonly assertedAt: ISODateTime;
  readonly observedAt?: ISODateTime;
  readonly reviewerRef?: string;
}
export type Evidence =
  | { readonly status: 'unknown' | 'proposed'; readonly explanation: string }
  | { readonly status: 'reported' | 'documented' | 'partial' | 'implemented'; readonly provenance: readonly [Provenance, ...Provenance[]] }
  | { readonly status: 'verified'; readonly provenance: readonly [Provenance, ...Provenance[]]; readonly verifiedAt: ISODateTime; readonly verifierRef: string };
export interface SourceDocument extends DataScope {
  readonly id: SourceId;
  /** Referência opaca do vault/registro; não permite leitura arbitrária do filesystem. */
  readonly documentRef: string;
  readonly sha256: SHA256;
  readonly revision?: string;
  readonly validAt?: ISODateTime;
}
export interface LayoutMetadata {
  /** Ordenação/rank são sugestões visuais finitas; não mudam custo ou semântica. */
  readonly order?: number;
  readonly rank?: number;
}
export interface NodeBase<K extends EntityKind> extends DataScope {
  readonly id: EntityId;
  readonly kind: K;
  readonly label: string;
  readonly aliases?: readonly string[];
  readonly description?: string;
  readonly domainId: string;
  readonly views: readonly ViewId[];
  readonly evidence: Evidence;
  /** Floresta de apresentação opcional; não é a relação semântica `contains`. */
  readonly hierarchyParent?: EntityId | null;
  readonly layout?: LayoutMetadata;
  /** Mostrar uma ação não a autoriza. Nunca conter shell, credenciais ou código. */
  readonly actions?: readonly { readonly actionRef: ActionRef; readonly label: string }[];
}
export type EntityKind =
  | 'system' | 'service' | 'agent' | 'tool' | 'policy' | 'quality_gate'
  | 'skill' | 'data_store' | 'environment' | 'infrastructure' | 'integration'
  | 'protocol' | 'frontend' | 'pipeline' | 'project' | 'template'
  | 'domain' | 'business_entity' | 'contract' | 'document';
export type Entity =
  | (NodeBase<'system'> & { readonly role?: string; readonly lifecycle: 'planned' | 'active' | 'retired' })
  | (NodeBase<'service'> & { readonly runtime?: string; readonly serviceRef?: string })
  | (NodeBase<'agent'> & { readonly role: string; readonly identityRef?: string; readonly profileRef?: string })
  | (NodeBase<'tool'> & { readonly toolRef: string; readonly inputSchemaRef: string; readonly effect: 'read' | 'write' | 'mixed' })
  | (NodeBase<'policy'> & { readonly policyRef: PolicyRef; readonly policyVersion: string })
  | (NodeBase<'quality_gate'> & { readonly checkRef: string; readonly blocking: boolean })
  | (NodeBase<'skill'> & { readonly instructionRef: string; readonly skillVersion?: string })
  | (NodeBase<'data_store'> & { readonly storage: 'relational' | 'vector' | 'document' | 'file' | 'queue' | 'other'; readonly engine?: string })
  | (NodeBase<'environment'> & { readonly stage: 'local' | 'development' | 'test' | 'staging' | 'production'; readonly environmentRef: string })
  | (NodeBase<'infrastructure'> & { readonly resource: 'host' | 'container' | 'network' | 'platform' | 'other'; readonly resourceRef?: string })
  | (NodeBase<'integration'> & { readonly adapterRef?: string; readonly protocolRef?: EntityId })
  | (NodeBase<'protocol'> & { readonly specificationRef: string; readonly protocolVersion?: string })
  | (NodeBase<'frontend'> & { readonly surface: 'web' | 'desktop' | 'mobile' | 'cli' | 'other'; readonly entryRef?: string })
  | (NodeBase<'pipeline'> & { readonly definitionRef: string; readonly trigger: 'manual' | 'event' | 'schedule' })
  | (NodeBase<'project'> & { readonly repositoryRef?: string; readonly ownerRef?: string })
  | (NodeBase<'template'> & { readonly artifact: 'document' | 'code' | 'workflow' | 'other'; readonly templateRef: string })
  | (NodeBase<'domain'> & { readonly definitionRef?: string })
  | (NodeBase<'business_entity'> & { readonly schemaRef?: string })
  | (NodeBase<'contract'> & { readonly schemaRef: string; readonly contractVersion: string })
  | (NodeBase<'document'> & { readonly sourceId: SourceId });

/** Identificadores estáveis; label traduzida pode mudar sem renomear predicate. */
export type Predicate =
  | 'depends_on' | 'contains' | 'runs_in' | 'hosted_on' | 'calls'
  | 'reads_from' | 'writes_to' | 'produces' | 'consumes' | 'implements'
  | 'governed_by' | 'uses_tool' | 'delegates_to' | 'validates'
  | 'evidenced_by' | 'related_to';
export interface SemanticEdgeBase<P extends Predicate> extends DataScope {
  readonly id: EdgeId;
  readonly predicate: P;
  readonly source: EntityId;
  readonly target: EntityId;
  readonly label?: string;
  readonly views: readonly ViewId[];
  readonly evidence: Evidence;
  /** Custo aditivo finito >= 0. Não representa probabilidade ou permissão. */
  readonly cost: number;
  readonly validFrom?: ISODateTime;
  readonly validUntil?: ISODateTime;
}
export type SemanticEdge =
  | (SemanticEdgeBase<'depends_on'> & { readonly required?: boolean })
  | SemanticEdgeBase<'contains'>
  | SemanticEdgeBase<'runs_in'>
  | SemanticEdgeBase<'hosted_on'>
  | (SemanticEdgeBase<'calls'> & { readonly transport?: 'http' | 'websocket' | 'mcp' | 'local' | 'other' })
  | SemanticEdgeBase<'reads_from'>
  | SemanticEdgeBase<'writes_to'>
  | SemanticEdgeBase<'produces'>
  | SemanticEdgeBase<'consumes'>
  | SemanticEdgeBase<'implements'>
  | SemanticEdgeBase<'governed_by'>
  | SemanticEdgeBase<'uses_tool'>
  | SemanticEdgeBase<'delegates_to'>
  | SemanticEdgeBase<'validates'>
  | SemanticEdgeBase<'evidenced_by'>
  | SemanticEdgeBase<'related_to'>;
export interface PredicateDefinition {
  readonly id: Predicate;
  readonly label: string;
  readonly sourceKinds: readonly EntityKind[];
  readonly targetKinds: readonly EntityKind[];
  readonly description: string;
}
export interface KnowledgeGraphV2 extends DataScope {
  readonly schemaVersion: 2;
  readonly ontologyVersion: string;
  readonly snapshotId: string;
  readonly generatedAt: ISODateTime;
  readonly sourceRevision?: string;
  readonly views: readonly { readonly id: ViewId; readonly label: string }[];
  /** Registro versionado: deve definir exatamente todos os predicates utilizados. */
  readonly predicates: readonly PredicateDefinition[];
  readonly sources: readonly SourceDocument[];
  readonly nodes: readonly Entity[];
  readonly edges: readonly SemanticEdge[];
}

/** PROPOSTA: requisição de intenção; parâmetros continuam não confiáveis no servidor. */
export interface ActionIntent {
  readonly actionRef: ActionRef;
  readonly targetId: EntityId;
  readonly snapshotId: string;
  readonly parameters: Readonly<Record<string, JsonValue>>;
  readonly idempotencyKey: string;
}
/** Somente em registro confiável do servidor; não integrar ao JSON exportado para o browser. */
export interface RegisteredCommand {
  readonly commandRef: CommandRef;
  readonly brokerToolRef: string;
  readonly executableRef: string;
  readonly workingDirectoryRef: string;
  readonly fixedArgv: readonly string[];
  readonly parameterSchemaRef: string;
  readonly timeoutMs: number;
  readonly maxOutputBytes: number;
  readonly policyRef: PolicyRef;
}
/** Resultado de resolução/validação server-side; nunca executar por shell. */
export interface ResolvedCommandRequest {
  readonly commandRef: CommandRef;
  readonly argv: readonly string[];
  readonly targetId: EntityId;
  readonly snapshotId: string;
  readonly taskId: string;
}
export type ActionDecision =
  | { readonly verdict: 'deny'; readonly reason: string }
  | { readonly verdict: 'require_approval'; readonly approvalRef: string; readonly requestHash: SHA256 }
  | { readonly verdict: 'allow'; readonly requestHash: SHA256 };

/** Saídas analíticas propostas: executam apenas sobre arestas semânticas autorizadas. */
export type PathResult =
  | { readonly found: false; readonly nodeIds: readonly []; readonly edgeIds: readonly [] }
  | { readonly found: true; readonly nodeIds: readonly EntityId[]; readonly edgeIds: readonly EdgeId[]; readonly hops: number; readonly totalCost: number };
export interface ValidationIssue {
  readonly severity: 'error' | 'warning';
  readonly code: 'duplicate_id' | 'unknown_endpoint' | 'unknown_view' | 'unknown_predicate'
    | 'invalid_predicate_endpoint' | 'invalid_number' | 'invalid_cost' | 'invalid_provenance'
    | 'invalid_scope' | 'unknown_parent' | 'hierarchy_cycle' | 'semantic_cycle';
  readonly ref: string;
  readonly message: string;
}
