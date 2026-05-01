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

export type ChatHistoryResponse = {
	messages: ChatMessage[]
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
