"use client";

import { Suspense } from "react";
import { CmsTeacherReportArtifactBar } from "../../../components/training/CmsTeacherReportArtifactBar";
import { TeacherManagementPlatformPage } from "../TeacherManagementPlatformPage";

export default function TeacherManagementCmsPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý giảng viên CMS...</div>}>
      <div className="cms-teacher-management-scheduled">
        <CmsTeacherReportArtifactBar />
        <TeacherManagementPlatformPage platform="cms" />
        <style jsx global>{`
          /* CMS management reports are prebuilt after the 05:00 +07 score sync.
             Hide the legacy actions that enqueue refresh/export jobs. Teacher and
             class drill-down pages keep their own live Excel flow unchanged. */
          .cms-teacher-management-scheduled .teacher-management-page .enterprise-page-identity__actions {
            display: none !important;
          }
        `}</style>
      </div>
    </Suspense>
  );
}
