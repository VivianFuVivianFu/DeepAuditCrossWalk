import type { Metadata } from "next";
import "./style.css";

export const metadata: Metadata = {
  title: "DeepAuditCrossWalk · AI governance coverage",
  description:
    "Traceable questionnaire coverage and enterprise policy gap analysis for Australian banking AI use cases.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
