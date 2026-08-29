"use client";

import { Suspense } from "react";
// Legacy Batch 34 contracts: Có SV Udemy chậm tiến độ · Làm mới số liệu · createAcademicTrainingTeacherCacheJob
import { TeacherManagementPlatformPage } from "./TeacherManagementPlatformPage";

export default function TeacherManagementPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý giảng viên CMS...</div>}>
      <TeacherManagementPlatformPage platform="cms" />
    </Suspense>
  );
}
