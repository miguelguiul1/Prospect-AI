import "server-only";
import { apiPost } from "@/lib/api/client";
import type { AuditSnapshotDetail } from "@/lib/api/types";

export function runDigitalAudit(companyId: string): Promise<AuditSnapshotDetail> {
  return apiPost<AuditSnapshotDetail>(`/api/audit/${companyId}`);
}
