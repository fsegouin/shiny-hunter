import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: 'shiny-hunter (web spike)',
  description: 'Browser-based Gen 1 shiny hunter — WasmBoy spike',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
