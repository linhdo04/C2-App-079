import type { Metadata } from "next";
import { ReactNode } from "react";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AeroField | Agricultural Intelligence",
    template: "%s | AeroField",
  },
  description: "Nền tảng điều phối dữ liệu và trợ lý AI cho vận hành nông nghiệp chính xác.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className="h-full antialiased"
      data-scroll-behavior="smooth"
    >
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
