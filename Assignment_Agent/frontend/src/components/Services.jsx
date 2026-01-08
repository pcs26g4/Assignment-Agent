import { useState, useEffect } from 'react'
import Navbar from './Navbar'
import api from '../api/axios'
import GitHubRepo from './GitHubRepo'
import PPTUpload from './PPTUpload'
import { downloadExcel } from '../utils/excelExport'
import { buildReportHTML, buildStudentHTML, buildReportHTMLForSection } from '../utils/reportBuilders'
import { 
  downloadDoc, 
  downloadPdf, 
  downloadStudentTxt, 
  downloadStudentPdf, 
  downloadStudentDoc, 
  downloadResult,
  downloadPPTSectionTxt,
  downloadPPTSectionPdf,
  downloadPPTSectionDoc
} from '../utils/fileDownloaders'
import { splitPPTFileSections, extractPPTScores } from '../utils/pptProcessors'
import { formatLabel, parseJsonResult, renderJsonResult, isValidGitHubUrl, formatFileSize } from '../utils/helpers'

const Services = ({ setIsAuthenticated }) => {
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  const [files, setFiles] = useState([])
  const [pptFiles, setPptFiles] = useState([])
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [pptDragActive, setPptDragActive] = useState(false)
  const [result, setResult] = useState('')
  const [summary, setSummary] = useState('')
  const [scores, setScores] = useState([])
  const [error, setError] = useState('')
  const [uploadedFileIds, setUploadedFileIds] = useState([])
  const [openrouterStatus, setOpenrouterStatus] = useState(null)
  const [lastTitle, setLastTitle] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [mode, setMode] = useState('files') // 'files' | 'github' | 'ppt'
  const [evaluateDesign, setEvaluateDesign] = useState(false) // For PPT: evaluate design vs content


  const handleFiles = (selectedFiles) => {
    const fileArray = Array.from(selectedFiles)
    setFiles(prev => [...prev, ...fileArray])
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files)
    }
  }

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files)
    }
  }

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  const removePPTFile = (index) => {
    setPptFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handlePPTDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setPptDragActive(true)
    } else if (e.type === 'dragleave') {
      setPptDragActive(false)
    }
  }

  const handlePPTDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setPptDragActive(false)
  }

  useEffect(() => {
    // Check Ollama status on component mount
    checkOpenRouterStatus()
  }, [])

  const checkOpenRouterStatus = async () => {
    try {
      const response = await api.get('/openrouter/status')
      setOpenrouterStatus(response.data)
    } catch (err) {
      setOpenrouterStatus({ connected: false })
    }
  }

  const parsedJsonResult = parseJsonResult(result)
  
  // Wrapper function for Excel export that handles mode-specific logic
  const handleDownloadExcel = () => {
    let rawScores = []
    
    // Get scores from scores array or extract from PPT results
    if (mode === 'ppt' && (!scores || scores.length === 0)) {
      rawScores = extractPPTScores(result)
    } else if (scores && scores.length > 0) {
      rawScores = scores
    } else {
      // No scores available
      return
    }
    
    if (rawScores.length === 0) return
    
    downloadExcel(rawScores, title, lastTitle)
  }

  const handleGenerate = async () => {
    if (mode === 'files') {
      if (!title.trim()) {
        setError('Please enter a title')
        return
      }
      if (!description.trim()) {
        setError('Please enter a description')
        return
      }
      if (files.length === 0) {
        setError('Please upload at least one file')
        return
      }
    } else if (mode === 'ppt') {
      if (!title.trim()) {
        setError('Please enter a title')
        return
      }
      if (!description.trim()) {
        setError('Please enter a description')
        return
      }
      if (pptFiles.length === 0) {
        setError('Please upload at least one PPT file')
        return
      }
    } else if (mode === 'github') {
      if (!isValidGitHubUrl(githubUrl)) {
        setError('Please enter a valid public GitHub repository URL')
        return
      }
      if (!description.trim()) {
        setError('Please enter rules/description for how the GitHub repo should be evaluated')
        return
      }
    }

    setIsGenerating(true)
    const usedTitle = title.trim()
    setLastTitle(usedTitle)
    setError('')
    setResult('')
    setSummary('')
    setScores([])
    
    try {
      // Step 1: Upload files (only if in files or ppt mode)
      let fileIds = []
      if (mode === 'files') {
        const formData = new FormData()
        files.forEach(file => {
          formData.append('files', file)
        })
        const uploadResponse = await api.post('/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        if (!uploadResponse.data.success) {
          throw new Error('File upload failed')
        }
        fileIds = uploadResponse.data.file_ids
        setUploadedFileIds(fileIds)
      } else if (mode === 'ppt') {
        const formData = new FormData()
        pptFiles.forEach(file => {
          formData.append('files', file)
        })
        const uploadResponse = await api.post('/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        if (!uploadResponse.data.success) {
          throw new Error('PPT file upload failed')
        }
        fileIds = uploadResponse.data.file_ids
        setUploadedFileIds(fileIds)
      }
      
      // Step 2: Generate content or evaluate/grade GitHub repo
      let response
      if (mode === 'github') {
        // Use GitHub grading endpoint - evaluates repo against user rules/description
        try {
          response = await api.post('/grade-git', {
            github_url: githubUrl.trim(),
            description: description.trim(),
          })
        } catch (err) {
          // Enhanced error handling for debugging
          if (err.response) {
            // Server responded with error status
            throw new Error(err.response?.data?.detail || err.response?.data?.error || `Server error: ${err.response.status}`)
          } else if (err.request) {
            // Request made but no response (network error, backend not running)
            throw new Error('Cannot connect to server. Please ensure the backend server is running on http://localhost:8000')
          } else {
            // Something else happened
            throw new Error(err.message || 'An unexpected error occurred')
          }
        }
        
        if (response.data.success) {
          const grading = response.data.result || {}
          const ruleResults = Array.isArray(grading.rule_results) ? grading.rule_results : []

          const formattedRules = ruleResults.length
            ? ruleResults
                .map((r, idx) => {
                  const satisfied = r?.is_satisfied === true ? 'Yes' : 'No'
                  const sev = r?.severity ? String(r.severity) : '-'
                  const evidence = r?.evidence ? String(r.evidence) : ''
                  const failure = r?.failure_reason ? String(r.failure_reason) : ''
                  return [
                    `Rule ${idx + 1}: ${r?.rule_text || '-'}`,
                    `  Satisfied: ${satisfied}`,
                    `  Severity: ${sev}`,
                    evidence ? `  Evidence: ${evidence}` : '',
                    failure ? `  Reason: ${failure}` : '',
                  ]
                    .filter(Boolean)
                    .join('\n')
                })
                .join('\n\n')
            : ''

          const techMismatch = grading.technology_mismatch || {}
          const techMismatchText =
            techMismatch && (techMismatch.expected_from_description || techMismatch.actual_from_code)
              ? [
                  '**Technology Stack Check:**',
                  `Expected (from description): ${techMismatch.expected_from_description || '-'}`,
                  `Actual (from code): ${techMismatch.actual_from_code || '-'}`,
                  `Has mismatch: ${techMismatch.has_mismatch ? 'Yes' : 'No'}`,
                  techMismatch.details ? `Details: ${techMismatch.details}` : '',
                ]
                  .filter(Boolean)
                  .join('\n')
              : ''

          const formattedResult = [
            grading.rules_summary ? `**Rules Summary:**\n${grading.rules_summary}\n` : '',
            typeof grading.score_percent === 'number'
              ? `**Overall Score (%):** ${grading.score_percent.toFixed(2)}\n`
              : '',
            Array.isArray(grading.detected_technology_stack) && grading.detected_technology_stack.length > 0
              ? `**Detected Technology Stack:**\n${grading.detected_technology_stack.join(', ')}\n`
              : '',
            grading.overall_comment ? `**Overall Comment:**\n${grading.overall_comment}\n` : '',
            techMismatchText ? `${techMismatchText}\n` : '',
            formattedRules ? `**Rule-by-rule Results:**\n${formattedRules}` : '',
          ]
            .filter(Boolean)
            .join('\n')

          setResult(formattedResult || JSON.stringify(grading, null, 2))
          setSummary('') // No summary structure for GitHub grading
          setScores([]) // No student scores for GitHub grading
        } else {
          setError(response.data.error || 'GitHub grading failed')
        }
      } else {
        // Use file upload grading endpoint (for both files and ppt modes)
        response = await api.post('/generate', {
          title: title.trim(),
          description: description.trim(),
          file_ids: fileIds,
          github_url: null,
          evaluate_design: mode === 'ppt' ? evaluateDesign : false
        })
        
        if (response.data.success) {
          setResult(response.data.result || '')
          if (response.data.summary) setSummary(response.data.summary)
          if (Array.isArray(response.data.scores)) setScores(response.data.scores)
          // Clear files after successful generation
          if (mode === 'files') {
            setFiles([])
          } else if (mode === 'ppt') {
            setPptFiles([])
          }
          setTitle('')
          setDescription('')
        } else {
          setError(response.data.error || 'Generation failed')
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'An error occurred during generation')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDownloadResult = () => {
    downloadResult(result, summary, scores, title, lastTitle)
  }
  
  const handleDownloadDoc = () => {
    downloadDoc(result, scores, title, lastTitle)
  }
  
  const handleDownloadPdf = () => {
    downloadPdf(result, scores, title, lastTitle)
  }
  
  const handleDownloadStudentTxt = (student, index) => {
    downloadStudentTxt(student, index, title, lastTitle)
  }
  
  const handleDownloadStudentPdf = (student, index) => {
    downloadStudentPdf(student, index, title, lastTitle)
  }
  
  const handleDownloadStudentDoc = (student, index) => {
    downloadStudentDoc(student, index, title, lastTitle)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      <Navbar setIsAuthenticated={setIsAuthenticated} user={user} />
      
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">Services</h1>
          <p className="text-gray-600">Upload files and generate content</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left Side - Mode Panel */}
          <div className="bg-white rounded-xl shadow-md p-6">
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <button
                onClick={() => setMode('files')}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${mode === 'files' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >File Upload</button>
              <button
                onClick={() => setMode('ppt')}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${mode === 'ppt' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >PPT Upload</button>
              <button
                onClick={() => setMode('github')}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${mode === 'github' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
              >GitHub Repo</button>
            </div>
            <h2 className="text-2xl font-bold text-gray-800 mb-4">
              {mode === 'files' ? 'File Upload' : mode === 'ppt' ? 'PPT Upload' : 'GitHub Repository'}
            </h2>
            
            {mode === 'files' ? (
              <div
                className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                  dragActive
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-gray-300 hover:border-indigo-400'
                }`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
              >
                <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                  <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="text-gray-600 mb-2"><span className="font-semibold text-indigo-600">Click to upload</span> or drag and drop</p>
                <p className="text-sm text-gray-500 mb-4">Multiple files supported (PDF, DOC, DOCX, TXT, and more)</p>
                <input type="file" multiple onChange={handleFileInput} className="hidden" id="file-upload" />
                <label htmlFor="file-upload" className="inline-block bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-700 cursor-pointer transition">Select Files</label>
              </div>
            ) : mode === 'ppt' ? (
              <PPTUpload
                files={pptFiles}
                onFilesChange={setPptFiles}
                onRemoveFile={removePPTFile}
                formatFileSize={formatFileSize}
                dragActive={pptDragActive}
                onDragEnter={handlePPTDrag}
                onDragLeave={handlePPTDrag}
                onDragOver={handlePPTDrag}
                onDrop={handlePPTDrop}
              />
            ) : (
              <>
                <GitHubRepo value={githubUrl} onChange={setGithubUrl} />
                <div className="mt-4 text-sm text-gray-700 bg-indigo-50 border border-indigo-100 rounded-lg p-4">
                  <p className="font-semibold mb-1">How to write the description/rules:</p>
                  <p className="mb-2">
                    Enter the rules in the Description box on the right. The system will check this GitHub repository
                    against those rules and grade it.
                  </p>
                  <p className="font-semibold mb-1">Example:</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li>Backend technology_stack is Python and FastAPI.</li>
                    <li>Use PostgreSQL as the main database.</li>
                    <li>Expose a <code>/health</code> endpoint that returns status 200.</li>
                    <li>Use JWT authentication for protected routes.</li>
                  </ul>
                </div>
              </>
            )}

            {/* Uploaded Files List */}
            {mode === 'files' && files.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold text-gray-800 mb-3">
                  Uploaded Files ({files.length})
                </h3>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {files.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition"
                    >
                      <div className="flex items-center space-x-3 flex-1 min-w-0">
                        <svg
                          className="w-5 h-5 text-indigo-600 flex-shrink-0"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          />
                        </svg>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-800 truncate">
                            {file.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {formatFileSize(file.size)}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => removeFile(index)}
                        className="ml-2 text-red-600 hover:text-red-700 transition"
                        title="Remove file"
                      >
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M6 18L18 6M6 6l12 12"
                          />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Side - Title, Description, Generate */}
          <div className="bg-white rounded-xl shadow-md p-6">
            <h2 className="text-2xl font-bold text-gray-800 mb-4">Content Details</h2>
            
            <div className="space-y-6">
              {/* Title Input */}
              <div>
                <label
                  htmlFor="title"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Enter title..."
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition"
                />
              </div>

              {/* Design Evaluation Toggle - Only for PPT mode */}
              {mode === 'ppt' && (
                <div className="mb-4">
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={evaluateDesign}
                      onChange={(e) => setEvaluateDesign(e.target.checked)}
                      className="w-5 h-5 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                    />
                    <span className="text-sm font-medium text-gray-700">
                      Evaluate Visual Design (instead of content)
                    </span>
                  </label>
                  <p className="text-xs text-gray-500 mt-1 ml-8">
                    When enabled, evaluates both content quality and visual design aspects (layout, colors, typography).
                    Works with PPTX files without requiring PowerPoint installation.
                  </p>
                </div>
              )}

              {/* Description Input */}
              <div>
                <label
                  htmlFor="description"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Description <span className="text-red-500">*</span>
                </label>
                <textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={
                    mode === 'files' 
                      ? "Enter evaluation criteria, questions, or instructions for grading student files..." 
                      : mode === 'ppt'
                      ? "Enter evaluation criteria, questions, or instructions for grading PowerPoint presentations..."
                      : "Enter rules/description for how the GitHub repo should be evaluated..."
                  }
                  rows={8}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition resize-none"
                />
                
                {/* Description Guidelines - Show for file upload and PPT modes */}
                {(mode === 'files' || mode === 'ppt') && (
                  <div className="mt-3 text-sm text-gray-700 bg-indigo-50 border border-indigo-100 rounded-lg p-4">
                    <p className="font-semibold mb-2 text-indigo-900">📝 How to write the description:</p>
                    <p className="mb-2 text-gray-700">
                      {mode === 'ppt' && evaluateDesign
                        ? "For design evaluation, provide context about the presentation topic or any specific design requirements. The system will analyze visual design aspects (layout, colors, typography, etc.)."
                        : mode === 'ppt'
                        ? "Provide clear instructions, questions, or evaluation criteria that will be used to grade the uploaded PowerPoint presentations based on text content."
                        : "Provide clear instructions, questions, or evaluation criteria that will be used to grade the uploaded student files."
                      }
                    </p>
                    <p className="font-semibold mb-1 text-indigo-900">Example descriptions:</p>
                    <div className="space-y-2 text-gray-700">
                      <div className="bg-white rounded p-2 border border-indigo-200">
                        <p className="font-medium text-xs mb-1">Example 1 - Question-based evaluation:</p>
                        <p className="text-xs italic">
                          "Evaluate student answers based on these questions: 1) What is the main theme of the story? 2) Identify three key characters and their roles. 3) Explain the climax of the narrative. Provide detailed feedback for each answer."
                        </p>
                      </div>
                      <div className="bg-white rounded p-2 border border-indigo-200">
                        <p className="font-medium text-xs mb-1">Example 2 - Criteria-based evaluation:</p>
                        <p className="text-xs italic">
                          "Grade the assignment based on: Content accuracy (40%), Structure and organization (30%), Grammar and spelling (20%), Creativity (10%). Provide scores and constructive feedback for each criterion."
                        </p>
                      </div>
                      <div className="bg-white rounded p-2 border border-indigo-200">
                        <p className="font-medium text-xs mb-1">Example 3 - Rubric-style evaluation:</p>
                        <p className="text-xs italic">
                          "Evaluate the essay using this rubric: Introduction (20 points), Body paragraphs with evidence (50 points), Conclusion (15 points), Writing quality (15 points). Identify strengths and areas for improvement."
                        </p>
                      </div>
                    </div>
                    <p className="mt-3 font-semibold text-xs text-indigo-900">💡 Tips:</p>
                    <ul className="list-disc pl-5 space-y-1 text-xs text-gray-700">
                      <li>Be specific about what you want evaluated</li>
                      <li>Include scoring criteria or rubrics if applicable</li>
                      <li>Specify the format you want feedback in</li>
                      <li>Mention any particular aspects to focus on</li>
                    </ul>
                  </div>
                )}
              </div>

              {/* Generate Button */}
              <button
                onClick={handleGenerate}
                disabled={
                  isGenerating ||
                  (mode === 'files' && (!title.trim() || !description.trim() || files.length === 0)) ||
                  (mode === 'ppt' && (!title.trim() || !description.trim() || pptFiles.length === 0)) ||
                  (mode === 'github' && (!isValidGitHubUrl(githubUrl) || !description.trim()))
                }
                className="w-full bg-indigo-600 text-white py-3 rounded-lg font-semibold hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2"
              >
                {isGenerating ? (
                  <>
                    <svg
                      className="animate-spin h-5 w-5 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <svg
                      className="w-5 h-5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                    <span>Generate</span>
                  </>
                )}
              </button>

              {/* Info Box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <div className="flex items-start space-x-3">
                  <svg
                    className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div>
                    <p className="text-sm text-blue-800 font-medium mb-1">Instructions</p>
                    {mode === 'files' ? (
                      <p className="text-sm text-blue-700">
                        Upload multiple files, enter a title and description, then click Generate to grade student
                        answers.
                      </p>
                    ) : mode === 'ppt' ? (
                      <p className="text-sm text-blue-700">
                        Upload multiple PowerPoint files (PPT, PPTX, PPTM), enter a title and description, then click Generate to grade student presentations.
                      </p>
                    ) : (
                      <p className="text-sm text-blue-700">
                        Paste a public GitHub repository URL on the left, write your grading rules in the Description
                        box, and click Generate to see how well the repository matches those rules.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Ollama Status */}
              {openrouterStatus && (
                <div className={`border rounded-lg p-4 ${
                  openrouterStatus.connected 
                    ? 'bg-green-50 border-green-200' 
                    : 'bg-red-50 border-red-200'
                }`}>
                  <div className="flex items-center space-x-2">
                    <div className={`w-3 h-3 rounded-full ${
                      openrouterStatus.connected ? 'bg-green-500' : 'bg-red-500'
                    }`}></div>
                    <p className={`text-sm font-medium ${
                      openrouterStatus.connected ? 'text-green-800' : 'text-red-800'
                    }`}>
                      {openrouterStatus.connected 
                        ? `OpenRouter Connected (${openrouterStatus.default_model})`
                        : 'OpenRouter Not Connected - Check API key or connectivity'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Results Section */}
        {(result || summary || (scores && scores.length > 0) || error) && (
          <div className="mt-8 bg-white rounded-xl shadow-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold text-gray-800">Results</h2>
              {(result || summary || (scores && scores.length > 0)) && (
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-sm text-gray-600 font-medium">
                    {mode === 'files' || mode === 'ppt'
                      ? 'Download all students reports:'
                      : 'Download GitHub evaluation:'}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleDownloadResult}
                      className="bg-indigo-600 text-white px-3 py-2 rounded-lg hover:bg-indigo-700 transition text-sm font-medium"
                      title="Download as .txt"
                    >.txt</button>
                    <button
                      onClick={handleDownloadPdf}
                      className="bg-green-600 text-white px-3 py-2 rounded-lg hover:bg-green-700 transition text-sm font-medium"
                      title="Download as PDF"
                    >.pdf</button>
                    <button
                      onClick={handleDownloadDoc}
                      className="bg-purple-600 text-white px-3 py-2 rounded-lg hover:bg-purple-700 transition text-sm font-medium"
                      title="Download as .doc"
                    >.doc</button>
                  </div>
                  {/* Excel export button for files and PPT modes */}
                  {(mode === 'files' || mode === 'ppt') && (scores && scores.length > 0 || mode === 'ppt') && (
                    <div className="flex items-center gap-2 ml-2 pl-2 border-l border-gray-300">
                      <span className="text-sm text-gray-600 font-medium">Export scores:</span>
                      <button
                        onClick={handleDownloadExcel}
                        className="bg-emerald-600 text-white px-3 py-2 rounded-lg hover:bg-emerald-700 transition text-sm font-medium flex items-center gap-1"
                        title="Download scores as Excel"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        Excel
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
                {error}
              </div>
            )}

            {/* Structured summary - for file uploads and PPT uploads */}
            {(mode === 'files' || mode === 'ppt') && summary && (
              <div className="mb-6">
                <h3 className="text-xl font-semibold text-gray-800 mb-2">Summary</h3>
                <p className="text-gray-700 whitespace-pre-wrap">{summary}</p>
              </div>
            )}

            {/* Structured scores table - for file uploads and PPT uploads, NOT for GitHub */}
            {(mode === 'files' || mode === 'ppt') && scores && scores.length > 0 && (
              <div className="mb-6">
                <h3 className="text-xl font-semibold text-gray-800 mb-3">Student Scores</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Score (%)</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Reasoning</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Download</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {scores.map((s, idx) => (
                        <tr key={idx}>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-800">{s.name || '-'}</td>
                          <td className="px-4 py-2 whitespace-nowrap text-sm text-gray-800">{typeof s.score_percent === 'number' ? s.score_percent.toFixed(2) : s.score_percent}</td>
                          <td className="px-4 py-2 text-sm text-gray-700 whitespace-pre-wrap">{s.reasoning || ''}</td>
                          <td className="px-4 py-2 whitespace-nowrap">
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleDownloadStudentTxt(s, idx)}
                                className="bg-indigo-600 text-white px-2 py-1 rounded text-xs hover:bg-indigo-700 transition"
                                title="Download as .txt"
                              >.txt</button>
                              <button
                                onClick={() => handleDownloadStudentPdf(s, idx)}
                                className="bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700 transition"
                                title="Download as PDF"
                              >.pdf</button>
                              <button
                                onClick={() => handleDownloadStudentDoc(s, idx)}
                                className="bg-purple-600 text-white px-2 py-1 rounded text-xs hover:bg-purple-700 transition"
                                title="Download as .doc"
                              >.doc</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Per-student per-question details - for file uploads and PPT uploads */}
            {(mode === 'files' || mode === 'ppt') && scores && scores.length > 0 && (
              <div className="space-y-6">
                {scores.map((s, sIdx) => (
                  <div key={`details-${sIdx}`} className="bg-white border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-lg font-semibold text-gray-800">{s.name || `Student ${sIdx + 1}`}</h4>
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-600">Score: {typeof s.score_percent === 'number' ? s.score_percent.toFixed(2) : s.score_percent}</span>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDownloadStudentTxt(s, sIdx)}
                            className="bg-indigo-600 text-white px-2 py-1 rounded text-xs hover:bg-indigo-700 transition"
                            title="Download as .txt"
                          >.txt</button>
                          <button
                            onClick={() => handleDownloadStudentPdf(s, sIdx)}
                            className="bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700 transition"
                            title="Download as PDF"
                          >.pdf</button>
                          <button
                            onClick={() => handleDownloadStudentDoc(s, sIdx)}
                            className="bg-purple-600 text-white px-2 py-1 rounded text-xs hover:bg-purple-700 transition"
                            title="Download as .doc"
                          >.doc</button>
                        </div>
                      </div>
                    </div>
                    {Array.isArray(s?.details) && s.details.length > 0 ? (
                      <div className="space-y-3">
                        {s.details.map((d, dIdx) => (
                          <div key={`d-${sIdx}-${dIdx}`} className="rounded-md bg-gray-50 p-3">
                            <p className="text-sm text-gray-800"><span className="font-medium">Q{dIdx + 1}:</span> {d?.question || '-'}</p>
                            <p className="text-sm text-gray-700"><span className="font-medium">Answer:</span> {d?.student_answer || '-'}</p>
                            <p className="text-sm text-gray-700"><span className="font-medium">Correct answer:</span> {d?.correct_answer || '-'}</p>
                            <p className={`text-sm font-medium ${d?.is_correct === true ? 'text-green-700' : 'text-red-700'}`}>
                              Evaluation: {d?.is_correct === true ? 'Correct' : 'Incorrect'}
                            </p>
                            {d?.feedback ? (
                              <p className="text-sm text-gray-600"><span className="font-medium">Feedback:</span> {d.feedback}</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-gray-600">No per-question details available.</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {result && (
              <div className="space-y-6">
                {parsedJsonResult ? (
                  renderJsonResult(parsedJsonResult, formatLabel)
                ) : mode === 'ppt' && result.includes('File:') ? (
                  (() => {
                    const fileSections = splitPPTFileSections(result)
                    // Use the grouped sections - they should already be properly grouped
                    const finalSections = fileSections.length > 0 ? fileSections : [result]
                    
                    return finalSections.map((section, idx) => {
                      // Extract filename from the main "File: " at the start (before CONTENT/DESIGN sections)
                      const mainFileMatch = section.match(/^File:\s*([^\n]+)/m)
                      const filename = mainFileMatch ? mainFileMatch[1].trim() : `File_${idx + 1}`
                      
                      // Check if this section has both CONTENT EVALUATION and VISUAL DESIGN EVALUATION
                      const hasContentEval = section.includes('CONTENT EVALUATION')
                      const hasDesignEval = section.includes('VISUAL DESIGN EVALUATION')
                      
                      // Split into content and design sections if both exist
                      let contentSection = ''
                      let designSection = ''
                      
                      if (hasContentEval && hasDesignEval) {
                        // Extract content section (from CONTENT EVALUATION header to VISUAL DESIGN EVALUATION header)
                        const contentMatch = section.match(/CONTENT EVALUATION[\s\S]*?(?=VISUAL DESIGN EVALUATION|$)/)
                        // Extract design section (from VISUAL DESIGN EVALUATION header to end)
                        const designMatch = section.match(/VISUAL DESIGN EVALUATION[\s\S]*?$/)
                        contentSection = contentMatch ? contentMatch[0].trim() : ''
                        designSection = designMatch ? designMatch[0].trim() : ''
                      }
                      
                      return (
                        <div key={idx} className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                          <div className="flex items-center justify-between mb-3">
                            <h3 className="text-lg font-semibold text-gray-800">{filename}</h3>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => downloadPPTSectionTxt(section, filename, title, lastTitle)}
                                className="bg-indigo-600 text-white px-2 py-1 rounded text-xs hover:bg-indigo-700 transition"
                                title="Download as .txt"
                              >.txt</button>
                              <button
                                onClick={() => downloadPPTSectionPdf(section, filename, title, lastTitle)}
                                className="bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700 transition"
                                title="Download as PDF"
                              >.pdf</button>
                              <button
                                onClick={() => downloadPPTSectionDoc(section, filename, title, lastTitle)}
                                className="bg-purple-600 text-white px-2 py-1 rounded text-xs hover:bg-purple-700 transition"
                                title="Download as .doc"
                              >.doc</button>
                            </div>
                          </div>
                          
                          {/* Display content and design sections separately if both exist */}
                          {hasContentEval && hasDesignEval ? (
                            <div className="space-y-4">
                              {/* Content Evaluation Section */}
                              <div className="bg-white rounded-lg p-4 border border-gray-300">
                                <h4 className="text-md font-semibold text-gray-800 mb-2 border-b border-gray-300 pb-2">
                                  CONTENT EVALUATION
                                </h4>
                                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono max-h-96 overflow-y-auto">
                                  {contentSection}
                                </pre>
                              </div>
                              
                              {/* Visual Design Evaluation Section */}
                              <div className="bg-white rounded-lg p-4 border border-gray-300">
                                <h4 className="text-md font-semibold text-gray-800 mb-2 border-b border-gray-300 pb-2">
                                  VISUAL DESIGN EVALUATION
                                </h4>
                                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono max-h-96 overflow-y-auto">
                                  {designSection}
                                </pre>
                              </div>
                            </div>
                          ) : (
                            <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono max-h-96 overflow-y-auto">
                              {section}
                            </pre>
                          )}
                        </div>
                      )
                    })
                  })()
                ) : (
                  <div className="bg-gray-50 rounded-lg p-4 max-h-96 overflow-y-auto">
                    <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono">
                      {result}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default Services

