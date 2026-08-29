"use client";

import { Suspense } from "react";
import { TeacherManagementPlatformPage } from "../TeacherManagementPlatformPage";

export default function TeacherManagementUdemyPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý giảng viên Udemy...</div>}>
      <TeacherManagementPlatformPage platform="udemy" />
    </Suspense>
  );
}
