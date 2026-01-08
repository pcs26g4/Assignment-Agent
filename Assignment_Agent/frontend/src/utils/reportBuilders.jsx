/**
 * Build HTML report for all students
 */
export const buildReportHTML = (scores, result, title, lastTitle) => {
  const titleText = (lastTitle && lastTitle.trim()) || (title && title.trim()) || 'Report'
  const style = `
    <style>
      body { font-family: Arial, sans-serif; color:#111827; }
      h1 { font-size: 22px; margin-bottom: 12px; }
      h2 { font-size: 18px; margin: 18px 0 8px; }
      .student { border:1px solid #e5e7eb; border-radius:8px; padding:12px; margin:12px 0; }
      .meta { display:flex; justify-content:space-between; font-size: 13px; color:#4b5563; margin-bottom:8px; }
      .q { background:#f9fafb; border-radius:6px; padding:10px; margin:8px 0; }
      .row { margin:2px 0; font-size: 13px; }
      .label { font-weight:600; }
      .ok { color:#047857; font-weight:600; }
      .bad { color:#b91c1c; font-weight:600; }
      .reason { white-space: pre-wrap; }
    </style>
  `
  const header = `<h1>${titleText}</h1>`

  // If we have structured scores (files mode), render student-style report
  if (Array.isArray(scores) && scores.length > 0) {
    const body = scores.map((s, sIdx) => {
    const nm = (s && s.name) ? String(s.name) : `Student ${sIdx + 1}`
    const sc = typeof s?.score_percent === 'number' ? s.score_percent.toFixed(2) : (s?.score_percent ?? '-')
    const reason = (s && s.reasoning) ? String(s.reasoning) : ''
    const details = Array.isArray(s?.details) ? s.details : []
    const needImp = (typeof s?.score_percent === 'number' && s.score_percent >= 100) ? 'None' : (reason || '')
    const meta = `
      <div class="meta">
        <div><span class="label">Student name:</span> ${nm}</div>
        <div><span class="label">Score:</span> ${sc}</div>
      </div>
      <div class="row reason"><span class="label">Reason:</span> ${reason}</div>
      <div class="row"><span class="label">Need to improve:</span> ${needImp}</div>
    `
    const qs = details.length > 0
      ? [`<h2>Per-question evaluation</h2>`].concat(details.map((d, i) => {
          const q = d?.question ? String(d.question) : '-'
          const sa = d?.student_answer ? String(d.student_answer) : '-'
          const ca = d?.correct_answer ? String(d.correct_answer) : '-'
          const res = d?.is_correct === true
            ? '<span class="ok">Correct</span>'
            : '<span class="bad">Incorrect</span>'
          const fb = d?.feedback ? `<div class="row"><span class="label">Feedback:</span> ${String(d.feedback)}</div>` : ''
          return `
            <div class="q">
              <div class="row"><span class="label">Q${i + 1}:</span> ${q}</div>
              <div class="row"><span class="label">Answer:</span> ${sa}</div>
              <div class="row"><span class="label">Correct answer:</span> ${ca}</div>
              <div class="row"><span class="label">Evaluation:</span> ${res}</div>
              ${fb}
            </div>
          `
        })).join("")
      : '<div class="row">No per-question details available.</div>'
    return `<div class="student">${meta}${qs}</div>`
    }).join("")
    return `<!DOCTYPE html><html><head><meta charset="utf-8">${style}</head><body>${header}${body}</body></html>`
  }

  // Fallback: GitHub grading or plain text result
  const plainBody = `
    <div class="student">
      <pre class="reason">${(result || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
    </div>
  `
  return `<!DOCTYPE html><html><head><meta charset="utf-8">${style}</head><body>${header}${plainBody}</body></html>`
}

/**
 * Build HTML report for a single student
 */
