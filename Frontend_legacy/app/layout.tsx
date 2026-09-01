import { Analytics } from '@vercel/analytics/next'
import type { Metadata, Viewport } from 'next'
import './globals.css'
import ParticlesBackground from './ParticlesBackground'

export const metadata: Metadata = {
  title: 'B1 IQ — SAP Data Intelligence',
  description: 'Securely query enterprise SAP data with natural language.',
  generator: 'v0.app',
  icons: {
    icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 25 25"><rect x="4" y="8" width="4" height="12" rx="2" fill="%23c4a1ff" transform="skewX(-16)" opacity="0.48" /><rect x="10" y="3" width="4" height="19" rx="2" fill="%23c4a1ff" transform="skewX(-16)" /><rect x="16" y="6" width="4" height="15" rx="2" fill="%23c4a1ff" transform="skewX(-16)" opacity="0.75" /></svg>',
  },
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#faf7f5',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet" />
      </head>
      <body className="antialiased" suppressHydrationWarning>
        <ParticlesBackground />
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
