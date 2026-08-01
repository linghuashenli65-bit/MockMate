import { defineStore } from 'pinia'
import { ls } from '../utils/helpers'

export const usePrepStore = defineStore('prep', {
  state: () => ({
    position: ls.get('position', ''),
    company: ls.get('company', ''),
    resume: ls.get('resume', ''),
    profile: null,          // 岗位画像
    resumeScore: null,      // 简历评分结果
    selectedRound: 'tech_1',
    useCustom: false,
    selectedCustomIds: [],
    lastEvaluation: null,   // 最近一次评分（反馈用）
    // 面试进行中状态
    currentSessionId: null,
    currentQuestionIndex: 0,
    interviewActive: false,
    currentRound: null,
    isWrittenRound: false,
    totalQuestions: 0,
  }),
  actions: {
    setPosition(v) { this.position = v; ls.set('position', v) },
    setCompany(v) { this.company = v; ls.set('company', v) },
    setResume(v) { this.resume = v; ls.set('resume', v) },
    saveFormMemory() {
      ls.set('position', this.position)
      ls.set('company', this.company)
      ls.set('resume', this.resume)
    },
    clearScore() {
      this.resumeScore = null
    },
    startInterviewSession(result) {
      this.currentSessionId = result.session_id
      this.currentQuestionIndex = 0
      this.interviewActive = true
      this.currentRound = result.round
      this.isWrittenRound = result.round === 'written'
      this.totalQuestions = this.selectedCustomIds.length || ROUND_TOTALS[result.round] || 8
      ls.set('active_session', result.session_id)
    },
    resetInterview() {
      this.currentSessionId = null
      this.currentQuestionIndex = 0
      this.interviewActive = false
      this.currentRound = null
      this.isWrittenRound = false
      this.totalQuestions = 0
    },
  },
})

export const ROUND_TOTALS = {
  written: 20,
  tech_1: 8,
  tech_2: 6,
  comprehensive: 6,
}
