import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Anchor — sourced answers on RBI & SEBI regulation",
  description:
    "Ask a question about Indian financial regulation and get an answer drawn only from official RBI Master Directions and SEBI Master Circulars, with the exact citations, or a clear refusal.",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="light"
      data-astryx-theme="neutral"
      className={sans.variable}
    >
      <body>{children}</body>
    </html>
  );
}
