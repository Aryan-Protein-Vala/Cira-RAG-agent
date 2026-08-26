import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Cinntra / CIRA — Enterprise Recruitment & Intelligence Control Center',
  description: 'Securely query enterprise recruitment and SAP Business One data with AI natural language intelligence.',
  generator: 'v0.app',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect x="4" y="8" width="4" height="12" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.48" /><rect x="10" y="3" width="4" height="19" rx="2" fill="%23818cf8" transform="skewX(-16)" /><rect x="16" y="6" width="4" height="15" rx="2" fill="%23818cf8" transform="skewX(-16)" opacity="0.75" /></svg>',
  },
}

export const viewport: Viewport = {
  themeColor: '#0b0f19',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400;1,700&family=Outfit:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased font-sans transition-colors duration-200" suppressHydrationWarning>
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
