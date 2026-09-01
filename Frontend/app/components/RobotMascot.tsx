'use client'

import React, { useState, useEffect } from 'react'

interface RobotMascotProps {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  isThinking?: boolean
  isTalking?: boolean
  className?: string
  interactive?: boolean
  mood?: 'happy' | 'thinking' | 'excited' | 'neutral'
}

export function RobotMascot({
  size = 'md',
  isThinking = false,
  isTalking = false,
  className = '',
  interactive = true,
}: RobotMascotProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [blink, setBlink] = useState(false)
  const [wave, setWave] = useState(false)

  // Periodic natural eye blink
  useEffect(() => {
    const interval = setInterval(() => {
      setBlink(true)
      setTimeout(() => setBlink(false), 220)
    }, 3800)
    return () => clearInterval(interval)
  }, [])

  // Dimension scaling
  const dimensions = {
    xs: { w: 28, h: 28 },
    sm: { w: 36, h: 36 },
    md: { w: 48, h: 48 },
    lg: { w: 84, h: 84 },
    xl: { w: 120, h: 120 },
  }[size]

  const handleClick = () => {
    if (!interactive) return
    setWave(true)
    setTimeout(() => setWave(false), 1200)
  }

  const activeThinking = isThinking
  const activeTalking = isTalking || wave

  return (
    <div
      className={`robot-mascot-container relative inline-flex items-center justify-center select-none cursor-pointer transition-transform duration-300 ${
        isHovered ? 'scale-105' : ''
      } ${className}`}
      style={{ width: dimensions.w, height: dimensions.h }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleClick}
      title={interactive ? 'CIRA AI Assistant — click me!' : 'CIRA AI Assistant'}
    >
      <svg
        viewBox="0 0 100 100"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`robot-svg w-full h-full filter drop-shadow-md ${
          activeTalking ? 'animate-robot-dance' : activeThinking ? 'animate-robot-think' : 'animate-robot-float'
        }`}
      >
        <defs>
          {/* Head & Body Gradients */}
          <linearGradient id="robotBodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#818cf8" />
            <stop offset="50%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#4f46e5" />
          </linearGradient>

          <linearGradient id="robotFaceGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#0f172a" />
            <stop offset="100%" stopColor="#1e293b" />
          </linearGradient>

          <linearGradient id="robotVisorGlow" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="50%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>

          <linearGradient id="robotEarGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#a5b4fc" />
            <stop offset="100%" stopColor="#6366f1" />
          </linearGradient>

          {/* Glow Filters */}
          <filter id="eyeGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <filter id="auraGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Ambient Glow Aura */}
        <circle
          cx="50"
          cy="52"
          r="40"
          fill="url(#robotVisorGlow)"
          opacity={activeThinking ? '0.35' : isHovered ? '0.25' : '0.12'}
          filter="url(#auraGlow)"
          className={activeThinking ? 'animate-pulse' : ''}
        />

        {/* Antenna */}
        <path
          d="M 50 25 L 50 14"
          stroke="#818cf8"
          strokeWidth="3.5"
          strokeLinecap="round"
        />
        {/* Antenna Orb with pulse */}
        <circle
          cx="50"
          cy="11"
          r={activeThinking ? '5' : '4'}
          fill={activeThinking ? '#38bdf8' : '#c084fc'}
          filter="url(#eyeGlow)"
          className={activeThinking ? 'animate-ping origin-center' : ''}
        />
        <circle
          cx="50"
          cy="11"
          r="4"
          fill={activeThinking ? '#38bdf8' : isHovered ? '#38bdf8' : '#818cf8'}
        />

        {/* Robot Ears / Side Sensors */}
        <rect
          x="14"
          y="38"
          width="6"
          height="16"
          rx="3"
          fill="url(#robotEarGrad)"
        />
        <rect
          x="80"
          y="38"
          width="6"
          height="16"
          rx="3"
          fill="url(#robotEarGrad)"
        />

        {/* Left Hand / Waving Arm */}
        <g
          className={
            wave
              ? 'animate-robot-wave origin-bottom-left'
              : activeThinking
              ? 'animate-robot-hands-busy'
              : ''
          }
          style={{ transformOrigin: '18px 65px' }}
        >
          <ellipse
            cx="17"
            cy={wave ? '52' : '65'}
            rx="5.5"
            ry="7"
            fill="#818cf8"
          />
          <circle cx="17" cy={wave ? '48' : '68'} r="3" fill="#c7d2fe" />
        </g>

        {/* Right Hand */}
        <g
          className={activeThinking ? 'animate-robot-hands-busy-alt' : ''}
          style={{ transformOrigin: '82px 65px' }}
        >
          <ellipse cx="83" cy="65" rx="5.5" ry="7" fill="#818cf8" />
          <circle cx="83" cy="68" r="3" fill="#c7d2fe" />
        </g>

        {/* Legs / Hover Thrusters */}
        <g className={activeThinking || activeTalking ? 'animate-pulse' : ''}>
          <path d="M 35 70 L 32 88" stroke="#6366f1" strokeWidth="8" strokeLinecap="round" />
          <path d="M 65 70 L 68 88" stroke="#6366f1" strokeWidth="8" strokeLinecap="round" />
          {/* Flame Jets */}
          {(activeThinking || activeTalking) && (
            <g filter="url(#eyeGlow)">
              <ellipse cx="32" cy="94" rx="4" ry="8" fill="#38bdf8" />
              <ellipse cx="68" cy="94" rx="4" ry="8" fill="#38bdf8" />
            </g>
          )}
        </g>

        {/* Main Head & Torso Chassis */}
        <rect
          x="20"
          y="24"
          width="60"
          height="52"
          rx="18"
          fill="url(#robotBodyGrad)"
          stroke="#a5b4fc"
          strokeWidth="1.5"
        />

        {/* Gloss highlight on head */}
        <path
          d="M 28 28 Q 50 25 72 28"
          stroke="#ffffff"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.5"
        />

        {/* Face Screen Visor */}
        <rect
          x="26"
          y="33"
          width="48"
          height="32"
          rx="12"
          fill="url(#robotFaceGrad)"
          stroke="#312e81"
          strokeWidth="1"
        />

        {/* Visor Scanlines / Gloss */}
        <path
          d="M 28 36 Q 50 34 72 36"
          stroke="#38bdf8"
          strokeWidth="1"
          opacity="0.3"
        />

        {/* Robot Eyes / Visor Display */}
        {activeThinking ? (
          /* Thinking Mode: Digital processing animation */
          <g filter="url(#eyeGlow)">
            {/* Pulsing Neural Nodes */}
            <circle cx="39" cy="48" r="4.5" fill="#38bdf8" className="animate-pulse" />
            <circle cx="50" cy="48" r="4.5" fill="#818cf8" className="animate-pulse" style={{ animationDelay: '0.2s' }} />
            <circle cx="61" cy="48" r="4.5" fill="#c084fc" className="animate-pulse" style={{ animationDelay: '0.4s' }} />
            <path
              d="M 39 48 L 50 48 L 61 48"
              stroke="#38bdf8"
              strokeWidth="1.5"
              strokeDasharray="2 2"
              opacity="0.7"
            />
          </g>
        ) : activeTalking ? (
          /* Talking Mode: Soundwave Visor */
          <g filter="url(#eyeGlow)">
            <rect x="34" y="44" width="3" height="10" rx="1.5" fill="#38bdf8" className="animate-pulse" />
            <rect x="40" y="41" width="3" height="16" rx="1.5" fill="#818cf8" className="animate-pulse" style={{ animationDelay: '0.15s' }} />
            <rect x="46" y="39" width="3" height="20" rx="1.5" fill="#38bdf8" className="animate-pulse" style={{ animationDelay: '0.3s' }} />
            <rect x="52" y="41" width="3" height="16" rx="1.5" fill="#818cf8" className="animate-pulse" style={{ animationDelay: '0.15s' }} />
            <rect x="58" y="44" width="3" height="10" rx="1.5" fill="#38bdf8" className="animate-pulse" />
          </g>
        ) : blink ? (
          /* Blinking: Flat glowing line */
          <g filter="url(#eyeGlow)">
            <line x1="34" y1="48" x2="44" y2="48" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" />
            <line x1="56" y1="48" x2="66" y2="48" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" />
          </g>
        ) : isHovered ? (
          /* Excited/Happy: Arc/Star Eyes */
          <g filter="url(#eyeGlow)">
            {/* Left Happy Curved Eye */}
            <path
              d="M 34 50 Q 39 42 44 50"
              stroke="#38bdf8"
              strokeWidth="3.5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Right Happy Curved Eye */}
            <path
              d="M 56 50 Q 61 42 66 50"
              stroke="#38bdf8"
              strokeWidth="3.5"
              strokeLinecap="round"
              fill="none"
            />
            {/* Cheerful Smile */}
            <path
              d="M 46 56 Q 50 60 54 56"
              stroke="#c084fc"
              strokeWidth="2"
              strokeLinecap="round"
              fill="none"
            />
          </g>
        ) : (
          /* Normal Friendly Mode: Cute Rounded Cyan Eyes */
          <g filter="url(#eyeGlow)">
            {/* Left Eye */}
            <circle cx="39" cy="48" r="5" fill="#38bdf8" />
            <circle cx="37.5" cy="46.5" r="1.5" fill="#ffffff" />

            {/* Right Eye */}
            <circle cx="61" cy="48" r="5" fill="#38bdf8" />
            <circle cx="59.5" cy="46.5" r="1.5" fill="#ffffff" />

            {/* Subtle Blush Cheeks */}
            <ellipse cx="32" cy="55" rx="2.5" ry="1.5" fill="#f472b6" opacity="0.6" />
            <ellipse cx="68" cy="55" rx="2.5" ry="1.5" fill="#f472b6" opacity="0.6" />

            {/* Cute Dot Smile */}
            <circle cx="50" cy="56" r="1.5" fill="#818cf8" />
          </g>
        )}

        {/* Chest Status Light / Power Core */}
        <circle
          cx="50"
          cy="69"
          r="2.5"
          fill={activeThinking ? '#34d399' : '#38bdf8'}
          filter="url(#eyeGlow)"
          className={activeThinking ? 'animate-pulse' : ''}
        />
      </svg>
    </div>
  )
}

export default RobotMascot
