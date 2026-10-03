import { HttpErrorResponse } from '@angular/common/http';

/** Message lisible d'une erreur d'API : le `detail` renvoyé par FastAPI s'il existe, sinon `fallback`. */
export function apiErrorMessage(err: HttpErrorResponse, fallback: string): string {
  const body: unknown = err.error;
  if (
    typeof body === 'object' &&
    body !== null &&
    'detail' in body &&
    typeof body.detail === 'string'
  ) {
    return body.detail;
  }
  return fallback;
}
