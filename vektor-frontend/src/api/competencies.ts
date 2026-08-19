import { apiRequest } from './client';
import type { Competency } from '../types/competency';

export function fetchCompetencies(): Promise<Competency[]> {
  return apiRequest<Competency[]>('/competencies');
}
