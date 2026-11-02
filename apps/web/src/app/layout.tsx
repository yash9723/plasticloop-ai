import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import "@fontsource-variable/inter";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "@fontsource/noto-sans-kannada/400.css";
import "@fontsource/noto-sans-kannada/600.css";
import "@fontsource/noto-sans-telugu/400.css";
import "@fontsource/noto-sans-telugu/600.css";
import "@/styles/globals.css";
import type { Locale } from "@/i18n/i18n";
import { AppProviders } from "@/providers/app-providers";

const SUPPORTED: readonly string[] = ["en", "kn", "hi", "te"];

export const metadata: Metadata = {
  title: { default: "PlasticLoop AI", template: "%s · PlasticLoop AI" },
  description: "Intelligent plastic waste collection, traceability and resource recovery for Bengaluru and the towns around it.",
  applicationName: "PlasticLoop AI",
  icons: { icon: "/icons/icon.svg", apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#166534" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieLocale = (await cookies()).get("pl_locale")?.value;
  const locale = (cookieLocale && SUPPORTED.includes(cookieLocale) ? cookieLocale : "en") as Locale;
  return (
    <html lang={locale} suppressHydrationWarning>
      <body>
        <AppProviders initialLocale={locale}>{children}</AppProviders>
      </body>
    </html>
  );
}
