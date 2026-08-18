"use client";

import { useState } from "react";
import { ChatLayout } from "@/components/chat/ChatLayout";
import { Lock } from "lucide-react";

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (employeeId && password) {
      setIsLoggedIn(true);
    }
  };

  if (isLoggedIn) {
    return <ChatLayout />;
  }

  return (
    <div className="login-shell">
      <div className="login-top">
      </div>
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span>CIRA SYSTEM</span>
        </div>
        <div className="eyebrow">Enterprise Access</div>
        <h1>Sign <em>In</em></h1>
        <p className="login-copy">Please enter your Employee ID and Password to securely access the intelligent SAP assistant.</p>
        
        <form onSubmit={handleLogin}>
          <label>
            Employee ID or Email
            <input 
              type="text" 
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="e.g. EMP-1042"
              required
            />
          </label>
          <label>
            Password
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>
          <button type="submit" className="primary-button login-button">
            Log In
          </button>
        </form>
        <div className="secure-note">
          <Lock className="w-3 h-3" />
          <span>Secure Connection</span>
        </div>
      </div>
    </div>
  );
}
