"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Bot, Menu, ChevronLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { DataCard } from './DataCard';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  type?: 'text' | 'tabular';
  data?: any[];
}

export function ChatLayout() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Hello! I am your SAP Data Assistant. How can I help you today? (Try asking for "data" to see the SAP integration)'
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: userMsg.content, session_id: 'sess_123' })
      });
      const data = await res.json();
      
      const assistantMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.text,
        type: data.type,
        data: data.data
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error connecting to the backend. Please ensure the FastAPI server is running on port 8000.'
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans">
      {/* Sidebar */}
      <div className={`${isSidebarOpen ? 'w-64' : 'w-0'} transition-all duration-300 bg-zinc-900 border-r border-zinc-800 flex flex-col overflow-hidden`}>
        <div className="p-4 border-b border-zinc-800 flex justify-between items-center h-16 shrink-0">
          <h2 className="font-semibold text-lg whitespace-nowrap">Chat History</h2>
          <Button variant="ghost" size="icon" onClick={() => setIsSidebarOpen(false)} className="text-zinc-400 hover:text-white">
            <ChevronLeft className="w-5 h-5" />
          </Button>
        </div>
        <ScrollArea className="flex-1 p-2">
          <div className="p-2 mb-2 rounded-md bg-zinc-800/50 text-sm cursor-pointer hover:bg-zinc-800 transition-colors">
            Current Session
          </div>
        </ScrollArea>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-zinc-950">
        <div className="h-16 border-b border-zinc-800 flex items-center px-4 shrink-0 shadow-sm z-10 bg-zinc-950">
          {!isSidebarOpen && (
            <Button variant="ghost" size="icon" onClick={() => setIsSidebarOpen(true)} className="mr-2 text-zinc-400 hover:text-white">
              <Menu className="w-5 h-5" />
            </Button>
          )}
          <h1 className="font-semibold text-lg bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">CIRA Agent</h1>
        </div>

        <div className="flex-1 overflow-y-auto p-4 md:p-8" ref={scrollRef}>
          <div className="max-w-4xl mx-auto space-y-6">
            {messages.map(msg => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`flex gap-3 max-w-[85%] ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-indigo-600' : 'bg-zinc-800 border border-zinc-700'}`}>
                    {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-indigo-400" />}
                  </div>
                  <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                    <div className={`px-4 py-3 rounded-2xl ${msg.role === 'user' ? 'bg-indigo-600 text-white rounded-tr-sm' : 'bg-zinc-900 border border-zinc-800 text-zinc-200 rounded-tl-sm'}`}>
                      <div className="prose prose-invert max-w-none text-sm">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                    {msg.type === 'tabular' && msg.data && (
                      <DataCard data={msg.data} />
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="flex gap-3 max-w-[85%]">
                  <div className="w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                    <Bot className="w-5 h-5 text-indigo-400" />
                  </div>
                  <div className="px-4 py-3 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-400 rounded-tl-sm flex items-center gap-2">
                    <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce delay-100" />
                    <div className="w-2 h-2 bg-zinc-500 rounded-full animate-bounce delay-200" />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="p-4 bg-zinc-950 border-t border-zinc-800 shrink-0">
          <div className="max-w-4xl mx-auto relative">
            <Input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder="Ask me anything..."
              className="w-full pr-12 bg-zinc-900 border-zinc-800 text-white h-12 rounded-xl focus-visible:ring-indigo-500"
            />
            <Button 
              onClick={sendMessage}
              disabled={isLoading || !input.trim()}
              size="icon" 
              className="absolute right-1 top-1 bottom-1 h-10 w-10 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-white disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </Button>
          </div>
          <div className="text-center mt-2">
            <span className="text-xs text-zinc-500">CIRA RAG Agent can make mistakes. Verify important information.</span>
