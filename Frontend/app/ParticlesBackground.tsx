"use client";

import { useEffect, useRef } from "react";

export default function ParticlesBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    let particles: any[] = [];
    const particleCount = 350; 

    let mouse = { x: -1000, y: -1000 };

    const handleMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    
    window.addEventListener("mousemove", handleMouseMove);
    
    const handleResize = () => {
       width = canvas.width = window.innerWidth;
       height = canvas.height = window.innerHeight;
       init();
    };
    
    window.addEventListener("resize", handleResize);

    class Particle {
      x: number;
      y: number;
      size: number;
      speedX: number;
      speedY: number;
      density: number;

      constructor() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.size = Math.random() * 2.5 + 0.5;
        this.speedX = Math.random() * 0.8 - 0.4;
        this.speedY = Math.random() * 0.8 - 0.4;
        this.density = Math.random() * 30 + 1;
      }

      update() {
        this.x += this.speedX;
        this.y += this.speedY;

        if (this.x > width || this.x < 0) this.speedX *= -1;
        if (this.y > height || this.y < 0) this.speedY *= -1;

        // Push away from mouse
        let dx = mouse.x - this.x;
        let dy = mouse.y - this.y;
        let distance = Math.sqrt(dx * dx + dy * dy);
        let forceDirectionX = dx / distance;
        let forceDirectionY = dy / distance;
        let maxDistance = 180;
        let force = (maxDistance - distance) / maxDistance;
        let directionX = forceDirectionX * force * this.density * 0.6;
        let directionY = forceDirectionY * force * this.density * 0.6;

        if (distance < maxDistance) {
          this.x -= directionX;
          this.y -= directionY;
        }
      }

      draw() {
        if (!ctx) return;
        ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.closePath();
        ctx.fill();
      }
    }

    const init = () => {
      particles = [];
      for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
      }
    };

    let animationFrameId: number;

    const animate = () => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
        particles[i].draw();
      }
      
      // Connect particles
      for (let a = 0; a < particles.length; a++) {
        for (let b = a; b < particles.length; b++) {
          let dx = particles[a].x - particles[b].x;
          let dy = particles[a].y - particles[b].y;
          let distance = dx * dx + dy * dy;
          if (distance < 7000) {
             let opacity = (1 - distance/7000) * 0.7;
             ctx.strokeStyle = `rgba(0, 0, 0, ${opacity})`;
             ctx.lineWidth = 0.6;
             ctx.beginPath();
             ctx.moveTo(particles[a].x, particles[a].y);
             ctx.lineTo(particles[b].x, particles[b].y);
             ctx.stroke();
          }
        }
      }
      
      animationFrameId = requestAnimationFrame(animate);
    };

    init();
    animate();

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div style={{
      position: "fixed",
      top: 0, left: 0,
      width: "100vw", height: "100vh",
      zIndex: -1,
      overflow: "hidden",
      background: "#f3f4f6" // Base light color
    }}>
      <div className="mesh-blob blob-1"></div>
      <div className="mesh-blob blob-2"></div>
      <div className="mesh-blob blob-3"></div>
      
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          top: 0, left: 0,
          width: "100%", height: "100%",
          pointerEvents: "none",
        }}
      />
    </div>
  );
}
