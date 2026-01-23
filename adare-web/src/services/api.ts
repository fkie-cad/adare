/**
 * Base API client with Axios
 * Handles requests to ADARE backend
 */

import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { ApiResponse } from '@/types/api'

class ApiClient {
  private instance: AxiosInstance

  constructor(baseURL: string = '/api') {
    this.instance = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.setupInterceptors()
  }

  private setupInterceptors() {
    // Request interceptor
    this.instance.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        // Add timestamp to prevent caching
        if (config.params) {
          config.params._t = Date.now()
        } else {
          config.params = { _t: Date.now() }
        }
        return config
      },
      (error: AxiosError) => {
        return Promise.reject(error)
      }
    )

    // Response interceptor
    this.instance.interceptors.response.use(
      (response) => {
        // Transform backend Result[T] to ApiResponse<T>
        if (response.data && typeof response.data === 'object') {
          if ('success' in response.data) {
            return response
          }
        }
        return response
      },
      (error: AxiosError) => {
        // Handle errors uniformly
        const errorMessage = this.extractErrorMessage(error)
        console.error('CLAUDE: API Error:', errorMessage)
        return Promise.reject(new Error(errorMessage))
      }
    )
  }

  private extractErrorMessage(error: AxiosError): string {
    if (error.response?.data) {
      const data = error.response.data as any
      if (data.error) return data.error
      if (data.message) return data.message
      if (data.detail) return data.detail
    }
    if (error.message) return error.message
    return 'An unknown error occurred'
  }

  // Generic GET request
  async get<T>(url: string, params?: any): Promise<ApiResponse<T>> {
    const response = await this.instance.get<ApiResponse<T>>(url, { params })
    return response.data
  }

  // Generic POST request
  async post<T>(url: string, data?: any): Promise<ApiResponse<T>> {
    const response = await this.instance.post<ApiResponse<T>>(url, data)
    return response.data
  }

  // Generic PUT request
  async put<T>(url: string, data?: any): Promise<ApiResponse<T>> {
    const response = await this.instance.put<ApiResponse<T>>(url, data)
    return response.data
  }

  // Generic DELETE request
  async delete<T>(url: string): Promise<ApiResponse<T>> {
    const response = await this.instance.delete<ApiResponse<T>>(url)
    return response.data
  }

  // Get raw Axios instance for special cases
  getAxiosInstance(): AxiosInstance {
    return this.instance
  }
}

// Export singleton instance
export const api = new ApiClient()
