import type { Metadata } from "next";
import { Shell } from "./components/shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Quant Control",
  description: "个人加密货币量化交易控制台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
