import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Decision Pattern Library",
  description: "Pressure-test high-stakes decisions against historical patterns",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        <header className="border-b border-gray-200 bg-white">
          <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-blue-600" />
            <span className="font-semibold text-sm tracking-wide">Decision Pattern Library</span>
            <span className="text-xs text-gray-400 ml-auto">Beta — no auth, share by link</span>
          </div>
        </header>
        <main className="max-w-4xl mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
