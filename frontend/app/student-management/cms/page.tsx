"use client";

import { Suspense } from "react";
import { StudentManagementPlatformPage } from "../StudentManagementPlatformPage";

export default function StudentManagementCmsPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý sinh viên CMS...</div>}>
      <StudentManagementPlatformPage platform="cms" />
    </Suspense>
  );
}
