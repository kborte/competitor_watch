import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Header } from "@/components/Header";

export const metadata: Metadata = {
  title: "Competitor Watch",
  description: "QIC competitor-watch dashboard",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col bg-[#f6f6fb]">
        <Providers>
          <Header />
          {children}
        </Providers>
      </body>
    </html>
  );
}