export const buildStudentHTML = (student, title, lastTitle) => {
  const titleText = (lastTitle && lastTitle.trim()) || (title && title.trim()) || 'Report'
  const style = `
    <style>
      body { font-family: Arial, sans-serif; color:#111827; }
      h1 { font-size: 22px; margin-bottom: 12px; }
      h2 { font-size: 18px; margin: 18px 0 8px; }
      .student { border:1px solid #e5e7eb; border-radius:8px; padding:12px; margin:12px 0; }
      .meta { display:flex; justify-content:space-between; font-size: 13px; color:#4b5563; margin-bottom:8px; }
      .q { background:#f9fafb; border-radius:6px; padding:10px; margin:8px 0; }
      .row { margin:2px 0; font-size: 13px; }
      .label { font-weight:600; }
      .ok { color:#047857; font-weight:600; }
      .bad { color:#b91c1c; font-weight:600; }
      .reason { white-space: pre-wrap; }
    </style>
  `
  const header = `<h1>${titleText}</h1>`
  const nm = (student && student.name) ? String(student.name) : 'Student'
  const sc = typeof student?.score_percent === 'number' ? student.score_percent.toFixed(2) : (student?.score_percent ?? '-')
  const reason = (student && student.reasoning) ? String(student.reasoning) : ''
  const details = Array.isArray(student?.details) ? student.details : []
  const needImp = (typeof student?.score_percent === 'number' && student.score_percent >= 100) ? 'None' : (reason || '')
  const meta = `
    <div class="meta">
      <div><span class="label">Student name:</span> ${nm}</div>
      <div><span class="label">Score:</span> ${sc}</div>
    </div>
    <div class="row reason"><span class="label">Reason:</span> ${reason}</div>
    <div class="row"><span class="label">Need to improve:</span> ${needImp}</div>
  `
  const qs = details.length > 0
    ? [`<h2>Per-question evaluation</h2>`].concat(details.map((d, i) => {
        const q = d?.question ? String(d.question) : '-'
        const sa = d?.student_answer ? String(d.student_answer) : '-'
        const ca = d?.correct_answer ? String(d.correct_answer) : '-'
        const res = d?.is_correct === true
          ? '<span class="ok">Correct</span>'
          : '<span class="bad">Incorrect</span>'
        const fb = d?.feedback ? `<div class="row"><span class="label">Feedback:</span> ${String(d.feedback)}</div>` : ''
        return `
          <div class="q">
            <div class="row"><span class="label">Q${i + 1}:</span> ${q}</div>
            <div class="row"><span class="label">Answer:</span> ${sa}</div>
            <div class="row"><span class="label">Correct answer:</span> ${ca}</div>
            <div class="row"><span class="label">Evaluation:</span> ${res}</div>
            ${fb}
          </div>
        `
      })).join("")
    : '<div class="row">No per-question details available.</div>'
  const body = `<div class="student">${meta}${qs}</div>`
  return `<!DOCTYPE html><html><head><meta charset="utf-8">${style}</head><body>${header}${body}</body></html>`
}

/**
 * Build HTML report for PPT section
 */
export const buildReportHTMLForSection = (section, filename, title, lastTitle) => {
  const titleText = (lastTitle && lastTitle.trim()) || (title && title.trim()) || 'Report'
  const style = `
    <style>
      body { font-family: Arial, sans-serif; color:#111827; padding: 20px; }
      h1 { font-size: 22px; margin-bottom: 12px; }
      h2 { font-size: 18px; margin: 18px 0 8px; color: #4b5563; }
      h3 { font-size: 16px; margin: 16px 0 6px; color: #6b7280; font-weight: bold; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
      pre { white-space: pre-wrap; font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.6; }
      .section { margin: 20px 0; padding: 15px; background: #f9fafb; border-radius: 8px; border: 1px solid #e5e7eb; }
      .separator { border-top: 2px solid #e5e7eb; margin: 20px 0; }
      .content-section { margin-bottom: 30px; }
    </style>
  `
  const header = `<h1>${titleText}</h1><h2>${filename}</h2>`
  
  // Check if section has both CONTENT and DESIGN evaluations
  const hasContentEval = section.includes('CONTENT EVALUATION')
  const hasDesignEval = section.includes('VISUAL DESIGN EVALUATION')
  
  let body = ''
  if (hasContentEval && hasDesignEval) {
    // Split into content and design sections
    const contentMatch = section.match(/CONTENT EVALUATION[\s\S]*?(?=VISUAL DESIGN EVALUATION|$)/)
    const designMatch = section.match(/VISUAL DESIGN EVALUATION[\s\S]*?$/)
    const contentSection = contentMatch ? contentMatch[0].trim() : ''
    const designSection = designMatch ? designMatch[0].trim() : ''
    
    // Format content section
    const contentHtml = contentSection
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
    
    // Format design section
    const designHtml = designSection
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
    
    body = `
      <div class="content-section">
        <h3>CONTENT EVALUATION</h3>
        <div class="section"><pre>${contentHtml}</pre></div>
      </div>
      <div class="content-section">
        <h3>VISUAL DESIGN EVALUATION</h3>
        <div class="section"><pre>${designHtml}</pre></div>
      </div>
    `
  } else {
    // Single section - format normally
    const content = section
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
    body = `<div class="section"><pre>${content}</pre></div>`
  }
  
  return `<!DOCTYPE html><html><head><meta charset="utf-8">${style}</head><body>${header}${body}</body></html>`
}

