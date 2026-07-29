import type { Metadata } from "next";
import { Manrope } from "next/font/google";

import "./globals.css";
import { THEME_SCRIPT, ThemeProvider } from "./theme";

const sans = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
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
    // `data-theme` and `color-scheme` are deliberately absent here: the script
    // below owns them. If React rendered `data-theme` it would reset the
    // script's value back to the prerendered one during hydration.
    <html
      lang="en"
      data-astryx-theme="neutral"
      className={sans.variable}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
