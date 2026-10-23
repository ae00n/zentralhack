import type { Metadata } from "next";
import { Barlow, IBM_Plex_Mono } from "next/font/google";
import SearchBand from "@/components/SearchBand";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

// next/font downloads at build time and self-hosts, so the built app runs offline.
// Barlow stands in for sz.ch's Trade Gothic Next (commercial licence, not used).
const barlow = Barlow({
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
  variable: "--font-barlow",
  display: "swap",
});
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Erschliessung SG.CIV.17 · Staatsarchiv Schwyz (Prototyp)",
  description: "Erschliessungs-Assistent für die Fotos SG.CIV.17: Ort, Gebäude und Strasse mit Quellen und Modell-Sicherheit",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={`${barlow.variable} ${mono.variable}`}>
      <body className="flex min-h-screen flex-col bg-paper text-ink">
        <SiteHeader />
        <SearchBand />
        <div className="flex-1">{children}</div>
        <SiteFooter />
      </body>
    </html>
  );
}
