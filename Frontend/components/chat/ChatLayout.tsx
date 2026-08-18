"use client";

import React, { useState, useRef, useEffect } from 'react';
import { Send, Plus, Search, MoreVertical, Compass, Settings } from 'lucide-react';
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
    <div className="app-shell">
      {/* Sidebar */}
      <div className={`sidebar ${isSidebarOpen ? '' : 'collapsed'}`}>
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <div className="brand-mark">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span>CIRA</span>
          </div>
          <button className="icon-button" onClick={() => setIsSidebarOpen(!isSidebarOpen)}>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
              <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15.25 10.75L12 14.25L8.75 10.75"></path>
            </svg>
          </button>
        </div>

        <div className="sidebar-actions">
          <button className="new-chat">
            <Plus className="w-4 h-4" />
            <span>New chat</span>
          </button>
          <button className="theme-toggle">
            <Search className="w-4 h-4" />
          </button>
        </div>

        <div className="history">
          <div className="history-group">
            <div className="group-label">Today</div>
            <button className="history-item active">
              <div className="history-title">
                <span>SAP Data Query</span>
              </div>
              <div className="history-menu-button">
                <MoreVertical className="w-4 h-4" />
              </div>
            </button>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="profile">
            <div className="avatar">JD</div>
            <div className="profile-info">
              <strong>John Doe</strong>
              <span>EMP-1042</span>
            </div>
            <button className="icon-button">
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="chat-shell">
        <div className="chat-header">
          <div className="mobile-title">
            <button className="icon-button mobile-menu" onClick={() => setIsSidebarOpen(true)}>
              <svg width="24" height="24" fill="none" viewBox="0 0 24 24">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4.75 5.75H19.25M4.75 12H19.25M4.75 18.25H19.25"></path>
              </svg>
            </button>
            <h2>SAP Intelligence</h2>
          </div>
          <div className="header-actions">
            <button className="secondary-button">
              <Compass className="w-4 h-4" />
              <span>Explore Data</span>
            </button>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-intro">
            <div className="intro-icon">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <h1>How can I help you today?</h1>
              <p>Query SAP OData, analyze trends, or request tabular data exports.</p>
            </div>
          </div>

          {messages.map(msg => (
            <div key={msg.id} className={`message-row ${msg.role === 'user' ? 'user' : ''}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? (
                  'JD'
                ) : (
                  <div className="brand-mark">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                )}
              </div>
              <div className="message-content">
                <div className="message-author">
                  {msg.role === 'user' ? (
                    <small>You</small>
                  ) : (
                    <small>CIRA</small>
                  )}
                </div>
                <div className="bubble">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
                {msg.type === 'tabular' && msg.data && (
                  <DataCard data={msg.data} />
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="message-row">
              <div className="message-avatar">
                <div className="brand-mark">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
              <div className="message-content">
                <div className="message-author">
                  <small>CIRA</small>
                </div>
                <div className="bubble text-zinc-500">
                  Thinking...
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Ask anything..."
              rows={1}
            />
            <button 
              onClick={sendMessage}
              disabled={isLoading || !input.trim()}
              className="send-button"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <div className="composer-note">
            CIRA RAG Agent can make mistakes. Consider verifying important information.
          </div>
        </div>
      </div>
    </div>
  );
}
