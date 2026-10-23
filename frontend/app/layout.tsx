import type { Metadata } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import Providers from "@/components/Providers";
import SearchBand from "@/components/SearchBand";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import "./globals.css";

// next/font downloads at build time and self-hosts, so the built app runs offline.
// Inter for the UI (zh.ch / bs.ch look, real tabular numbers); Geist Mono only for signatures and the Excel row.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Erschliessung SG.CIV.17 · Staatsarchiv Schwyz (Prototyp)",
  description: "Erschliessungs-Assistent für die Fotos SG.CIV.17: Ort, Gebäude und Strasse mit Quellen und Modell-Sicherheit",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={`${inter.variable} ${mono.variable}`}>
      <body className="flex min-h-screen flex-col bg-paper text-ink">
        <Providers>
          <SiteHeader />
          <SearchBand />
          <div className="flex-1">{children}</div>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
