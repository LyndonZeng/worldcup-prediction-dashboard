import type {Metadata} from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "2026 World Cup Prediction Dashboard",
  description: "Information-only model dashboard with Asian handicap probabilities."
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

