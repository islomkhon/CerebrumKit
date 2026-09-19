import api from './client'

export async function generateJson<T extends Record<string, any>>(description: string, structure: T): Promise<Partial<T>> {
  const res = await api.post('/admin/generator', { description, structure })
  return res.data
}
