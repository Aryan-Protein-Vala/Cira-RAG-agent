import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'CIRA — SAP Data Intelligence',
  description: 'Securely query enterprise SAP data with natural language.',
  generator: 'v0.app',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect x="4" y="8" width="4" height="12" rx="2" fill="%23e69a9d" transform="skewX(-16)" opacity="0.48" /><rect x="10" y="3" width="4" height="19" rx="2" fill="%23e69a9d" transform="skewX(-16)" /><rect x="16" y="6" width="4" height="15" rx="2" fill="%23e69a9d" transform="skewX(-16)" opacity="0.75" /></svg>',
  },
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: '#f5f3f0',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased" suppressHydrationWarning>
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
