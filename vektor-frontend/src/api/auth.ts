import { apiRequest } from './client';
import type { TokenResponse, User } from '../types/auth';

export function login(email: string, password: string): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    anonymous: true,
  });
}

export function fetchMe(): Promise<User> {
  return apiRequest<User>('/users/me');
}
