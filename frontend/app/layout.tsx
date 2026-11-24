import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quant Control",
  description: "Personal crypto quantitative trading dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
