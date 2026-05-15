export type User = {
	id: string
	email: string
	name: string | null
	picture: string | null
}

export type AuthStatus = {
	authenticated: boolean
	user: User | null
}

export type Thread = {
	id: string
	name: string
	created_at: string
	updated_at: string
}

export type ThreadListResponse = {
	threads: Thread[]
}

export type ChatMessage = {
	id: string
	role: 'user' | 'assistant' | 'system'
	content: string
	created_at: string
}

export type GeneratedImage = {
	id: string
	thread_id: string
	prompt: string
	revised_prompt: string | null
	mime_type: string
	image_base64: string
	created_at: string
}

export type ChatHistoryResponse = {
	messages: ChatMessage[]
	generated_images: GeneratedImage[]
}

export type Attachment = {
	id: string
	file_name: string
	mime_type: string
	size_bytes: number
	kind: 'image' | 'video' | 'table' | 'formula' | 'code' | 'file'
	url: string
	created_at: string
}

export type AttachmentListResponse = {
	attachments: Attachment[]
}

export type ImageGenerationRequest = {
	prompt: string
	thread_id?: string
	size?: string
	style?: string
	response_format?: 'b64_json' | 'url'
}

export type ImageGenerationResponse = {
	mime_type: string
	image_base64: string
	revised_prompt: string | null
}

export type ImageValidationRuleInput = {
	rule_id: string
	description?: string
	field_path: string
	operator: string
	expected?: unknown
	required?: boolean
}

export type ImageValidationRequest = {
	image_id: string
	thread_id?: string
	note?: string
	include_default_rules?: boolean
	rules?: ImageValidationRuleInput[]
}

export type ImageValidationRuleResult = {
	rule_id: string
	description: string
	operator: string
	expected: unknown
	extracted: unknown
	passed: boolean
	required: boolean
	message: string
}

export type ImageValidationExtractedData = {
	metadata: Record<string, unknown>
	text: string
	labels: string[]
	fields: Record<string, string>
}

export type ImageValidationResponse = {
	image_id: string
	source_name: string
	source_type: string
	source_thread_id: string | null
	extracted_data: ImageValidationExtractedData
	passed: boolean
	failed_rules: ImageValidationRuleResult[]
	rule_results: ImageValidationRuleResult[]
	summary: string
	chat_summary: string
}

export type StreamEvent =
	| { type: 'token'; content: string }
	| { type: 'done' }
	| { type: 'error'; message: string }

export type LoginRequest = {
	email: string
	password: string
}

export type RegisterRequest = {
	email: string
	password: string
	name?: string
}

export type SupportedDatabaseType = 'mysql' | 'postgresql' | 'sqlite' | 'supabase'

export type DatabaseConnectionInput = {
	db_type?: SupportedDatabaseType
	host?: string
	port?: number
	database?: string
	username?: string
	password?: string
	schema?: string
	sqlite_path?: string
	url?: string
	ssl_required?: boolean
}

export type DatabaseTableColumn = {
	name: string
	data_type: string
}

export type DatabaseTableSchema = {
	name: string
	columns: DatabaseTableColumn[]
}

export type DatabaseConnectRequest = {
	connection?: DatabaseConnectionInput
}

export type DatabaseConnectResponse = {
	connected: boolean
	message: string
	db_type?: string | null
	database?: string | null
	schema?: string | null
	tables: DatabaseTableSchema[]
	schema_summary?: string | null
}

export type DatabaseQueryRequest = {
	question: string
	max_rows?: number
	thread_id?: string
	connection?: DatabaseConnectionInput
}

export type DatabaseQueryResponse = {
	detected_intent: string
	allowed: boolean
	message: string
	sql?: string | null
	explanation?: string | null
	columns: string[]
	rows: Record<string, unknown>[]
	row_count: number
	formatted_table?: string | null
}

export type SpreadsheetQueryRequest = {
	source_id: string
	question: string
	sheet_name?: string
	max_rows?: number
	thread_id?: string
}

export type SpreadsheetQueryResponse = {
	source_type: string
	allowed: boolean
	message: string
	answer: string
	columns: string[]
	rows_considered: number
	thread_id?: string | null
}

export type ImageValidationBatchRequest = {
	image_ids: string[]
	include_default_rules?: boolean
	rules?: ImageValidationRuleInput[]
}

export type ImageValidationBatchItem = {
	image_id: string
	success: boolean
	result: ImageValidationResponse | null
	error: string | null
}

export type ImageValidationBatchResult = {
	total_images: number
	processed_images: number
	passed_images: number
	failed_images: number
	results: ImageValidationBatchItem[]
	summary: string
}

export type ResearchPaper = {
	title: string
	authors: string[]
	published: string
	arxiv_id: string
	url: string
	summary: string
}

export type ResearchDigestQueryRequest = {
	query: string
	max_results?: number
	max_summary_length?: number
	thread_id?: string
}

export type ResearchDigestResponse = {
	query: string
	papers_found: number
	digest: string
	papers: ResearchPaper[]
	thread_id?: string | null
}

export type ResearchDigestStreamEvent =
	| { type: 'status'; stage: string; message: string }
	| { type: 'token'; content: string }
	| { type: 'final'; result: ResearchDigestResponse }
	| { type: 'done' }
	| { type: 'error'; message: string }

// ── Project 12 — MCP Research (same shape as P10, extra agent_source field) ─
export type McpResearchQueryRequest = {
	query: string
	max_results?: number
	max_summary_length?: number
	thread_id?: string
}

export type McpResearchPaper = {
	title: string
	authors: string[]
	published: string
	arxiv_id: string
	url: string
	summary: string
}

export type McpResearchResponse = {
	query: string
	papers_found: number
	digest: string
	papers: McpResearchPaper[]
	thread_id?: string | null
	agent_source: string
}

export type McpResearchStreamEvent =
	| { type: 'status'; stage: string; message: string }
	| { type: 'token'; content: string }
	| { type: 'final'; result: McpResearchResponse }
	| { type: 'done' }
	| { type: 'error'; message: string }

export type TicTacToeMark = 'X' | 'O'

export type TicTacToeMoveRequest = {
	board: string[]
	user_move: number
	user_mark?: TicTacToeMark
	agent_mark?: TicTacToeMark
	thread_id?: string
}

export type TicTacToeMoveResponse = {
	board: string[]
	user_move: number
	agent_move: number | null
	status: 'in_progress' | 'user_won' | 'agent_won' | 'draw'
	winner: TicTacToeMark | null
	agent_reason: string
	agent_source: 'llm' | 'fallback' | 'none'
}
