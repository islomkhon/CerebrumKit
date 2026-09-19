export interface Country {
  id: number
  name: string
  code: string
  phone_code: string[] | null
  is_active: boolean
}

export interface User {
  id: number
  name: string
  email: string
  role: string
  country_id: number | null
  language: string
  is_active: boolean
}

export interface Project {
  id: number
  name: string
  description: string | null
  is_active: boolean
  /** The system's own project: its row cannot be edited or deleted. */
  is_system: boolean
  workflow: any[] | null
  created_at: string
}

export interface AgentContextTool {
  tool_id: number
  name: string
  comment: string | null
  arguments: string | null
  position: number
  is_active: boolean
}

export interface Agent {
  id: number
  name: string
  description: string | null
  skill_ids: number[]
  tool_ids: number[]
  /** Tools this agent runs on its own before it reads a message. */
  context_tools: AgentContextTool[]
  is_active: boolean
}

export interface Skill {
  id: number
  name: string
  description: string | null
  tool_ids: number[]
  is_active: boolean
}

export interface Tool {
  id: number
  name: string
  description: string | null
  type: string | null
  body: string | null
  is_active: boolean
}

export interface Chat {
  id: number
  user_id: number
  project_id: number
  new_messages_count: number
  last_message_id: number | null
  description: string | null
  created_at: string
}

export interface Message {
  id: number
  chat_id: number
  sender_type: string
  sender_id: number | null
  sender_name: string | null
  receiver_type: string | null
  receiver_id: number | null
  receiver_name: string | null
  message_type: string
  content: string | null
  created_at: string
}

export interface ProjectTable {
  id: number
  project_id: number
  table_name: string
  description: string | null
}

export interface ProjectSummary {
  id: number
  name: string
}

export interface StorageColumnInfo {
  name: string
  data_type: string
  description?: string | null
  editor_type?: string | null
  length?: number | null
  nullable?: boolean
  default_value?: any
}

export interface StorageTableInfo {
  name: string
  description?: string | null
  columns: StorageColumnInfo[]
  row_count: number
  projects?: ProjectSummary[]
  is_system?: boolean
}

export interface StorageColumnInput {
  name: string
  data_type: string
  description?: string | null
  length?: number | null
  nullable?: boolean
  default_value?: any
}

export interface StorageTableCreate {
  name: string
  description?: string | null
  columns: StorageColumnInput[]
}

export interface StorageTableUpdate {
  name?: string
  description?: string | null
  columns?: StorageColumnInput[]
}

export interface StorageRow {
  id: number
  data: Record<string, any>
  created_at: string | null
  updated_at: string | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

/** One LLM connection the system can run agents on. */
export interface Platform {
  id: number
  name: string
  base_url: string | null
  api_key: string | null
  model: string
  temperature: number | null
  max_tokens: number | null
  thinking: boolean
  is_active: boolean
  /** The row the system runs on right now, including the first-row fallback. */
  effective: boolean
}

export interface PlatformTestResult {
  ok: boolean
  message: string
}
