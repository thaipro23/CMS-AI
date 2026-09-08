import type { ReactNode } from "react";
import ConstraintModeControls from "./ConstraintModeControls";

export default function BankQuizLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <ConstraintModeControls />
      {children}
    </>
  );
}
