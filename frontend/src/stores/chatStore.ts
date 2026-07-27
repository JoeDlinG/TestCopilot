/**
 * Chat store — persists AI conversation state across page switches so the
 * user doesn't lose their chat history or generated test cases when
 * navigating to other pages and back.
 */
import { create } from 'zustand'
import type { AIChatMessage } from '../types'

interface ChatStore {
  sessionId: string
  messages: AIChatMessage[]
  testCaseResult: any
  queryResult: any
  activeTab: string
  selectedSkills: string[]
  input: string

  setSessionId: (id: string) => void
  addMessage: (msg: AIChatMessage) => void
  setMessages: (msgs: AIChatMessage[]) => void
  setTestCaseResult: (r: any) => void
  setQueryResult: (r: any) => void
  setActiveTab: (tab: string) => void
  setSelectedSkills: (skills: string[]) => void
  setInput: (v: string) => void
  clear: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  sessionId: '',
  messages: [],
  testCaseResult: null,
  queryResult: null,
  activeTab: 'chat',
  selectedSkills: [],
  input: '',

  setSessionId: (id) => set({ sessionId: id }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  setTestCaseResult: (r) => set({ testCaseResult: r }),
  setQueryResult: (r) => set({ queryResult: r }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedSkills: (skills) => set({ selectedSkills: skills }),
  setInput: (v) => set({ input: v }),

  clear: () =>
    set({
      sessionId: '',
      messages: [],
      testCaseResult: null,
      queryResult: null,
      activeTab: 'chat',
      input: '',
    }),
}))
