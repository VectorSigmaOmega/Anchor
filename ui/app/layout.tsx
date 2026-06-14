import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Anchor",
  description: "Grounded regulatory answers over official SEBI and RBI circulars.",
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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
