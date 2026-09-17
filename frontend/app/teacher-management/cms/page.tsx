"use client";

import { Suspense } from "react";
import { TeacherManagementPlatformPage } from "../TeacherManagementPlatformPage";

export default function TeacherManagementCmsPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý giảng viên CMS...</div>}>
      <TeacherManagementPlatformPage platform="cms" />
    </Suspense>
  );
}
