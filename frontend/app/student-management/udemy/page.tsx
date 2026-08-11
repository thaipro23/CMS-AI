"use client";

import { Suspense } from "react";
import { StudentManagementPlatformPage } from "../StudentManagementPlatformPage";

export default function StudentManagementUdemyPage() {
  return (
    <Suspense fallback={<div className="card">Đang tải quản lý sinh viên Udemy...</div>}>
      <StudentManagementPlatformPage platform="udemy" />
    </Suspense>
  );
}
