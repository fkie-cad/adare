import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { endpoints } from '@/api/endpoints'
import type { ApiResponse } from '@/types/api'

export interface TestFunction {
  dotnotation: string
  name?: string
  file_name?: string
  description?: string
  [key: string]: unknown
}

export function useTestFunctions(fileName?: string) {
  return useQuery({
    queryKey: ['testfunctions', fileName ?? null],
    queryFn: async () => {
      const url = fileName ? endpoints.testfunctionsByFile(fileName) : endpoints.testfunctions
      const { data } = await api.get<ApiResponse<TestFunction[]>>(url)
      return data.data ?? []
    },
  })
}

export function useTestFunction(dotnotation: string) {
  return useQuery({
    queryKey: ['testfunction', dotnotation],
    queryFn: async () => {
      const { data } = await api.get<ApiResponse<TestFunction>>(
        endpoints.testfunction(dotnotation),
      )
      return data.data!
    },
    enabled: !!dotnotation,
  })
}
