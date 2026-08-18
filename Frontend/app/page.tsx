"use client";

import { useState } from "react";
import { ChatLayout } from "@/components/chat/ChatLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Shield } from "lucide-react";

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState("");

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (employeeId.trim().length > 3) {
      setIsLoggedIn(true);
    } else {
      setError("Please enter a valid Employee ID (at least 4 characters).");
    }
  };

  if (isLoggedIn) {
    return <ChatLayout />;
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop')] bg-cover bg-center opacity-20 mix-blend-screen pointer-events-none"></div>
      <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/80 to-transparent pointer-events-none"></div>
      
      <Card className="w-full max-w-md bg-zinc-900/80 border-zinc-800 backdrop-blur-xl shadow-2xl z-10">
        <CardHeader className="space-y-3 text-center pb-6">
          <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto shadow-lg shadow-indigo-500/30">
            <Shield className="text-white w-6 h-6" />
          </div>
          <CardTitle className="text-2xl font-bold text-white tracking-tight">CIRA Portal</CardTitle>
          <CardDescription className="text-zinc-400">Enter your Employee ID to access the intelligent SAP assistant.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Input
                type="text"
                placeholder="Employee ID"
                value={employeeId}
                onChange={(e) => {
                  setEmployeeId(e.target.value);
                  setError("");
                }}
                className="bg-zinc-950/50 border-zinc-800 text-white h-12 px-4 focus-visible:ring-indigo-500"
              />
              {error && <p className="text-red-400 text-sm pl-1">{error}</p>}
            </div>
            <Button type="submit" className="w-full h-12 bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-md transition-all shadow-lg shadow-indigo-500/25">
              Authenticate
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center border-t border-zinc-800/50 pt-6">
          <p className="text-xs text-zinc-500 text-center">
            Secure connection established. <br/> Access restricted to authorized personnel only.
          </p>
        </CardFooter>
      </Card>
    </div>
  );
}
